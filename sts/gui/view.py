# Copyright 2011-2013 Colin Scott
# Copyright 2012-2013 Andrew Or
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

'''
Graphical representation of STS topology switch, host and link entities
'''
from sts.entities import Host as STSHost, HostInterface as STSHostInterface, \
                         FuzzSoftwareSwitch as STSSwitch, AccessLink as STSAccessLink, \
                         Link as STSNetworkLink
from sts.gui.entities import GuiNode, GuiHost, GuiSwitch, GuiLink
from pox.lib.addresses import IPAddr, EthAddr
from pox.openflow.libopenflow_01 import ofp_phy_port

import os
import logging
import math
import json
from random import randint
from threading import Timer
from PyQt4 import QtGui, QtCore

log = logging.getLogger("sts.gui")

class TopologyView(QtGui.QGraphicsView):
  '''
  QGraphicsView that provides a graphical representation of STS topology
  '''
  def __init__(self, sts_topology, parent=None, sync_period=2.0, debugging=False):
    QtGui.QGraphicsView.__init__(self, parent)
    self.topology_scene = QtGui.QGraphicsScene(self)
    self.topology_scene.setItemIndexMethod(QtGui.QGraphicsScene.NoIndex)
    self.topology_scene.setSceneRect(-300, -300, 600, 600)
    self.setScene(self.topology_scene)
    self.setRenderHint(QtGui.QPainter.Antialiasing)
    self.setStyleSheet("background: black")
    self.scale(0.9, 0.9)
    self.setMinimumSize(400, 400)

    # Node boundaries
    self.minX, self.maxX = -300, 300
    self.minY, self.maxY = -200, 200

    # Cursor
    self.setDragMode(self.ScrollHandDrag)
    self.setCursor(QtCore.Qt.ArrowCursor)

    # Syncer updates topology scene to contain entities matching those in STS
    self.syncer = STSSyncer(sts_topology, self, sync_period, debugging)

  def mouseReleaseEvent(self, event):
    ''' Show context menu when right-clicking on empty space on the scene. '''
    if not self.itemAt(event.pos()):
      if event.button() == QtCore.Qt.RightButton:
        popup = QtGui.QMenu()
        popup.addAction("Turn %s Debug Messages" % ("Off" if self.syncer.debugging else "On"),
                        self.syncer.toggle_debug_messages)
        popup.addAction("Load State", self.syncer.load_state)
        popup.addAction("Save State", self.syncer.save_state)
        popup.addAction("Create Switch", self.syncer.create_switch)
        popup.exec_(event.globalPos())
    QtGui.QGraphicsView.mouseReleaseEvent(self, event)

class STSSyncer:
  '''
  Container of Node and Link objects in GUI that periodically syncs with STS Topology
  '''
  def __init__(self, sts_topology, topology_view, sync_period=2.0, debugging=True):
    self.dpid2switch = {}
    self.hid2host = {}
    self.access_links = []
    self.network_links = []
    self.sts_topology = sts_topology
    self.topology_view = topology_view
    self.topology_scene = topology_view.topology_scene
    self.debugging = debugging

    # Sync with STS topology
    self.sts_topology = sts_topology
    self.sync_period = sync_period
    self.mismatch_count = 0
    self.sync_with_sts()

  @property
  def switches(self):
    return self.dpid2switch.values()

  @property
  def hosts(self):
    return self.hid2host.values()

  @property
  def dpids(self):
    return self.dpid2switch.keys()

  @property
  def hids(self):
    return self.hid2host.keys()

  @property
  def links(self):
    return self.access_links + self.network_links

  def debug(self, msg):
    if self.debugging:
      print "sts.gui:%s" % msg
      #TODO: Change back to log.debug(msg)

  def toggle_debug_messages(self):
    self.debugging = not self.debugging

  def synced_with_sts(self):
    ''' Return True if GUI and STS share the same map of nodes and links '''
    self.debug("\n================== GUI Sync Check ==================" +
               "\n\tSwitches: \tSTS = %s, Gui = %s" %
                    (len(self.sts_topology.switches), len(self.switches)) +
               "\n\tHosts:    \tSTS = %s, Gui = %s" %
                    (len(self.sts_topology.hosts), len(self.hosts)) +
               "\n\tAccess Link: \tSTS = %s, Gui = %s" %
                    (len(self.sts_topology.access_links), len(self.access_links)) +
               "\n\tNetwork Link: \tSTS = %s, Gui = %s" %
                    (len(self.sts_topology.network_links), len(self.network_links)) +
               "\n====================================================\n")

    if len(self.switches) != len(self.sts_topology.switches) or\
       len(self.hosts) != len(self.sts_topology.hosts) or\
       len(self.access_links) != len(self.sts_topology.access_links) or\
       len(self.network_links) != len(self.sts_topology.network_links):
      return False
    for hid in self.sts_topology.hid2host.keys():
      if hid not in self.hids:
        return False
    for dpid in self.sts_topology.dpid2switch.keys():
      if dpid not in self.dpids:
        return False
    for hid in self.hids:
      if hid not in self.sts_topology.hid2host.keys():
        return False
    for dpid in self.dpids:
      if dpid not in self.sts_topology.dpid2switch.keys():
        return False
    return True

  def sync_with_sts(self):
    ''' Resync all network elements if STS and GUI are persistently desynchronized '''
    if self.sts_topology is None or self.synced_with_sts():
      Timer(self.sync_period, self.sync_with_sts).start()
      self.mismatch_count = 0
      return

    self.mismatch_count += 1

    # If inconsistency between STS and GUI is persistent, resync
    if self.mismatch_count >= 2:
      self.mismatch_count = 0
      
      # Remove all links in GUI
      for link in self.links:
        link.source.linkList.remove(link)
        link.dest.linkList.remove(link)
        if link in self.topology_scene.items():
          self.topology_scene.removeItem(link)
      self.access_links = []
      self.network_links = []

      # Remove switches found in GUI but not STS
      for dpid, switch in self.dpid2switch.items():
        if dpid not in self.sts_topology.dpid2switch.keys():
          if switch in self.topology_scene.items():
            self.topology_scene.removeItem(switch)
          del self.dpid2switch[dpid]
          self.debug("--- Removing switch with dpid = %d" % dpid)

      # Remove hosts found in GUI but not STS
      for hid, host in self.hid2host.items():
        if hid not in self.sts_topology.hid2host.keys():
          if host in self.topology_scene.items():
            self.topology_scene.removeItem(host)
          del self.hid2host[hid]
          self.debug("--- Removing host with hid = %d" % hid)

      # Add switches found in STS but not in GUI
      for dpid in self.sts_topology.dpid2switch.keys():
        self.add_switch(dpid)
        self.debug("--- Adding new switch with dpid = %d" % dpid)

      # Add hosts found in STS but not in GUI
      for hid in self.sts_topology.hid2host.keys():
        self.add_host(hid)
        self.debug("--- Adding new host with dpid = %d!" % hid)

      # Reconnect all access links
      for access_link in self.sts_topology.access_links:
        sts_host = access_link.host
        sts_switch = access_link.switch
        self.add_access_link(sts_host.hid, sts_switch.dpid)
        self.debug("--- Adding new access link connecting Host %d <--> Switch %d!"
                   % (sts_host.hid, sts_switch.dpid))

      # Reconnect all network links
      for network_link in self.sts_topology.network_links:
        sts_from_switch = network_link.start_software_switch
        sts_to_switch = network_link.end_software_switch
        self.add_network_link(sts_from_switch.dpid, sts_to_switch.dpid)
        self.debug("--- Adding new network link connecting Switch %d --> Switch %d!"
                   % (sts_from_switch.dpid, sts_to_switch.dpid))
    Timer(self.sync_period, self.sync_with_sts).start()

  def reset(self):
    ''' Reset GUI topology '''
    for item in self.hosts + self.switches + self.links:
      if item in self.topology_scene.items():
        self.topology_scene.removeItem(item)
    self.hid2host = {}
    self.dpid2switch = {}
    self.access_links = []
    self.network_links = []

  def add_host(self, hid, position=None):
    ''' Add and register a host in GUI with the given hid and position '''
    if hid is None or hid in self.hids:
      return
    host = GuiHost(self.topology_view, hid)
    self.hid2host[hid] = host
    self.topology_scene.addItem(host)
    if position is None:
      position = (randint(self.topology_view.minX, self.topology_view.maxX),
                  randint(self.topology_view.minY, self.topology_view.maxY))
    host.setPos(position[0], position[1])

  def add_switch(self, dpid, position=None):
    ''' Add and register a switch in GUI with the given dpid and position '''
    if dpid is None or dpid in self.dpids:
      return    
    switch = GuiSwitch(self.topology_view, dpid)
    self.dpid2switch[dpid] = switch
    self.topology_scene.addItem(switch)
    if position is None:
      position = (randint(self.topology_view.minX, self.topology_view.maxX),
                  randint(self.topology_view.minY, self.topology_view.maxY))
    switch.setPos(position[0], position[1])

  def add_access_link(self, hid, dpid):
    ''' Add and register an access link in GUI '''
    if hid is None or\
       dpid is None or\
       hid not in self.hids or\
       dpid not in self.dpids:
      return
    link = GuiLink(self.topology_view, self.hid2host[hid], self.dpid2switch[dpid])
    self.access_links.append(link)
    self.topology_scene.addItem(link)

  def add_network_link(self, from_dpid, to_dpid):
    ''' Add and register a unidirectional network link in GUI '''
    if from_dpid is None or\
       to_dpid is None or\
       from_dpid not in self.dpids or\
       to_dpid not in self.dpids:
      return
    link = GuiLink(self.topology_view, self.dpid2switch[from_dpid], self.dpid2switch[to_dpid])
    self.network_links.append(link)
    self.topology_scene.addItem(link)

  def get_sts_host(self, gui_host):
    ''' Given a host in GUI, return the corresponding host in STS by hid '''
    if gui_host.id in self.sts_topology.hid2host.keys():
      return self.sts_topology.hid2host[gui_host.id]
    return None

  def get_sts_switch(self, gui_switch):
    ''' Given a switch in GUI, return the corresponding switch in STS by dpid '''
    if gui_switch.id in self.sts_topology.dpid2switch.keys():
      return self.sts_topology.dpid2switch[gui_switch.id]
    return None

  def create_switch(self, dpid=None):
    ''' Create a switch with the given dpid in both STS and GUI '''
    if dpid is None:
      dpid = max(self.dpid2switch.keys()) + 1
    num_ports = 2
    switch = self.sts_topology.create_switch(dpid, num_ports)
    self.add_switch(dpid)

  def remove_switch(self, dpid):
    '''
    Remove a switch in both STS and GUI, along with all associated links and any
    dangling hosts previously attached
    '''
    if dpid is None or dpid not in self.dpids:
      return
    gui_switch = self.dpid2switch[dpid]
    sts_switch = self.sts_topology.dpid2switch[dpid]
    self.sts_topology.remove_switch(sts_switch)
    # Remove associated network links in GUI
    network_links_to_remove = []
    for network_link in self.network_links:
      if network_link.source is gui_switch or\
         network_link.dest is gui_switch:
        network_links_to_remove.append(network_link)
    for network_link in network_links_to_remove:
      network_link.source.linkList.remove(network_link)
      network_link.dest.linkList.remove(network_link)
      if network_link in self.topology_scene.items():
        self.topology_scene.removeItem(network_link)
      self.network_links.remove(network_link)
    # Remove associated access links in GUI
    access_links_to_remove = []
    for access_link in self.access_links:
      if access_link.dest is gui_switch:
        access_links_to_remove.append(access_link)
    for access_link in access_links_to_remove:
      gui_host = access_link.source
      gui_host.linkList.remove(access_link)
      if access_link in self.topology_scene.items():
        self.topology_scene.removeItem(access_link)
      self.access_links.remove(access_link)
      # Remove dangling hosts in GUI, if any
      if len(gui_host.linkList) == 0:
        if gui_host in self.topology_scene.items():
          self.topology_scene.removeItem(gui_host)
        del self.hid2host[gui_host.id]
    # Remove switch in GUI
    if gui_switch in self.topology_scene.items():
      self.topology_scene.removeItem(gui_switch)
    del self.dpid2switch[dpid]
    
  def attach_host_to_switch(self, dpid):
    ''' Create a host and attach it to the switch with the given dpid in both STS and GUI '''
    if dpid is None or dpid not in self.dpids:
      return
    sts_switch = self.sts_topology.dpid2switch[dpid]
    sts_host = self.sts_topology.create_host(sts_switch, get_switch_port=
             lambda switch: self.sts_topology.link_tracker.find_unused_port(switch))
    hid = sts_host.hid
    # Situate the new host near the switch
    gui_switch = self.dpid2switch[dpid]
    host_x = randint(int(gui_switch.x())-100, int(gui_switch.x())+100)
    host_y = randint(int(gui_switch.y())-100, int(gui_switch.y())+100)
    if host_x < self.topology_view.minX:
      host_x = self.topology_view.minX
    if host_x > self.topology_view.maxX:
      host_x = self.topology_view.maxX
    if host_y < self.topology_view.minY:
      host_y = self.topology_view.minY
    if host_y > self.topology_view.maxY:
      host_y = self.topology_view.maxY
    self.add_host(hid, (host_x, host_y))
    self.add_access_link(hid, dpid)

  def remove_host(self, hid):
    ''' Remove a host and all associated access links in both STS and GUI '''
    if hid is None or hid not in self.hids:
      return
    gui_host = self.hid2host[hid]
    sts_host = self.sts_topology.hid2host[hid]
    self.sts_topology.remove_host(sts_host)
    # Remove access links in GUI
    for access_link in self.access_links:
      if access_link.source is gui_host:
        access_link.dest.linkList.remove(access_link)
        if access_link in self.topology_scene.items():
          self.topology_scene.removeItem(access_link)
        self.access_links.remove(access_link)
    # Remove host in GUI
    if gui_host in self.topology_scene.items():
      self.topology_scene.removeItem(gui_host)
    del self.hid2host[hid]

  def create_network_link(self, from_dpid, to_dpid):
    ''' Create a unidirectional network link in both STS and GUI '''
    if from_dpid is None or\
       to_dpid is None or\
       from_dpid not in self.dpids or\
       to_dpid not in self.dpids:
      return
    sts_from_switch = self.sts_topology.dpid2switch[from_dpid]
    sts_to_switch = self.sts_topology.dpid2switch[to_dpid]
    self.sts_topology.create_network_link(sts_from_switch, None, sts_to_switch, None)
    self.add_network_link(from_dpid, to_dpid)

  def remove_network_link(self, from_dpid, to_dpid):
    ''' Remove a unidirectional network link in both STS and GUI '''
    if from_dpid is None or\
       to_dpid is None or\
       from_dpid not in self.dpids or\
       to_dpid not in self.dpids:
      return
    sts_from_switch = self.sts_topology.dpid2switch[from_dpid]
    sts_to_switch = self.sts_topology.dpid2switch[to_dpid]
    self.sts_topology.remove_network_link(sts_from_switch, sts_to_switch)
    gui_from_switch = self.dpid2switch[from_dpid]
    gui_to_switch = self.dpid2switch[to_dpid]
    for link in self.network_links:
      if link.source is gui_from_switch and link.dest is gui_to_switch:
        gui_from_switch.linkList.remove(link)
        gui_to_switch.linkList.remove(link)
        self.network_links.remove(link)
        self.topology_scene.removeItem(link)
    
  def save_state(self):
    '''
    Save all JSON serialized entities of both the STS and GUI topologies to a file
    Each line is in the format (<entity type>, <serialized form>):
      "s" = switch
      "h" = host
      "l" = network link
    Access links need not be saved, because there is a one to one correspondence
    between hosts and access links
    '''
    lines = []
    for gui_switch in self.switches:
      sts_switch = self.get_sts_switch(gui_switch)
      line = json.dumps(("s", self.serialize_switch(gui_switch, sts_switch)))
      lines.append(line)
    for gui_host in self.hosts:
      sts_host = self.get_sts_host(gui_host)
      line = json.dumps(("h", self.serialize_host(gui_host, sts_host)))
      lines.append(line)
    for link in self.sts_topology.network_links:
      line = json.dumps(("l", self.serialize_network_link(link)))
      lines.append(line)

    title = "Specify file to store topology state"
    filename = QtGui.QFileDialog.getSaveFileName(self.topology_view, title, "gui/layouts")
    f = QtCore.QFile(filename)
    f.open(QtCore.QIODevice.WriteOnly)
    for line in lines:
      f.write(QtCore.QByteArray(line + "\n"))
    f.close()

  def load_state(self):
    '''
    Load all JSON serialized entities of both the STS and GUI topologies from a file
    Each line is in the format (type, serialized_entity):
      "s" = switch
      "h" = host
      "l" = network link
    Switches must be loaded first
    '''
    title = "Load topology layout from file"
    filename = QtGui.QFileDialog.getOpenFileName(self.topology_view, title, "gui/layouts")
    f = QtCore.QFile(filename)
    if not f.open(QtCore.QIODevice.ReadOnly):
      self.debug("Error in load_state: Cannot open specified file!")
      return
    line = f.readLine()
    if line.isNull():
      self.debug("Error in load_state: Empty file!")
      return

    # Reset both STS and GUI topology
    self.sts_topology.reset()
    self.reset()

    type2handler = {
      "s" : self.deserialize_switch,
      "h" : self.deserialize_host,
      "l" : self.deserialize_network_link,
    }
    while not line.isNull():
      (type, s) = json.loads(str(line))
      if type not in type2handler.keys():
        self.debug("Error in load_state: Unparseable line detected!")
      type2handler[type](s)
      line = f.readLine()
    f.close()

  def serialize_host(self, gui_host, sts_host):
    '''
    Format Example:
      {"ingress_switch_dpids":[1,3],
       "position":(-60.0,20.0)}
    '''
    ingress_switch_dpids = set()
    for access_link in self.access_links:
      if access_link.source.id == gui_host.id:
        ingress_switch_dpids.add(access_link.dest.id)
      if access_link.dest.id == gui_host.id:
        ingress_switch_dpids.add(access_link.source.id)
    ingress_switch_dpids = list(ingress_switch_dpids)
    position = (round(gui_host.x(), 2), round(gui_host.y(), 2))
    info = {}
    info["ingress_switch_dpids"] = ingress_switch_dpids
    info["position"] = position
    return json.dumps(info)

  def serialize_switch(self, gui_switch, sts_switch):
    '''
    Format Example:
      {"dpid":5,
       "numports":3
       "position":(-10.0,80.0)}
    '''
    dpid = sts_switch.dpid
    numports = len(sts_switch.ports.values())
    position = (round(gui_switch.x(), 2), round(gui_switch.y(), 2))
    info = {}
    info["dpid"] = dpid
    info["numports"] = numports
    info["position"] = position
    return json.dumps(info)

  def serialize_network_link(self, sts_link):
    '''
    Format Example:
      {"from_switch_dpid":5,
       "to_switch_dpid":3}
    '''
    link_info = {}
    link_info["from_switch_dpid"] = sts_link.start_software_switch.dpid
    link_info["to_switch_dpid"] = sts_link.end_software_switch.dpid
    return json.dumps(link_info)

  def deserialize_host(self, s):
    '''
    Format Example:
      {"ingress_switch_dpids":[1,3],
       "position":(-60.0,20.0)}
    '''
    info = json.loads(s)
    ingress_switch_dpids = info["ingress_switch_dpids"]
    position = info["position"]
    sts_ingress_switches = []
    for dpid in ingress_switch_dpids:
      sts_ingress_switches.append(self.sts_topology.dpid2switch[dpid])
    sts_host = self.sts_topology.create_host(sts_ingress_switches)
    self.add_host(sts_host.hid, position)
    for dpid in ingress_switch_dpids:
      self.add_access_link(sts_host.hid, dpid)

  def deserialize_switch(self, s):
    '''
    Format Example:
      {"dpid":5,
       "numports":3
       "position":(-10.0,80.0)}
    '''
    info = json.loads(s)
    dpid = info["dpid"]
    numports = info["numports"]
    position = info["position"]
    sts_switch = self.sts_topology.create_switch(dpid, numports)
    self.add_switch(dpid, position)

  def deserialize_network_link(self, s):
    '''
    Format Example:
      {"from_switch_dpid":5,
       "to_switch_dpid":3}
    '''
    info = json.loads(s)
    from_switch_dpid = info["from_switch_dpid"]
    to_switch_dpid = info["to_switch_dpid"]
    sts_from_switch = self.sts_topology.dpid2switch[from_switch_dpid]
    sts_to_switch = self.sts_topology.dpid2switch[to_switch_dpid]
    sts_link = self.sts_topology.create_network_link(sts_from_switch, None, sts_to_switch, None)
    self.add_network_link(from_switch_dpid, to_switch_dpid)
