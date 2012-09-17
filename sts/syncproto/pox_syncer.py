import logging
import time
import os
import socket

from pox.lib.ioworker.io_worker import JSONIOWorker

from sts.io_master import IOMaster
from sts.syncproto.base import SyncTime, SyncMessage, SyncProtocolSpeaker
from pox.lib.util import parse_openflow_uri

log = logging.getLogger("pox_syncer")

# POX Module launch method
def launch():
  if "sts_sync" in os.environ:
    sts_sync = os.environ["sts_sync"]
    log.info("starting sts sync for spec: %s" % sts_sync)
    sync_master = POXSyncMaster()
    sync_master.start(sts_sync)
  else:
    log.info("no sts_sync variable found in environment. Not starting pox_syncer")

class POXSyncMaster(object):
  def __init__(self):
    self.io_master = IOMaster()

  def start(self, sync_uri):
    self.connection = POXSyncConnection(self.io_master, sync_uri)
    self.connection.listen()
    self.connection.wait_for_connect()
    self.patch_functions()


  def patch_functions(self):
    time._orig_time = time.time
    time.time = self.get_time

  def get_time(self):
    return SyncTime(*self.connection.request("DeterministicValue", "gettimeofday")).as_float()

class POXSyncConnection(object):
  def __init__(self, io_master, sync_uri):
    (self.mode, self.host, self.port) = parse_openflow_uri(sync_uri)
    self.speaker = POXSyncProtocolSpeaker()
    self.io_master = io_master

  def listen(self):
    if self.mode != "ptcp":
      raise RuntimeError("only ptcp (passive) mode supported for now")
    listen_socket = socket.socket()
    listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    host = self.host if self.host else "0.0.0.0"
    listen_socket.bind( (self.host, self.port) )
    listen_socket.listen(1)
    self.listen_socket = listen_socket

  def wait_for_connect(self):
    log.info("waiting for sts_sync connection on %s:%d" % (self.host, self.port))
    (socket, addr) = self.listen_socket.accept()
    self.io_worker = JSONIOWorker(self.io_master.create_worker_for_socket(socket))
    self.speaker.set_io_worker(self.io_worker)

  def request(self, messageClass, name):
    message = self.speaker.send(SyncMessage(type="REQUEST", messageClass=messageClass, name=name))

    while not self.speaker.has_response(message.xid):
      self.io_master.select(0.2)

    response = self.speaker.retrieve_response(message.xid)
    return response.value

class POXSyncProtocolSpeaker(SyncProtocolSpeaker):
  def __init__(self, json_io_worker=None):
    self.received_responses = {}

    handlers = {
      ("RESPONSE", "DeterministicValue"): self._set_deterministic_value
    }
    SyncProtocolSpeaker.__init__(self, handlers, json_io_worker)

  def _set_deterministic_value(self, message):
    self.received_responses[message.xid] = message

  def has_response(self, xid):
    return xid in self.received_responses

  def retrieve_response(self, xid):
    return self.received_responses.pop(xid)

