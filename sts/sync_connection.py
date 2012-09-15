import collections
import itertools
import json

from pox.lib.util import parse_openflow_uri

def sync_connect(controller, sync_uri):
 return s

class SyncConnectionManager(object):
  """the connection manager for the STS sync protocols. 
     TODO: finish"""
  def initialize(self, io_master):
    self.io_loop  = io_master
    self.sync_connections = []

  def connect(self, controller, sync_info):
    s = SyncConnection(controller, sync_uri)
    s.connect()

    s.on_disconnect(self.remove_connection)
    return s

  def remove_connection(self, connection):
    self.sync_connections.remove(connection)

class SyncTime(collections.namedtuple('SyncTime', ('seconds', 'microSeconds'))):
  """ ValueObject that models the microsecond timestamps used in STS Sync Messages """
  def __new__(cls, seconds, microSeconds):
    return super(cls, SyncTime).__new__(cls, seconds, microSeconds)

  pass

class SyncMessage(collections.namedtuple('SyncMessage', ('type', 'messageClass', 'time', 'xid', 'name', 'value', 'fingerPrint'))):
  """ value object that models a message in the STS sync protocol """
  def __new__(cls, type, messageClass, time, xid=None, **kw):
    if type not in ("ASYNC", "REQUEST", "RESPONSE"):
      raise ValueError("SyncMessage: type must one of (ASYNC, REQUEST, RESPONSE)")

    if type == "RESPONSE" and xid is None:
      raise ValueError("SyncMessage: xid must be given for messages of type RESPONSE")

    return super(cls, SyncMessage).__new__(cls, type=type, messageClass=messageClass, time=SyncTime(**time), xid=xid, **kw)

class SyncProtocolSpeaker:
  """ speaks the sts sync protocol """
  def __init__(self, json_io_worker=None, state_logger=None):
    self.state_logger = state_logger
    self.xid_generator = itertools.count(1)

    self.handlers = {
        "StateChange": self._log_state_change
    }

    self.set_io_worker(json_io_worker)

  def get_io_worker(self):
    return self._io_worker

  def set_io_worker(self, json_io_worker):
    self._io_worker = json_io_worker
    if(self._io_worker):
      self._io_worker.on_receive_json = self.receive_json

  io_worker = property(get_io_worker, set_io_worker)

  def _log_state_change(self, message):
    self.state_logger.state_change(message.time, message.fingerPrint, message.name, message.value)

  def send(self, message):
    if message.xid is None:
      message = message._replace(xid=self.xid_generator.next())

    if(self._io_worker):
      self._io_worker.send(message._asdict())

  def receive_json(self, worker, json_hash):
    message = SyncMessage(**json_hash)
    if message.messageClass not in self.handlers:
      raise ValueError("Unknown message class: %s" % message.messageClass)
    # dispatch message
    self.handlers[message.messageClass](message)

class SyncConnection(object):
  """ A connection to a controller with the sts sync protocol """
  def initialize(self, controller, sync_uri, state_logger):
    self.controller = controller
    (self.mode, self.host, self.port) = parse_openflow_uri(sync_uri)
    self._on_disconnect = []
    self.speaker = SyncProtocolSpeaker(state_logger=state_logger)

  def on_disconnect(self, func):
    self._on_disconnect.append(func)

  def connect(self, io_master):
    if self.mode != "tcp":
      raise RuntimeError("only tcp (active) mode supported by now")

    socket = connect_socket_with_backoff(self.host, self.port)
    self.io_worker = JSONIOWorker(io_loop.create_worker_for_socket(socket))
    self.speaker.io_worker = self.io_worker

  def disconnect(self):
    self._socket.close()
    for handler in self._on_disconnect:
      handler(self)



