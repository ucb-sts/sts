
from base import *
from itertools import count
import logging

class STSSocketDemultiplexer(SocketDemultiplexer):
  _id_gen = count(1)

  def __init__(self, true_io_worker, server_info):
    super(STSSocketDemultiplexer, self).__init__(true_io_worker)
    self.server_info = server_info
    # let MockSockets know who their Demuxer is upon connect()
    STSMockSocket.address2demuxer[server_info] = self

  def _on_receive(self, worker, json_hash):
    super(STSSocketDemultiplexer, self)._on_receive(worker, json_hash)
    assert(json_hash['type'] == 'data' and 'data' in json_hash)
    sock_id = json_hash['id']
    if sock_id not in self.id2socket:
      raise ValueError("Unknown socket id %d" % sock_id)
    sock = self.id2socket[sock_id]
    raw_data = json_hash['data'].decode('base64')
    sock.append_read(raw_data)

  def add_new_socket(self, new_socket):
    sock_id = self._id_gen.next()
    new_socket.sock_id = sock_id
    new_socket.json_worker = self.json_worker
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
    # cause the underlying socket to send here. connect() is a blocking call,
    # so we're at liberty to block.
    demuxer.true_io_worker.socket.setblocking(1)
    try:
      l = demuxer.true_io_worker.socket.send(demuxer.true_io_worker.send_buf)
      if l > 0:
        demuxer.true_io_worker._consume_send_buf(l)
    except socket.error as (s_errno, strerror):
      log.error("Socket error: " + strerror)
    demuxer.true_io_worker.socket.setblocking(0)

  def getpeername(self):
    return self.peer_address

