# Copyright 2011-2013 Colin Scott
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# To monkey patch client side (implemented in sts/simulation_state.py):
#  - After booting the controller,
#  - and after STSSyncProtocol's socket has been created (i.e. no more auxiliary
#    sockets remain to be instantiated)
#  - create a single real socket for each ControllerInfo
#  - connect them normally
#  - wrap them in MultiplexedSelect's io_worker
#  - create a STSSocketDemultiplexer for them
#  - override select.select with MultiplexedSelect (this will create a true
#    socket for the pinger)
#  - return STSMocketSockets to all switches rather than socket.sockets

from base import *
from sts.util.convenience import base64_decode
from itertools import count
import logging


log = logging.getLogger("sts_sock_mux")

class STSSocketDemultiplexer(SocketDemultiplexer):
  # All mock sockets have negative fileno()s, to differentiate them from
  # normal files
  # -1 is reserved for the listen socket
  _id_gen = count(start=-2, step=-1)

  def __init__(self, true_io_worker, server_info):
    super(STSSocketDemultiplexer, self).__init__(true_io_worker)
    self.server_info = server_info
    # let MockSockets know who their Demuxer is when they connect()
    STSMockSocket.address2demuxer[server_info] = self

  def _on_receive(self, worker, json_hash):
    super(STSSocketDemultiplexer, self)._on_receive(worker, json_hash)
    assert(json_hash['type'] == 'data' and 'data' in json_hash)
    sock_id = json_hash['id']
    if sock_id not in self.id2socket:
      raise ValueError("Unknown socket id %d" % sock_id)
    sock = self.id2socket[sock_id]
    raw_data = base64_decode(json_hash['data'])
    sock.append_read(raw_data)

  def add_new_socket(self, new_socket):
    sock_id = self._id_gen.next()
    new_socket.sock_id = sock_id
    new_socket.json_worker = self.json_worker
    MultiplexedSelect.fileno2ready_to_read[sock_id] = new_socket.ready_to_read
    self.id2socket[sock_id] = new_socket

class STSMockSocket(MockSocket):
  # Set by STSSocketDemuxers so we know who our demuxer is upon connect()
  address2demuxer = {}

  def connect(self, address):
    if address not in self.address2demuxer:
      raise RuntimeError("don't know our demuxer %s" % str(address))

    self.peer_address = address
    demuxer = self.address2demuxer[address]
    demuxer.add_new_socket(self)

    # Send a SYN
    true_address = demuxer.client_info
    wrapped = {'id' : self.sock_id, 'type' : 'SYN', 'address' : true_address }
    self.json_worker.send(wrapped)
    # Note: select() won't be called by STS with this socket as a param until
    # the switch receives a HELLO message. But for that to occur, we need the
    # controller to initiate the HELLO message in reaction to our connection
    # attempt. Therefore, we need to explicitly
    # cause the underlying socket to send here.
    try:
      l = demuxer.true_io_worker.socket.send(demuxer.true_io_worker.send_buf)
      if l > 0:
        demuxer.true_io_worker._consume_send_buf(l)
    except socket.error as (s_errno, strerror):
      log.error("Socket error: " + strerror)
      raise

  def getpeername(self):
    return self.peer_address

