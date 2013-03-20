# Copyright 2011-2013 Colin Scott
# Copyright 2011-2013 Andreas Wundsam
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

# Base class for all (python) controller-specific syncer modules, as well as
# the STS syncer. (Runs in both the STS process and the controller
# process(es))

import collections
import itertools
import logging
import time
import socket

# TODO(cs): specific to POX!
from pox.lib.ioworker.io_worker import JSONIOWorker

log = logging.getLogger("sync_connection")
def unpatched_time():
  if hasattr(time, "_orig_time"):
    return time._orig_time()
  else:
    return time.time()


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
    if type not in ("ASYNC", "SYNC", "ACK", "REQUEST", "RESPONSE"):
      raise ValueError("SyncMessage: type must one of (ASYNC, SYNC, ACK, REQUEST, RESPONSE)")

    if (type == "RESPONSE" or type == "ACK") and xid is None:
      raise ValueError("SyncMessage: xid must be given for messages of type %s" % type)

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

  def wait_for_message(self, timeout=None):
    self.io_master.select(timeout)

  def send(self, msg):
    self.io_worker.send(msg)

  def get_on_message_received(self):
    return self.io_worker.on_json_received

  def set_on_message_received(self, f):
    self.io_worker.on_json_received = lambda io_worker, msg: f(msg)

  on_message_received = property(get_on_message_received, set_on_message_received)

class SyncProtocolSpeaker(object):
  """ speaks the sts sync protocol """
  def __init__(self, handlers, io_delegate, collect_stats=True):
    self.xid_generator = itertools.count(1)
    self.io = io_delegate
    #self.sent_xids = set()
    self.listener = SyncProtocolListener(handlers, io_delegate,
                                         collect_stats=collect_stats)

  def message_with_xid(self, message):
    if message.xid:
      return message
    else:
      return message._replace(xid=self.xid_generator.next())

  def send(self, message):
    ''' Send a message you don't expect a response from '''
    message = self.message_with_xid(message)
    #if((message.type, message.xid) in self.sent_xids):
    #  raise RuntimeError("Error sending message %s: XID %d already sent" % (str(message), message.xid))
    #self.sent_xids.add( (message.type, message.xid) )
    self.io.send(message._asdict())

    return message

  def async_notification(self, messageClass, fingerPrint, value):
    # Don't really need an xid..
    message = self.message_with_xid(SyncMessage(type="ASYNC",
                                    messageClass=messageClass,
                                    fingerPrint=fingerPrint,
                                    value=value))
    self.send(message)

  def sync_notification(self, messageClass, fingerPrint, value):
    message = self.message_with_xid(SyncMessage(type="SYNC",
                                    messageClass=messageClass,
                                    fingerPrint=fingerPrint,
                                    value=value))
    self.send(message)
    return self.listener.wait_for_xaction(message)

  def ack_sync_notification(self, messageClass, xid):
    message = SyncMessage(type="ACK", messageClass=messageClass, xid=xid)
    self.send(message)

  def sync_request(self, messageClass, name, timeout=None):
    ''' Send a message you expect a response from.
    Note: Blocks this thread until a response is recieved!'''
    message = self.message_with_xid(SyncMessage(type="REQUEST", messageClass=messageClass, name=name))
    self.send(message)
    return self.listener.wait_for_xaction(message, timeout)

class SyncProtocolListener(object):
  ''' Speaker delegates to this class to wait on messages '''
  def __init__(self, handlers, io_delegate, collect_stats=True,
               delay_threshold_ms=3.0):
    self.handlers = handlers
    self.collect_stats = collect_stats
    self.delay_threshold_ms = delay_threshold_ms
    self.waiting_xids = {}
    self.received_responses = {}
    self.io = io_delegate
    self.io.on_message_received = self.on_message_received

  def on_message_received(self, msg_hash):
    message = SyncMessage(**msg_hash)
    key = (message.type, message.messageClass)

    if (message.type == "RESPONSE" or message.type == "ACK") and message.xid in self.waiting_xids:
      del self.waiting_xids[message.xid]
      self.received_responses[message.xid] = message
      return

    if key not in self.handlers:
      raise ValueError("%s: No message handler for: %s\nKnown handlers are: %s" % (type(self).__name__, str(key), ", ".join(map(lambda h: str(h), self.handlers))))
    # dispatch message
    self.handlers[key](message)

  def wait_for_xaction(self, message, timeout=None):
    xid = message.xid
    self.waiting_xids[xid] = message

    start = unpatched_time()

    # Blocks this thread!
    while not xid in self.received_responses:
      if timeout:
        now = unpatched_time()
        if now - start > timeout:
          raise socket.timeout()
        to_wait = timeout - (now-start)
      else:
        to_wait = None

      self.io.wait_for_message(to_wait)

    if self.collect_stats:
      end = unpatched_time()
      ms_elapsed = (end - start) * 1000
      if ms_elapsed > self.delay_threshold_ms:
        if hasattr(log, "_orig_log"):
          log._orig_log(logging.DEBUG, "Spent %.02f milliseconds waiting on %s" %
                      (ms_elapsed, str(message)), [])
        else:
          log._log(logging.DEBUG, "Spent %.02f milliseconds waiting on %s" %
                      (ms_elapsed, str(message)), [])

    response = self.received_responses.pop(xid)
    return response.value

