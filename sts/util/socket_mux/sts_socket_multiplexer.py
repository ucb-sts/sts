
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
    sock_id = json_hash['id']
    if sock_id not in self.id2socket:
      raise ValueError("Unknown socket id %d" % sock_id)
    sock = self.id2socket[sock_id]
    sock.append_read(json_hash['data'])

  def add_new_socket(self, new_socket):
    sock_id = self._id_gen.next()
    new_socket.sock_id = sock_id
    new_socket.json_worker = self.json_worker
    self.id2socket[sock_id] = new_socket

class STSMockSocket(MockSocket):
  # Set by STSSocketDemuxers so we know who our demuxer is upon connect()
  address2demuxer = {}

  def connect(self, address):
    # TODO(cs): implement a proper handshake protocol
    if address not in self.address2demuxer:
      raise RuntimeError("don't know our demuxer %s" % str(address))

    demuxer = self.address2demuxer[address]
    demuxer.add_new_socket(self)
