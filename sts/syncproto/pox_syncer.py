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

# This  module runs inside a POX process. It's loaded into pox/ext before
# booting POX.

import logging
import time
import os
import socket

from pox.core import core, UpEvent
from pox.lib.graph.nom import Switch, Host, Link
from pox.lib.graph.util import NOMEncoder

from sts.util.io_master import IOMaster
from sts.syncproto.base import SyncTime, SyncMessage, SyncProtocolSpeaker, SyncIODelegate
from pox.lib.util import parse_openflow_uri
from pox.lib.recoco import Task, Select

from logging import Logger

log = logging.getLogger("pox_syncer")

# POX Module launch method
def launch(interpose_on_logging=True, blocking=False):
  interpose_on_logging = str(interpose_on_logging).lower() == "true"
  blocking = str(blocking).lower() == "true"
  if "sts_sync" in os.environ:
    sts_sync = os.environ["sts_sync"]
    log.info("starting sts sync for spec: %s" % sts_sync)

    io_master = POXIOMaster()
    io_master.start(core.scheduler)

    sync_master = POXSyncMaster(io_master,
                                interpose_on_logging=interpose_on_logging,
                                blocking=blocking)
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
  def __init__(self, io_master, interpose_on_logging=True, blocking=True):
    self._in_get_time = False
    self.io_master = io_master
    self.interpose_on_logging = interpose_on_logging
    self.blocking = blocking
    self.core_up = False
    core.addListener(UpEvent, self.handle_UpEvent)

  def handle_UpEvent(self, _):
    self.core_up = True

  def start(self, sync_uri):
    self.connection = POXSyncConnection(self.io_master, sync_uri)
    self.connection.listen()
    self.connection.wait_for_connect()
    self.patch_functions()

  def patch_functions(self):
    # Patch time.time()
    if hasattr(time, "_orig_time"):
      raise RuntimeError("Already patched")
    time._orig_time = time.time
    time.time = self.get_time

    if self.interpose_on_logging:
      # Patch Logger.* for state changes
      # All logging.Logger log methods go through a private method _log
      Logger._orig_log = Logger._log
      def new_log(log_self, level, msg, *args, **kwargs):
        Logger._orig_log(log_self, level, msg, *args, **kwargs)
        if self.blocking and self.core_up:
          print "Waiting on ACK.."
        self.state_change(msg, *args)
      Logger._log = new_log

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

  def state_change(self, msg, *args):
    ''' Notify sts that we're about to make a state change (log msg) '''
    args = [ str(s) for s in args ]
    if self.blocking and self.core_up:
      self.connection.sync_notification("StateChange", msg, args)
      print "ACK received.."
    else:
      self.connection.async_notification("StateChange", msg, args)

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
    listen_socket.bind( (host, self.port) )
    listen_socket.listen(1)
    self.listen_socket = listen_socket

  def wait_for_connect(self):
    log.info("waiting for sts_sync connection on %s:%d" % (self.host, self.port))
    (socket, _) = self.listen_socket.accept()
    log.info("sts_sync connected")
    self.speaker = POXSyncProtocolSpeaker(SyncIODelegate(self.io_master, socket))

  def request(self, messageClass, name):
    if self.speaker:
      return self.speaker.sync_request(messageClass=messageClass, name=name)
    else:
      log.warn("POXSyncConnection: not connected. cannot handle requests")

  def async_notification(self, messageClass, fingerPrint, value):
    if self.speaker:
      self.speaker.async_notification(messageClass, fingerPrint, value)
    else:
      log.warn("POXSyncConnection: not connected. cannot handle requests")

  def sync_notification(self, messageClass, fingerPrint, value):
    if self.speaker:
      self.speaker.sync_notification(messageClass, fingerPrint, value)
    else:
      log.warn("POXSyncConnection: not connected. cannot handle requests")

class POXSyncProtocolSpeaker(SyncProtocolSpeaker):
  def __init__(self, io_delegate=None):
    self.snapshotter = POXNomSnapshotter()

    handlers = {
      ("REQUEST", "NOMSnapshot"): self._get_nom_snapshot,
      ("ASYNC", "LinkDiscovery"): self._link_discovery
    }
    SyncProtocolSpeaker.__init__(self, handlers, io_delegate)

  def _get_nom_snapshot(self, message):
    snapshot = self.snapshotter.get_snapshot()
    response = SyncMessage(type="RESPONSE", messageClass="NOMSnapshot", time=SyncTime.now(), xid = message.xid, value=snapshot)
    self.send(response)

  def _link_discovery(self, message):
    link = message.value
    core.openflow_discovery.install_link(link[0], link[1], link[2], link[3])

class POXNomSnapshotter(object):
  def __init__(self):
    self.encoder = NOMEncoder()

  def get_snapshot(self):
    nom = {"switches":[], "hosts":[], "links":[]}
    for s in core.topology.getEntitiesOfType(Switch):
      nom["switches"].append(self.encoder.encode(s))
    for h in core.topology.getEntitiesOfType(Host):
      nom["hosts"].append(self.encoder.encode(h))
    for l in core.topology.getEntitiesOfType(Link):
      nom["links"].append(self.encoder.encode(l))
    return nom


