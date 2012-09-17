import collections
import itertools
import json
import logging
import time

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

class SyncProtocolSpeaker(object):
  """ speaks the sts sync protocol """
  def __init__(self, handlers, json_io_worker=None):
    self.xid_generator = itertools.count(1)
    self.handlers = handlers
    self.set_io_worker(json_io_worker)

  def get_io_worker(self):
    return self._io_worker

  def set_io_worker(self, json_io_worker):
    self._io_worker = json_io_worker
    if(self._io_worker):
      self._io_worker.on_json_received = self.on_json_received

  io_worker = property(get_io_worker, set_io_worker)

  def send(self, message):
    if message.xid is None:
      message = message._replace(xid=self.xid_generator.next())

    if(self._io_worker):
      self._io_worker.send(message._asdict())

    return message

  def on_json_received(self, worker, json_hash):
    message = SyncMessage(**json_hash)
    key = (message.type, message.messageClass)
    if key not in self.handlers:
      raise ValueError("Unknown message class: %s" % message.messageClass)
    # dispatch message
    self.handlers[key](message)


