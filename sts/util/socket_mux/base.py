
from sts.util.io_master import IOMaster
from pox.lib.ioworker.io_worker import JSONIOWorker
import select
import socket
import logging

# TODO(cs): what if the controller doesn't use a select loop?
# TODO(cs): what if the client chooses to bind() to more than one port?

# The wire protocol is fairly simple:
#  - all messages are wrapped in a json hash
#  - each hash has two fields: `id', and `data'
#  - `id' identifies a channel. The value of `id' is shared between the client
#     socket and the corresponding socket in the server.
#  - Whenever the server sees an id it has not observed before, it creates a
#    MockSocket and stores it to be accept()'ed by the mock listener socket.
#    TODO(cs): we should eventually implement a proper handshake protocol

class SocketDemultiplexer(object):
  def __init__(self, true_io_worker):
    self.json_worker = JSONIOWorker(true_io_worker,
                                    on_json_received=self._on_receive)
    self.id2socket = {}
    self.log = logging.getLogger("sockdemux")

  def _on_receive(self, _, json_hash):
    if 'id' not in json_hash or 'data' not in json_hash:
      raise ValueError("Invalid json_hash %s" % str(json_hash))

class MockSocket(object):
  def __init__(self, protocol, sock_type, sock_id=-1, json_worker=None):
    self.protocol = protocol
    self.sock_type = sock_type
    self.sock_id = sock_id
    self.json_worker = json_worker
    self.pending_reads = []

  def ready_to_read(self):
    return self.pending_reads != []

  def send(self, data):
    wrapped = {'id' : self.sock_id, 'data' : data}
    self.json_worker.send(wrapped)

  def recv(self, bufsize):
    if self.pending_reads == []:
      # Never block
      return None
    # TODO(cs): don't ignore bufsize
    data = self.pending_reads.pop(0)
    return data

  def append_read(self, data):
    self.pending_reads.append(data)

  def fileno(self):
    return self.sock_id

  def setsockopt(self, *args, **kwargs):
    # TODO(cs): implement me
    pass

  def setblocking(self, _):
    # We never block anyway
    pass

  def close(self):
    # TODO(cs): implement me
    pass

class MultiplexedSelect(IOMaster):
  # Note that there will be *two* IOMasters running in the process. This one
  # runs below the normal IOMaster. MultiplexedSelect subclasses IOMaster only to
  # wrap the single true socket in an internal IOWorker. Also note that the normal
  # IOMaster's pinger sockets will in fact be MockSockets. We have the only
  # real pinger socket (MultiplexedSelect must be instantiated before
  # socket.socket is overridden).
  def __init__(self, *args, **kwargs):
    super(MultiplexedSelect, self).__init__(*args, **kwargs)
    self.true_io_worker = None
    self.log = logging.getLogger("mux_select")

  def set_true_io_worker(self, true_io_worker):
    self.true_io_worker = true_io_worker

  def select(self, rl, wl, xl, timeout=0):
    ''' Note that this layer is *below* IOMaster's Select loop (and does not
    include io_workers, consequently). '''
    # Always remove MockSockets (don't mess with other non-socket fds)
    mock_read_socks = [ s for s in rl if isinstance(s, MockSocket) ]
    (rl, wl, xl) = [ [s for s in l if not isinstance(s, MockSocket)]
                     for l in [rl, wl, xl] ]

    # Grab the sock lists for our internal socket. These lists will have at
    # most one element (self.true_io_worker)
    (our_rl, our_wl, our_xl) = self.grab_workers_rwe()

    # TODO(cs): non-monkey-patched version
    (rl, wl, xl) = select.select(rl+our_rl, wl+our_wl, xl+our_xl, timeout)
    (rl, wl, xl) = self.handle_socks_rwe(rl, wl, xl, mock_read_socks)
    return (rl, wl, xl)

  def handle_socks_rwe(self, rl, wl, xl, mock_read_socks):
    if self.pinger in rl:
      self.pinger.pongAll()
      rl.remove(self.pinger)

    if self.true_io_worker in xl:
      raise RuntimeError("Error in true socket")

    if self.true_io_worker in rl:
      rl.remove(self.true_io_worker)
      # Trigger self.true_io_worker.on_received
      try:
        data = self.true_io_worker.socket.recv(self._BUF_SIZE)
        if data:
          self.true_io_worker._push_receive_data(data)
        else:
          self.log.info("Closing true_io_worker after empty read")
          self.true_io_worker.close()
          self._workers.discard(self.true_io_worker)
      except socket.error as (s_errno, strerror):
        self.log.error("Socket error: " + strerror)
        self.true_io_worker.close()
        self._workers.discard(self.true_io_worker)

    if self.true_io_worker in wl:
      wl.remove(self.true_io_worker)
      try:
        l = self.true_io_worker.socket.send(self.true_io_worker.send_buf)
        if l > 0:
          self.true_io_worker._consume_send_buf(l)
      except socket.error as (s_errno, strerror):
        if s_errno != errno.EAGAIN:
          self.log.error("Socket error: " + strerror)
          self.true_io_worker.close()
          self._workers.discard(self.true_io_worker)

    # Now add MockSockets that are ready to read
    rl += [ s for s in mock_read_socks if s.ready_to_read() ]
    return (rl, wl, xl)

def monkeypatch_sts():
  # Client side:
  #  - After booting the controller,
  #  - and after STSSyncProtocol's socket has been created (no more auxiliary
  #    sockets remain to be instantiated)
  #  - override select.select with MultiplexedSelect (this will create a true
  #    socket for the pinger)
  #  - create a single real socket based on ControllerInfos
  #  - connect it normally
  #  - wrap it in MultiplexedSelect's io_worker
  #  - create a SocketDemultiplexer
  #  - override socket.socket
  #    - takes two params: protocol, socket type
  #    - if not SOCK_STREAM type, return a normal socket
  #    - else, return SocketMultplexer.new_socket
  # TODO(cs): is it possible to override classes? Do class contructors take
  # precedence over functions in the same module with the same name?
  pass

def monkeypatch_pox():
  # Server side:
  #  - Instantiate MultipexedSelect (this will create a true
  #    socket for the pinger)
  #  - override select.select with MultiplexedSelect
  #  - override socket.socket
  #    - takes two params: protocol, socket type
  #    - if not SOCK_STREAM type, return a normal socket
  #  - we don't know bind address until bind() is called
  #  - after bind(), create true socket, create SocketDemultiplexer
  # All subsequent sockets will be instantiated through accept()
  pass

