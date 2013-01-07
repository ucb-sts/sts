
from base import *
from itertools import count
import logging

class STSSocketDemultiplexer(SocketDemultiplexer):
  _id_gen = count(1)

  def _on_receive(self, worker, json_hash):
    super(STSSocketDemultiplexer, self)._on_receive(worker, json_hash)
    sock_id = json_hash['id']
    if sock_id not in self.id2socket:
      raise ValueError("Unknown socket id %d" % sock_id)
    sock = self.id2socket[sock_id]
    sock.append_read(json_hash['data'])

  def new_socket(self):
    sock_id = self._id_gen.next()
    sock = STSMockSocket(None, None, sock_id=sock_id,
                         json_worker=self.json_worker)
    self.id2socket[sock_id] = sock
    return sock

class STSMockSocket(MockSocket):
  def connect(self, address):
    # TODO(cs): implement a proper handshake protocol
    pass

