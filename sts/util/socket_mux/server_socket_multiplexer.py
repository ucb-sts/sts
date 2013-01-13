
from base import *
import socket
import logging
import base64

class ServerSocketDemultiplexer(SocketDemultiplexer):
  def __init__(self, true_io_worker, mock_listen_sock):
    ''' Whenever we see a handshake from the client, hand new MockSockets to
    mock_listen_sock so that they can be accept()'ed'''
    super(ServerSocketDemultiplexer, self).__init__(true_io_worker)
    self.mock_listen_sock = mock_listen_sock

  def _on_receive(self, worker, json_hash):
    super(ServerSocketDemultiplexer, self)._on_receive(worker, json_hash)
    sock_id = json_hash['id']
    msg_type = json_hash['type']
    if msg_type == "SYN":
      # we just saw an unknown channel.
      print("Incoming MockSocket connection %s" %
            json_hash['address'])
      new_sock = self.new_socket(sock_id=sock_id,
                                 peer_address=json_hash['address'])
      self.mock_listen_sock.append_new_mock_socket(new_sock)
    elif msg_type == "data":
      raw_data = base64.b64decode(json_hash['data'])
      sock_id = json_hash['id']
      if sock_id not in self.id2socket:
        raise ValueError("Unknown socket id %d" % sock_id)
      sock = self.id2socket[sock_id]
      sock.append_read(raw_data)
    else:
      raise ValueError("Unknown msg_type %s" % msg_type)

  def new_socket(self, sock_id=-1, peer_address=None):
    sock = ServerMockSocket(None, None, sock_id=sock_id,
                            json_worker=self.json_worker,
                            peer_address=peer_address)
    MultiplexedSelect.fileno2ready_to_read[sock_id] = sock.ready_to_read
    self.id2socket[sock_id] = sock
    return sock

class ServerMockSocket(MockSocket):
  def __init__(self, protocol, sock_type, sock_id=-1, json_worker=None,
               set_true_listen_socket=lambda: None, peer_address=None):
    super(ServerMockSocket, self).__init__(protocol, sock_type,
                                           sock_id=sock_id,
                                           json_worker=json_worker)
    self.set_true_listen_socket = set_true_listen_socket
    self.peer_address = peer_address
    self.new_sockets = []
    self.log = logging.getLogger("mock_sock")
    self.listener = False

  def ready_to_read(self):
    return self.pending_reads != [] or self.new_sockets != []

  def bind(self, server_info):
    # Before bind() is called, we don't know the
    # address of the true connection.
    self.server_info = server_info

  def listen(self, _):
    self.listener = True
    # Here, we create a *real* socket.
    # bind it to server_info, and wait for the client SocketDemultiplexer to
    # connect. After this is done, we can instantiate our own
    # SocketDemultiplexer.
    # Assumes that all invocations of bind() are intended for connection to
    # STS. TODO(cs): STS should tell pox_monkeypatcher exactly what ports it
    # intends to bind to. If bind() is called for some other port, delegate to
    # a real socket.
    if hasattr(socket, "_old_socket"):
      true_socket = socket._old_socket(self.protocol, self.sock_type)
    else:
      true_socket = socket.socket(self.protocol, self.sock_type)
    true_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    true_socket.bind(self.server_info)
    true_socket.setblocking(0)
    true_socket.listen(1)
    # We give this true socket to select.select and
    # wait for the client SocketDemultiplexer connection
    self.set_true_listen_socket(true_socket, self,
                                accept_callback=self._accept_callback)

  def _accept_callback(self, io_worker):
    # Keep a reference so that it won't be gc'ed?
    self.demux = ServerSocketDemultiplexer(io_worker, mock_listen_sock=self)
    # revert the monkeypatch of socket.socket in case the server
    # makes auxiliary TCP connections
    if hasattr(socket, "_old_socket"):
      socket.socket = socket._old_socket

  def accept(self):
    sock = self.new_sockets.pop(0)
    return (sock, self.peer_address)

  def append_new_mock_socket(self, mock_sock):
    self.new_sockets.append(mock_sock)

  def __repr__(self):
    if self.listener:
      return "MockListenerSocket"
    else:
      return "MockServerSocket"


class ServerMultiplexedSelect(MultiplexedSelect):
  def __init__(self, *args, **kwargs):
    super(ServerMultiplexedSelect, self).__init__(*args, **kwargs)
    self.true_listen_socks = []
    self.mock_listen_socks = []
    self.listen_sock_to_accept_callback = {}
    self.pending_accepts = 0

  def set_true_listen_socket(self, true_listen_socket, mock_listen_sock, accept_callback):
    # Keep around true_listen_socket until STS's SocketDemultiplexer connects
    self.true_listen_socks.append(true_listen_socket)
    self.mock_listen_socks.append(mock_listen_sock)
    # At this point, bind() has been called, and we need to wait for the
    # client SocketDemultiplexer to connect. After it connects, we invoke
    # accept_callback with the new io_worker as a parameter
    self.pending_accepts += 1
    self.listen_sock_to_accept_callback[true_listen_socket] = accept_callback

  def ready_to_read(self, sock_or_io_worker):
    if sock_or_io_worker in self.mock_listen_socks:
      return sock_or_io_worker.ready_to_read()
    else:
      return super(ServerMultiplexedSelect, self)\
                  .ready_to_read(sock_or_io_worker)

  def grab_workers_rwe(self):
    (rl, wl, xl) = super(ServerMultiplexedSelect, self).grab_workers_rwe()
    rl += self.true_listen_socks
    return (rl, wl, xl)

  def handle_socks_rwe(self, rl, wl, xl, mock_read_socks, mock_write_workers):
    for true_listen_sock in self.true_listen_socks:
      if true_listen_sock in xl:
        raise RuntimeError("Error in listen socket")

      if self.pending_accepts > 0 and true_listen_sock in rl:
        rl.remove(true_listen_sock)
        # Once the listen sock gets an accept(), throw out it out (no
        # longer needed), replace it with the return of accept(),
        # and invoke the accept_callback
        print "Incoming true socket connected"
        self.pending_accepts -= 1
        new_sock = true_listen_sock.accept()[0]
        true_listen_sock.close()
        self.true_listen_socks.remove(true_listen_sock)
        self.set_true_io_worker(self.create_worker_for_socket(new_sock))
        self.listen_sock_to_accept_callback[true_listen_sock]\
                                            (self.true_io_workers[-1])
        del self.listen_sock_to_accept_callback[true_listen_sock]

    return super(ServerMultiplexedSelect, self)\
            .handle_socks_rwe(rl, wl, xl, mock_read_socks, mock_write_workers)
