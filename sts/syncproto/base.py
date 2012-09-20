import collections
import itertools
import json
import logging
import time

from pox.lib.ioworker.io_worker import JSONIOWorker
from pox.lib.util import parse_openflow_uri, connect_socket_with_backoff

log = logging.getLogger("sync_connection")


class SyncTime(collections.namedtuple('SyncTime', ('seconds', 'microSeconds'))):
  """ ValueObject that models the microsecond timestamps used in STS Sync Messages """
  def __new__(cls, seconds, microSeconds):
    return super(cls, SyncTime).__new__(cls, seconds, microSeconds)

  @staticmethod
  def now():
    # if time.time has been patched by sts then we don't want to fall into this
    # trap ourselves
    if(hasattr(time, "_orig_time")):
      now = time._orig_time()
    else:
      now = time.time()
    return SyncTime( int(now), int((now * 1000000) % 1000000))

  def as_float(self):
    return float(self.seconds) + float(self.microSeconds) / 1e6

class SyncMessage(collections.namedtuple('SyncMessage', ('type', 'messageClass', 'time', 'xid', 'name', 'value', 'fingerPrint'))):
  """ value object that models a message in the STS sync protocol """
  def __new__(cls, type, messageClass, time=None, xid=None, name=None, value=None, fingerPrint=None):
    if type not in ("ASYNC", "REQUEST", "RESPONSE"):
      raise ValueError("SyncMessage: type must one of (ASYNC, REQUEST, RESPONSE)")

    if type == "RESPONSE" and xid is None:
      raise ValueError("SyncMessage: xid must be given for messages of type RESPONSE")

    if time is None:
      time = SyncTime.now()
    elif isinstance(time, SyncTime):
      pass
    elif isinstance(time, list):
      time = SyncTime(*time)
    elif isinstance(time, dict):
      time = SyncTime(**time)
    else:
      raise ValueError("Unknown type %s (repr %s) for time" % (time.__class__, repr(time)))

    return super(cls, SyncMessage).__new__(cls, type=type, messageClass=messageClass, time=time, xid=xid, name=name, value=value, fingerPrint=fingerPrint)

class SyncIODelegate(object):
  def __init__(self, io_master, socket):
    self.io_master = io_master
    self.io_worker = JSONIOWorker(self.io_master.create_worker_for_socket(socket))

  def wait_for_message(self):
    self.io_master.select(None)

  def send(self, msg):
    self.io_worker.send(msg)

  def get_on_message_received(self):
    return self.io_worker.on_json_received

  def set_on_message_received(self, f):
    self.io_worker.on_json_received = lambda io_worker, msg: f(msg)

  on_message_received = property(get_on_message_received, set_on_message_received)

class SyncProtocolSpeaker(object):
  """ speaks the sts sync protocol """
  def __init__(self, handlers, io_delegate):
    self.xid_generator = itertools.count(1)
    self.handlers = handlers
    self.io = io_delegate
    self.io.on_message_received = self.on_message_received
    self.waiting_xids = set()
    self.received_responses = {}
    self.sent_xids = set()

  def message_with_xid(self, message):
    if message.xid:
      return message
    else:
      return message._replace(xid=self.xid_generator.next())

  def send(self, message):
    message = self.message_with_xid(message)
    if(message.xid in self.sent_xids):
      raise RuntimeError("Error sending message %s: XID %d already sent" % (str(message), message.xid))
    self.sent_xids.add(message.xid)
    self.io.send(message._asdict())

    return message

  def on_message_received(self, msg_hash):
    message = SyncMessage(**msg_hash)
    key = (message.type, message.messageClass)

    if message.type == "RESPONSE" and message.xid in self.waiting_xids:
      self.waiting_xids.discard(message.xid)
      self.received_responses[message.xid] = message
      return

    if key not in self.handlers:
      raise ValueError("%s: No message handler for: %s\nKnown handlers are: %s" % (type(self).__name__, str(key), ", ".join(map(lambda h: str(h), self.handlers))))
    # dispatch message
    self.handlers[key](message)

  def sync_request(self, messageClass, name):
    message = self.message_with_xid(SyncMessage(type="REQUEST", messageClass=messageClass, name=name))
    self.waiting_xids.add(message.xid)
    self.send(message)

    while not message.xid in self.received_responses:
      self.io.wait_for_message()

    response = self.received_responses.pop(message.xid)
    return response.value
