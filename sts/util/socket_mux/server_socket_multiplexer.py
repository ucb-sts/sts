
from base import *
import socket
import logging

class ServerSocketDemultiplexer(SocketDemultiplexer):
  def __init__(self, true_io_worker, mock_listen_sock):
    ''' Whenever we see a handshake from the client, hand new MockSockets to
    mock_listen_sock so that they can be accept()'ed'''
    super(ServerSocketDemultiplexer, self).__init__(true_io_worker)
    self.mock_listen_sock = mock_listen_sock

  def _on_receive(self, worker, json_hash):
    sock_id = json_hash['id']
    if sock_id not in self.id2socket:
      # we just saw an unknown channel.
      # TODO(cs): implement a proper handshake protocol
      self.log.debug("Incoming MockSocket connection")
      new_sock = self.new_socket(sock_id=sock_id)
      self.mock_listen_sock.append_new_mock_socket(new_sock)
      new_sock.append_read(json_hash['data'])

  def new_socket(self, sock_id=-1):
    sock = ServerMockSocket(None, None, sock_id=sock_id,
                            json_worker=self.json_worker)
    self.id2socket[sock_id] = sock
    return sock

class ServerMockSocket(MockSocket):
  def __init__(self, protocol, sock_type, sock_id=-1, json_worker=None,
               set_true_listen_socket=lambda: None):
    super(ServerMockSocket, self).__init__(protocol, sock_type,
                                           sock_id=sock_id,
                                           json_worker=json_worker)
    self.set_true_listen_socket = set_true_listen_socket
    self.new_sockets = []

  def ready_to_read(self):
    return self.pending_reads != [] or self.new_sockets != []

  def bind(self, server_info):
    # Before bind() is called, we don't know the
    # address of the true connection. Here, we create a *real* socket.
    # bind it to server_info, and wait for the client SocketDemultiplexer to
    # connect. After this is done, we can instantiate our own
    # SocketDemultiplexer.
    # TODO(cs): un-patched version of socket.socket..
    true_socket = socket.socket(self.protocol, self.sock_type)
    true_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    true_socket.bind(server_info)
    true_socket.setblocking(0)
    true_socket.listen(1)
    # We give this true socket to select.select and
    # wait for the client SocketDemultiplexer connection
    self.set_true_listen_socket(true_socket,
                                accept_callback=self._accept_callback)
    self.server_info = server_info

  def _accept_callback(self, io_worker):
    # Keep a reference so that it won't be gc'ed?
    self.multiplexer = ServerSocketDemultiplexer(io_worker, mock_listen_sock=self)
    # TODO(cs): revert the monkeypatch of socket.socket in case the server
    # makes auxiliary TCP connections

  def listen(self, _):
    pass

  def accept(self):
    sock = self.new_sockets.pop(0)
    # TODO(cs): the second element of this tuple should be the address
    # of the peer, not ourselves. For that, we need a handshake protocol
    return (sock, get_address(self.server_info, sock.sock_id))

  def append_new_mock_socket(self, mock_sock):
    self.new_sockets.append(mock_sock)

class ServerMultiplexedSelect(MultiplexedSelect):
  def __init__(self, *args, **kwargs):
    super(ServerMultiplexedSelect, self).__init__(*args, **kwargs)
    self.true_listen_sock = None

  def set_true_listen_socket(self, true_listen_socket, accept_callback):
    # Keep around true_listen_socket until STS's SocketDemultiplexer connects
    self.true_listen_sock = true_listen_socket
    # At this point, bind() has been called, and we need to wait for the
    # client SocketDemultiplexer to connect. After it connects, we invoke
    # accept_callback with the new io_worker as a parameter
    self.pending_accept = True
    self.accept_callback = accept_callback

  def grab_workers_rwe(self):
    (rl, wl, xl) = super(ServerMultiplexedSelect, self).grab_workers_rwe()
    if self.true_listen_sock is not None:
      rl.append(self.true_listen_sock)
    return (rl, wl, xl)

  def handle_socks_rwe(self, rl, wl, xl, mock_read_socks):
    if self.true_listen_sock in xl:
      raise RuntimeError("Error in listen socket")

    if self.pending_accept and self.true_listen_sock in rl:
      rl.remove(self.true_listen_sock)
      # Once the listen sock gets an accept(), throw out it out (no
      # longer needed), replace it with the return of accept(),
      # and invoke the accept_callback
      self.log.debug("Incoming true socket connected")
      self.pending_accept = False
      new_sock = self.true_listen_sock.accept()[0]
      self.true_listen_sock.close()
      self.true_listen_sock = None
      self.set_true_io_worker(self.create_worker_for_socket(new_sock))
      # The server proc should only ever have one true socket to STS
      assert(len(self.true_io_workers) == 1)
      self.accept_callback(self.true_io_workers[0])

    return super(ServerMultiplexedSelect, self)\
            .handle_socks_rwe(rl, wl, xl, mock_read_socks)

def get_address(server_info, sock_id):
  if type(server_info) == tuple:
    # normal TCP socket
    # (address, mock port no)
    return (self.server_info[0], sock.sock_id)
  else:
    return server_info

