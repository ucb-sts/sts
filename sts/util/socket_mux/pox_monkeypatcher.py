
from server_socket_multiplexer import ServerMultiplexedSelect,ServerMockSocket
import select
import socket

# Note: Make sure that this module is loaded after all other modules except
# of_01

def launch():
  # Server side:
  #  - Instantiate ServerMultipexedSelect (this will create a true
  #    socket for the pinger)
  #  - override select.select with ServerMultiplexedSelect
  #  - override socket.socket
  #    - takes two params: protocol, socket type
  #    - if not SOCK_STREAM type, return a normal socket
  #  - we don't know bind address until bind() is called
  #  - after bind(), create true socket, create SocketDemultiplexer
  # All subsequent sockets will be instantiated through accept()
  mux_select = ServerMultiplexedSelect()
  # Monkey patch select.select
  select._old_select = select.select
  select.select = mux_select.select
  # Monkey patch socket.socket
  socket._old_socket = socket.socket
  def socket_patch(protocol, sock_type):
    if sock_type == socket.SOCK_STREAM:
      return ServerMockSocket(protocol, sock_type,
                 set_true_listen_socket=mux_select.set_true_listen_socket)
    else:
      socket._old_socket(protocol, sock_type)
  socket.socket = socket_patch
  # TODO(cs): will mux_select be GC'ed?

