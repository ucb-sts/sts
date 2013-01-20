
from sts.util.io_master import IOMaster
from pox.lib.ioworker.io_worker import JSONIOWorker, IOWorker
import select
import socket
import logging
import errno
import base64
import threading

log = logging.getLogger("sock_mux")

# TODO(cs): what if the controller doesn't use a select loop? The demuxing can
# still be achieved, it's just that all socket calls will be blocking. We
# would also need to make sure that our code is thread-safe.

# The wire protocol is fairly simple:
#  - all messages are wrapped in a json hash
#  - each hash has two fields: `id', and `type'
#  - `id' identifies a channel. The value of `id' is shared between the client
#     socket and the corresponding socket in the server.
#  - Upon connect(), tell the server that we've connected. `type' is set to
#    "SYN", and an additional `address' field tells the server the proper
#    address to return from accept().
#  - Upon seeing the SYN for an id it has not observed before, the server
#    creates a MockSocket and stores it to be accept()'ed by the mock listener
#    socket.
#  - All data messages are of type `data', and include a `data' field

class SocketDemultiplexer(object):
  def __init__(self, true_io_worker):
    self.true_io_worker = true_io_worker
    self.client_info = true_io_worker.socket.getsockname()
    self.json_worker = JSONIOWorker(true_io_worker,
                                    on_json_received=self._on_receive)
    self.id2socket = {}
    self.log = logging.getLogger("sockdemux")

  def _on_receive(self, _, json_hash):
    if 'id' not in json_hash or 'type' not in json_hash:
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
    # base 64 occasionally adds extraneous newlines: bit.ly/aRTmNu
    json_safe_data = base64.b64encode(data).replace("\n", "")
    wrapped = {'id' : self.sock_id, 'type' : 'data', 'data' : json_safe_data}
    self.json_worker.send(wrapped)
    # that just put it on a buffer. Now, actually send...
    # TODO(cs): this is hacky. Should really define our own IOWorker class
    buf = self.json_worker.io_worker.send_buf
    l = self.json_worker.io_worker.socket.send(buf)
    if l != len(buf):
      raise RuntimeError("FIXME: data didn't fit in one send()")
    self.json_worker.io_worker._consume_send_buf(l)
    return len(data)

  def recv(self, bufsize):
    if self.pending_reads == []:
      log.warn("recv() called with an empty buffer")
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

  def getpeername(self):
    pass

  def close(self):
    # TODO(cs): implement me
    pass

def is_mocked(sock_or_io_worker):
  return sock_or_io_worker.fileno() < 0

def sort_sockets(rl, wl, xl):
  for l in [rl, wl, xl]:
    l.sort(key=lambda s: s.fileno())
  return (rl, wl, xl)

class MultiplexedSelect(IOMaster):
  # Note that there will be *two* IOMasters running in the process. This one
  # runs below the normal IOMaster. MultiplexedSelect subclasses IOMaster only to
  # wrap its true socket(s) in an internal IOWorker. Also note that the normal
  # IOMaster's pinger sockets will in fact be MockSockets. We have the only
  # real pinger socket (MultiplexedSelect must be instantiated before
  # socket.socket is overridden).

  # The caller may pass in classes that wrap our MockSockets. select() can
  # only rely on the fileno() to tell whether the socket is ready to read.
  # Therefore we keep a map fileno() -> MockSocket.ready_to_read.
  # TODO(cs): perhaps this shouldn't be a class variable
  fileno2ready_to_read = {}

  def __init__(self, *args, **kwargs):
    super(MultiplexedSelect, self).__init__(*args, **kwargs)
    self.true_io_workers = []
    self.log = logging.getLogger("mux_select")

  def set_true_io_worker(self, true_io_worker):
    self.true_io_workers.append(true_io_worker)

  def ready_to_read(self, sock_or_io_worker):
    fileno = sock_or_io_worker.fileno()
    if fileno >= 0:
      raise ValueError("Not a MockSocket!")
    if fileno not in self.fileno2ready_to_read:
      raise RuntimeError("Unknown mock fileno %d" % fileno)
    return self.fileno2ready_to_read[fileno]()

  def select(self, rl, wl, xl, timeout=0):
    ''' Note that this layer is *below* IOMaster's Select loop '''
    # If this isn't the main thread, use normal select
    if (threading.current_thread().name != "MainThread" and
        threading.current_thread().name != "BackgroundIOThread"):
      if hasattr(select, "_old_select"):
        return select._old_select(rl, wl, xl, timeout)
      else:
        return select.select(rl, wl, xl, timeout)

    # Always remove MockSockets or wrappers of MockSockets
    # (don't mess with other non-socket fds)
    mock_read_socks = [ s for s in rl if is_mocked(s) ]
    mock_write_workers = [ w for w in wl if is_mocked(w) ]

    # If any of our mock sockets are ready to read, return immediately
    ready_to_read_mock = [ s for s in mock_read_socks if self.ready_to_read(s) ]
    if ready_to_read_mock != [] or mock_write_workers != []:
      return sort_sockets(ready_to_read_mock, mock_write_workers, [])

    (rl, wl, xl) = [ [s for s in l if not is_mocked(s) ]
                     for l in [rl, wl, xl] ]

    # Grab the sock lists for our internal socket. These lists will contain
    # our true_io_worker(s), along with our pinger.
    (our_rl, our_wl, our_xl) = self.grab_workers_rwe()

    if hasattr(select, "_old_select"):
      (rl, wl, xl) = select._old_select(rl+our_rl, wl+our_wl, xl+our_xl, timeout)
    else:
      (rl, wl, xl) = select.select(rl+our_rl, wl+our_wl, xl+our_xl, timeout)
    (rl, wl, xl) = self.handle_socks_rwe(rl, wl, xl, mock_read_socks,
                                         mock_write_workers)
    return (rl, wl, xl)

  def handle_socks_rwe(self, rl, wl, xl, mock_read_socks, mock_write_workers):
    if self.pinger in rl:
      self.pinger.pongAll()
      rl.remove(self.pinger)

    for true_io_worker in self.true_io_workers:
      if true_io_worker in xl:
        raise RuntimeError("Error in true socket")

      if true_io_worker in rl:
        rl.remove(true_io_worker)
        # Trigger self.true_io_worker.on_received
        try:
          data = true_io_worker.socket.recv(self._BUF_SIZE)
          if data:
            true_io_worker._push_receive_data(data)
          else:
            print "Closing true_io_worker after empty read"
            true_io_worker.close()
            self._workers.discard(true_io_worker)
        except socket.error as (s_errno, strerror):
          if s_errno != errno.EWOULDBLOCK:
            print ("Socket read error: " + strerror)
            true_io_worker.close()
            self._workers.discard(true_io_worker)

      if true_io_worker in wl:
        wl.remove(true_io_worker)
        try:
          l = true_io_worker.socket.send(true_io_worker.send_buf)
          if l > 0:
            true_io_worker._consume_send_buf(l)
        except socket.error as (s_errno, strerror):
          if s_errno != errno.EAGAIN and s_errno != errno.EWOULDBLOCK:
            print "Socket error: " + strerror
            true_io_worker.close()
            self._workers.discard(true_io_worker)

    # Now add MockSockets that are ready to read
    rl += [ s for s in mock_read_socks if self.ready_to_read(s) ]
    # As well as MockSockets that are ready to write.
    # This will cause the IOMaster above to flush the
    # io_worker's buffers into our true_io_worker.
    wl += mock_write_workers
    # Sort all sockets to ensure determinism
    return sort_sockets(rl, wl, xl)

