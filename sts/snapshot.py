# Copyright 2011-2013 Colin Scott
# Copyright 2011-2013 Andreas Wundsam
# Copyright 2012-2013 Sam Whitlock
# Copyright 2012-2012 Kyriakos Zarifis
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

import urllib2
import logging
import json
import string
import time
from pox.lib.graph.util import NOMDecoder
from pox.openflow.topology import OpenFlowSwitch
from pox.openflow.flow_table import FlowTable, TableEntry
from pox.openflow.libopenflow_01 import ofp_match, ofp_action_output
from sts.entities import POXController, BigSwitchController

log = logging.getLogger("Snapshot")

class Snapshot(object):
  """
  A Snapshot object is a description of the controllers' view of the network in terms that are meaningful
  to the debugger. Any snaphsot grabbed from any controller should be transformed
  into a Snapshot object in order to be fed to HSA
  """
  def __int__(self):
    self.time = None
    self.switches = []
    # The debugger doesn't use the next two (for now anyway)
    self.hosts = []
    self.links = []

  def __repr__(self):
    return "<Snapshot object: (%i switches)>"%len(self.switches)

class SnapshotService(object):
  """
  Controller-specific SnapshotServices take care of grabbing a snapshot from
  their controller in whatever format the controller exports it, and translating
  it into a Snaphot object that is meaningful to the debbuger
  """
  def __init__(self):
    self.snapshot = Snapshot()

  def fetchSnapshot(self, controller):
    pass

class FlexibleNOMDecoder:
  def __init__(self):
    self.pox_nom_decoder = NOMDecoder()

  def decode(self, json):
    if isinstance(json, (str, unicode)) and string.find(json, "__module__")>=0:
      return self.pox_nom_decoder.decode(json)
    else:
      return self.decode_switch(json)

  def decode_switch(self, json):
    flow_table = self.decode_flow_table(json["flow_table"] if "flow_table" in json else json["flowTable"])
    switch = OpenFlowSwitch(json["dpid"], flow_table=flow_table)
    return switch

  def decode_flow_table(self, json):
    ft = FlowTable()
    for e in json["entries"]:
      ft.add_entry(self.decode_entry(e))
    return ft

  def decode_entry(self, json):
    e = TableEntry()
    for (k, v) in json.iteritems():
      if k == "match":
        e.match = self.decode_match(v)
      elif k == "actions":
        e.actions = [ self.decode_action(a) for a in v ]
      else:
        setattr(e, k, v)
    return e

  def decode_match(self, json):
    return ofp_match(**json)

  def decode_action(self, json):
    a = ofp_action_output(port = json['port'])
    return a

class SyncProtoSnapshotService(SnapshotService):
  def __init__(self):
    SnapshotService.__init__(self)
    self.myNOMDecoder = FlexibleNOMDecoder()

  def fetchSnapshot(self, controller):
    jsonNOM = controller.sync_connection.get_nom_snapshot()

    # Update local Snapshot object
    self.snapshot.switches = [self.myNOMDecoder.decode(s) for s in jsonNOM["switches"]]
    self.snapshot.hosts = [self.myNOMDecoder.decode(h) for h in jsonNOM["hosts"]]
    self.snapshot.links = [self.myNOMDecoder.decode(l) for l in jsonNOM["links"]]
    self.snapshot.time = time.time()

    return self.snapshot

class PoxSnapshotService(SnapshotService):
  def __init__(self):
    SnapshotService.__init__(self)
    self.port = 7790
    self.myNOMDecoder = NOMDecoder()

  def fetchSnapshot(self, controller):
    from pox.lib.util import connect_socket_with_backoff
    import socket
    snapshotSocket = connect_socket_with_backoff('127.0.0.1', self.port)
    log.debug("Sending Request")
    snapshotSocket.send("{\"hello\":\"nommessenger\"}")
    snapshotSocket.send("{\"getnom\":0}", socket.MSG_WAITALL)
    log.debug("Receiving Results")
    jsonstr = ""
    while True:
      data = snapshotSocket.recv(1024)
      log.debug("%d byte packet received" % len(data))
      if not data: break
      jsonstr += data
      if len(data) != 1024: break
    snapshotSocket.close()

    jsonNOM = json.loads(jsonstr) # (json string with the NOM)

    # Update local Snapshot object
    self.snapshot.switches = [self.myNOMDecoder.decode(s) for s in jsonNOM["switches"]]
    self.snapshot.hosts = [self.myNOMDecoder.decode(h) for h in jsonNOM["hosts"]]
    self.snapshot.links = [self.myNOMDecoder.decode(l) for l in jsonNOM["links"]]
    self.snapshot.time = time.time()

    return self.snapshot

class BigSwitchSnapshotService(SnapshotService):
  def __init__(self):
    SnapshotService.__init__(self)

  def fetchSnapshot(self, controller):
    req = urllib2.Request('http://localhost:8080/wm/core/proact')
    response = urllib2.urlopen(req)
    json_data = response.read()
    l = json.loads(json_data)
    res = []
    for m in l:
      res.append(Snapshot.from_json_map(m))
    return res

    # Create local Snapshot object
    snapshot = Snapshot()
    self.snapshot = snapshot
    return self.snapshot

def get_snapshotservice(controller_configs):
  '''Return a SnapshotService object determined by the name of the first
  controller in the controller_configs.

  For now, we only support a homogenous controller environment.'''
  # Read from config what controller we are using
  # TODO(cs): allow for heterogenous controllers?
  if controller_configs != [] and controller_configs[0].sync:
    snapshotService = SyncProtoSnapshotService()
  elif controller_configs != [] and controller_configs[0].controller_class == POXController:
    snapshotService = PoxSnapshotService()
  elif controller_configs != [] and controller_configs[0].controller_class == BigSwitchController:
    snapshotService = BigSwitchSnapshotService()
  else:
    # We default snapshotService to POX
    snapshotService = PoxSnapshotService()
  return snapshotService
