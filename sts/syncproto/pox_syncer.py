import logging
import time
import os
import socket
import threading
import traceback

from pox.core import core
from pox.lib.ioworker.io_worker import JSONIOWorker
from pox.lib.graph.nom import Switch, Host, Link
from pox.lib.graph.util import NOMEncoder

from sts.util.io_master import IOMaster
from sts.syncproto.base import SyncTime, SyncMessage, SyncProtocolSpeaker, SyncIODelegate
from pox.lib.util import parse_openflow_uri
from pox.lib.recoco import Task, Select

log = logging.getLogger("pox_syncer")

# POX Module launch method
def launch():
  if "sts_sync" in os.environ:

    sts_sync = os.environ["sts_sync"]
    log.info("starting sts sync for spec: %s" % sts_sync)

    io_master = POXIOMaster()
    io_master.start(core.scheduler)

    sync_master = POXSyncMaster(io_master)
    sync_master.start(sts_sync)
  else:
    log.info("no sts_sync variable found in environment. Not starting pox_syncer")

class POXIOMaster(IOMaster, Task):
  """ horrible clutch of a hack that is both a regular select loop and a POX task
      yielding select (so it can be run by the recoco scheduler) """

  _select_timeout = 5

  def __init__(self):
    IOMaster.__init__(self)
    Task.__init__(self)

  def run(self):
    while True:
      read_sockets, write_sockets, exception_sockets = self.grab_workers_rwe()
      rlist, wlist, elist = yield Select(read_sockets, write_sockets, exception_sockets, self._select_timeout)
      self.handle_workers_rwe(rlist, wlist, elist)

class POXSyncMaster(object):
  def __init__(self, io_master):
    self.io_master = io_master
    self._in_get_time = False

  def start(self, sync_uri):
    self.connection = POXSyncConnection(self.io_master, sync_uri)
    self.connection.listen()
    self.connection.wait_for_connect()
    self.patch_functions()

  def patch_functions(self):
    if hasattr(time, "_orig_time"):
      raise RuntimeError("Already patched")
    time._orig_time = time.time
    time.time = self.get_time

  def get_time(self):
    """ Hack alert: python logging use time.time(). That means that log statements in the determinism
        protocols are going to invoke get_time again. Solve by returning the real time if we (get_time)
        are in the stacktrace """

    if self._in_get_time:
      return time._orig_time()

    try:
      self._in_get_time = True
      time_array = self.connection.request("DeterministicValue", "gettimeofday")
      sync_time =  SyncTime(*time_array)
      return sync_time.as_float()
    finally:
      self._in_get_time = False

class POXSyncConnection(object):
  def __init__(self, io_master, sync_uri):
    (self.mode, self.host, self.port) = parse_openflow_uri(sync_uri)
    self.io_master = io_master
    self.speaker = None

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
    self.speaker = POXSyncProtocolSpeaker(SyncIODelegate(self.io_master, socket))

  def request(self, messageClass, name):
    if self.speaker:
      return self.speaker.sync_request(messageClass=messageClass, name=name)
    else:
      log.warn("POXSyncConnection: not connected. cannot handle requests")

class POXSyncProtocolSpeaker(SyncProtocolSpeaker):
  def __init__(self, io_delegate=None):
    self.snapshotter = POXNomSnapshotter()

    handlers = {
      ("REQUEST", "NOMSnapshot"): self._get_nom_snapshot
    }
    SyncProtocolSpeaker.__init__(self, handlers, io_delegate)

  def _get_nom_snapshot(self, message):
    snapshot = self.snapshotter.get_snapshot()
    response = SyncMessage(type="RESPONSE", messageClass="NOMSnapshot", time=SyncTime.now(), xid = message.xid, value=snapshot)
    self.send(response)


class POXNomSnapshotter(object):
  def __init__(self):
    self.encoder = NOMEncoder()

  def get_snapshot(self):
    nom = {"switches":[], "hosts":[], "links":[]}
    for s in core.topology.getEntitiesOfType(Switch):
      nom["switches"].append(self.encoder.encode(s))
    for h in core.topology.getEntitiesOfType(Host):
      nom["hosts"].append(self.myencoder.encode(h))
    for l in core.topology.getEntitiesOfType(Link):
      nom["links"].append(self.myencoder.encode(l))
    return nom


