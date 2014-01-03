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

# Note: Make sure that this module is loaded after all other modules except
# of_01; the OpenFlow listen socket needs to be mocked.

from server_socket_multiplexer import *
import select
import socket
import os
import signal
from pox.core import core

log = core.getLogger()

def launch(snapshot_address=None):
  '''
  snapshot_address is a path to a unix domain socket to listen on.
  If None, snapshotting is not enabled.
  '''
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

  # N.B. ServerMultiplexedSelect sits underneath POX's select.select calls,
  # and obtains control of the thread whenever POX invokes select.select.
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

  if snapshot_address:
    # Snapshotting protocol (over a domain socket):

    # In STS:
    #  - set simulation to "record-only" mode
    #  - send "SNAPSHOT" to controller

    # In controller upon receiving "SNAPSHOT":
    #  - fork a child
    #     - in child, set (inherited) domain socket to blocking
    #     - write READY <PID>
    #     - block on recv()
    #  - proceed

    # In STS after peek()ing:
    #  - double check that READY <PID> was received
    #  - kill parent process
    #  - send "PROCEED" to domain socket
    #  - close STSSocketDemultiplexer.true_io_worker.socket
    #  - create a new socket and connect it to the same (address, port) pair
    #    as before
    #  - override STSSocketDemultiplexer.true_io_worker.socket
    #  - unset "record-only" mode
    #  - proceed

    # In child, upon recv()ing "PROCEED":
    #  - create a new blocking listen socket bound to
    #    ServerSocketDemultiplexer.mock_listen_sock.server_info
    #    (old true listen socket should already have been closed)
    #  - wait for ClientSocketDemultiplexer to connect()
    #  - accept(), and close() the previous true socket
    #  - replace true_io_worker.socket with return value from accept()

    # N.B. the synchronization of this snapshot protocol isn't perfect.
    # For example it's possible that the snapshot protocol itself perturbs
    # the behavior of the forked controller.

    # N.B. probably shouldn't run STSSyncProto with snapshotting, since we're
    # messing with sockets.

    def proceed():
      '''
      executed within in the forked controller process after STS has
      finished peek()ing.

      This method blocks until STS connects a new mux socket.
      '''
      log.debug("Received PROCEED command. Wiring new mux socket")
      # Clone the old true listen socket, but make it block
      demuxer = ServerSocketDemultiplexer.instance
      to_clone = demuxer.mock_listen_sock
      try:
        cloned_listen_sock = create_true_listen_socket(to_clone.server_info,
                                                       to_clone.protocol,
                                                       to_clone.sock_type,
                                                       blocking=1)
      except:
        log.critical('''Error cloning mux listen socket. Perhaps the parent process'''
                     ''' hasn't finished the mux handshake yet, and is still '''
                     ''' bound to %s?''' % to_clone.server_info)
        raise

      # block until ClientSocketDemultiplexer connect()s, then replace our mux
      # socket with a new one.
      log.debug("accept()ing new mux socket")
      new_socket = cloned_listen_sock.accept()[0]
      cloned_listen_sock.close()
      demuxer.true_io_worker.socket = new_socket
      log.debug("Done rewiring")

    def snapshot(snapshot_sock):
      log.debug("Received SNAPSHOT signal. fork()ing")

      if mux_select.true_listen_socks != []:
        # snapshotting should only be executed after the socket_mux
        # bind/listen/accept protocol has completed.
        raise RuntimeError("Should not snapshot before mux handshake has completed")

      pid = os.fork()
      if pid == 0: # Child
        snapshot_sock.setblocking(1)
        log.debug("Sending READY")
        snapshot_sock.send("READY %d" % os.getpid())
        command = snapshot_sock.recv(100)
        snapshot_sock.setblocking(0)
        if command == "PROCEED":
          proceed()
        else:
          raise ValueError("Unknown command %s" % command)

    def read_snapshot_commands(io_worker):
      command = io_worker.peek_receive_buf()
      io_worker.consume_receive_buf(len(command))
      if command == "SNAPSHOT":
        snapshot(snapshot_sock)
      else:
        raise ValueError("Unknown command %s" % command)

    log.debug("Creating snapshot listen socket")
    # Make sure the domain socket does not already exist
    try:
      os.unlink(snapshot_address)
    except OSError:
      if os.path.exists(snapshot_address):
        raise RuntimeError("can't remove snapshot domain socket %s" % str(snapshot_address))

    snapshot_listen_sock = create_true_listen_socket(snapshot_address, socket.AF_UNIX,
                                                     socket.SOCK_STREAM, blocking=1)
    log.debug("accept()ing snapshot socket")
    # N.B. this is a blocking operation. STS needs to connect immediately
    # after booting this controller.
    snapshot_sock = snapshot_listen_sock.accept()[0]
    log.debug("snapshot socket accept()ed")
    snapshot_sock.setblocking(0)
    snapshot_worker = mux_select.create_worker_for_socket(snapshot_sock)
    snapshot_worker.set_receive_handler(read_snapshot_commands)
