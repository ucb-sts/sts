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
  def __init__(self, sts_topology, parent=None, syncPeriod=2.0, debugging=False):
    QtGui.QGraphicsView.__init__(self, parent)
    self.layout = "random"
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
    self.syncer = STSSyncer(sts_topology, self, syncPeriod, debugging)
    
  def drawBackground(self, painter, rect):
    '''
    Draw background. For now just some text
    '''
    sceneRect = self.sceneRect()
    text_rect = QtCore.QRectF(sceneRect.left() - 5, sceneRect.top() + 60,
                 sceneRect.width() - 4, sceneRect.height() - 4)
    
    message = self.tr("Topology")
    font = painter.font()
    font.setPointSize(12)
    painter.setFont(font)
    painter.setPen(QtCore.Qt.darkGray)
    painter.drawText(text_rect.translated(20.8, 5.8), message)
    painter.setPen(QtCore.Qt.white)
    painter.setPen(QtGui.QColor(QtCore.Qt.gray).light(130))
    painter.drawText(text_rect.translated(20, 5), message)
    
  def mouseReleaseEvent(self, event):
    '''
    Show context menu when right-clicking on empty space on the scene.
    '''
    if not self.itemAt(event.pos()):
      if event.button() == QtCore.Qt.RightButton:
        popup = QtGui.QMenu()
        popup.addAction("Toggle Debug Messages", self.syncer.toggleDebugMessages)
        popup.addAction("Load State", self.syncer.load_state)
        popup.addAction("Save State", self.syncer.save_state)
        popup.addAction("Create Switch", self.syncer.createSwitch)
        popup.exec_(event.globalPos())
    QtGui.QGraphicsView.mouseReleaseEvent(self, event)

class STSSyncer:
  '''
  Container of Gui Node and Link objects and periodically syncs with STS Topology 
  '''
  def __init__(self, sts_topology, topology_view, syncPeriod=2.0, debugging=False):
    self.dpid2nodes = {}
    self.links = []
    self.sts_topology = sts_topology
    self.topology_view = topology_view
    self.topology_scene = topology_view.topology_scene
    self.debugging = debugging
    
    # Sync with STS topology
    self.sts_topology = sts_topology
    self.syncPeriod = syncPeriod
    self.sync_with_sts()
    
  @property
  def nodes(self):
    return self.dpid2nodes.values()

  @property
  def dpids(self):
    return self.dpid2nodes.keys()

  def debug(self, msg):
    if self.debugging:
      log.debug(msg)
  
  def toggleDebugMessages(self):
    self.debugging = not self.debugging
  
  def synced_with_sts(self):
    '''
    Returns True if STSSyncer shares the same map of nodes and links with STS topology
    '''
    self.debug("\n================== STS Sync Check =================="+
               "\n\tGui nodes: %s" % len(self.nodes)+
               "\n\t\tSTS switches: %s" % len(self.sts_topology.dpid2switch)+
               "\n\t\tSTS hosts: %s" % len(self.sts_topology.hosts)+
               "\n\tGui links : %s" % len(self.links)+
               "\n\t\tSTS access links : %s" % len(self.sts_topology.access_links)+
               "\n\t\tSTS network links : %s" % len(self.sts_topology.network_links)+
               "\n====================================================\n")
    
    if len(self.nodes) != len(self.sts_topology.switches) + len(self.sts_topology.hosts) or\
        len(self.links) != len(self.sts_topology.access_links) + len(self.sts_topology.network_links):
      return False
    for node in self.nodes:
      if isinstance(node, GuiHost):    
        if str(node.id) not in [self.get_gui_id(host) for host in self.sts_topology.hosts]:
          return False 
      if isinstance(node, GuiSwitch):
        if str(node.id) not in [self.get_gui_id(switch) for switch in self.sts_topology.switches]:
          return False
    return True
  
  def sync_with_sts(self):
    Timer(self.syncPeriod, self.sync_with_sts).start()
    if self.sts_topology is None:
      self.debug("Error: sts_topology is None!")
      return
     
    if not self.synced_with_sts():
      self.debug("Not synced with STS!")
      for link in self.links:
        if link in self.topology_scene.items():
          self.topology_scene.removeItem(link) 
      self.links = []
      
      sts_host_ids = [self.get_gui_id(host) for host in self.sts_topology.hosts]
      sts_switch_ids = [self.get_gui_id(switch) for switch in self.sts_topology.switches]
      
      # Remove nodes found in GUI but not STS
      for node_id in self.dpids:
        if node_id not in sts_host_ids and node_id not in sts_switch_ids:
          if self.dpid2nodes[node_id] in self.topology_scene.items():
            self.topology_scene.removeItem(self.dpid2nodes[node_id])
          del self.dpid2nodes[node_id]
          self.debug("--- Removing node with dpid = %s" % node_id)
      
      # Add switches found in STS but not in GUI
      for dpid in sts_switch_ids:
        self.addNode(dpid, "switch")
        self.debug("--- Adding new switch with dpid = %s" % dpid)
      
      # Add hosts found in STS but not in GUI
      for host in self.sts_topology.hosts:
        node_id = self.get_gui_id(host)
        self.addNode(node_id, "host")
        self.debug("--- Adding new host with dpid = %s!" % node_id)
      
      # Connect all access links
      for access_link in self.sts_topology.access_links:
        sts_host = access_link.host
        sts_switch = access_link.switch
        host_id = self.get_gui_id(sts_host)
        switch_id = self.get_gui_id(sts_switch)
        self.addLink(host_id, switch_id)
        self.debug("--- Adding new access link connecting %s<-->%s!" % (host_id, switch_id))
      
      # Connect all network links
      for network_link in self.sts_topology.network_links:
        sts_switch1 = network_link.start_software_switch
        sts_switch2 = network_link.end_software_switch
        switch1_id = self.get_gui_id(sts_switch1)
        switch2_id = self.get_gui_id(sts_switch2)
        self.addLink(switch1_id, switch2_id)
        self.debug("--- Adding new network link connecting %s<-->%s!" % (switch1_id, switch2_id))

  def addNode(self, node_id=None, node_type=None):
    '''
    Add a new node to topology scene
    '''
    if node_id is None or (node_type != "host" and node_type != "switch"):
      return
    node_id = str(node_id)
    if node_id not in self.dpids:
      node_number = len(self.dpids) # Guarantees that a new node_number will be used
      if node_type=="host":
        node = GuiHost(self.topology_view, node_id, node_number)
      elif node_type=="switch":
        node = GuiSwitch(self.topology_view, node_id, node_number)
      self.dpid2nodes[node_id] = node
      self.topology_scene.addItem(node)
      node.setPos(randint(self.topology_view.minX, self.topology_view.maxX),
                  randint(self.topology_view.minY, self.topology_view.maxY))
  
  def addLink(self, node1_id, node2_id):
    '''
    Add a new link to topology scene
    '''
    if node1_id not in self.dpids or node2_id not in self.dpids:
      return
    node1_id = str(node1_id)
    node2_id = str(node2_id)
    link = GuiLink(self.topology_view, self.dpid2nodes[node1_id], self.dpid2nodes[node2_id])
    self.links.append(link)
    self.topology_scene.addItem(link)
  
  def get_gui_id(self, sts_node):
    '''
    Given an STS node, constructs the corresponding GUI node's id
      get_gui_id(host) = construct a comma delimited tuple string from its MAC addresses
      get_gui_id(switch) = switch's dpid in string form
    '''
    if isinstance(sts_node, STSHost):
      return "(" + ",".join([str(interface.hw_addr) for interface in sts_node.interfaces]) + ")"
    elif isinstance(sts_node, STSSwitch):
      return str(sts_node.dpid)
    else:   # Should never happen
      self.debug("Error: Node does not exist in STS!")
      return None
    
  def get_sts_node(self, gui_node):
    '''
    Given a GUI node, retrieves the corresponding STS node if it exists
    '''
    if not isinstance(gui_node, GuiNode) or gui_node.id not in self.dpids:
      self.debug("Error: Node does not exist in GUI!")
      return None
    
    # Switch
    if isinstance(gui_node, GuiSwitch):
      if int(gui_node.id) not in self.sts_topology.dpid2switch.keys():
        self.debug("Error: Switch in GUI %s cannot be found in STS!" % host.id)
        return None
      return self.sts_topology.dpid2switch[int(gui_node.id)]
    
    # Host
    if isinstance(gui_node, GuiHost):
      sts_host = None
      for h in self.sts_topology.hosts:
        if gui_node.id == self.get_gui_id(h):
          sts_host = h
      if sts_host is None:
        self.debug("Error: Host in GUI %s cannot be found in STS!" % host.id)
      return sts_host
           
  def createSwitch(self, dpid=None):
    '''
    Create a new switch in both the gui and the original STS topology
    Assumes that STS topology's maximum dpid = number of switches 
    '''
    if dpid is None:
      dpid = max(self.sts_topology.dpid2switch.keys())+1
    num_ports = 1
    switch = self.sts_topology.create_switch(dpid, num_ports)
    self.addNode(dpid, "switch")
   
  def createLink(self, node1_id, node2_id):
    '''
    Create a new link in both the gui and the original STS topology
    '''
    if node1_id is None or node2_id is None:
      return
    node1_id = str(node1_id)
    node2_id = str(node2_id)
    if node1_id not in self.dpids or node2_id not in self.dpids:
      return
    node1 = self.dpid2nodes[node1_id]
    node2 = self.dpid2nodes[node2_id]
    
    # Network link
    if isinstance(node1, GuiSwitch) and isinstance(node2, GuiSwitch):
      sts_switch1 = self.get_sts_node(node1)
      sts_switch2 = self.get_sts_node(node2)
      if sts_switch1 is None or sts_switch2 is None:
        return
      self.sts_topology.create_network_link(sts_switch1, None, sts_switch2, None)
      self.addLink(node1_id, node2_id)
      
    # Access link
    elif (isinstance(node1, GuiSwitch) and isinstance(node2, GuiHost)) or \
          (isinstance(node1, GuiHost) and isinstance(node2, GuiSwitch)):
      host = node1 if isinstance(node1, GuiHost) else node2
      switch = node1 if isinstance(node1, GuiSwitch) else node2
      sts_host = self.get_sts_node(host)
      sts_switch = self.get_sts_node(switch)
      if sts_host is None or sts_switch is None:
        return
      self.sts_topology.create_access_link(sts_host, None, sts_switch, None)
      self.addLink(node1_id, node2_id)
      
      # Update GUI host's id
      del self.dpid2nodes[host.id]
      host.id = self.get_gui_id(sts_host)
      self.dpid2nodes[host.id] = host
      
  def save_state(self):
    '''
    Save all JSON serialized entities of both the STS and GUI topologies to a file
    Each line is in the format (<entity type>, <serialized form>):
      "h" = host
      "s" = switch
      "al" = access link
      "nl" = network link
    '''
    lines = []
    
    for node in self.nodes:
      sts_node = self.get_sts_node(node)
      if isinstance(node, GuiHost):
        line = json.dumps(("h", self.serialize_host(node, sts_node)))
        lines.append(line)
      elif isinstance(node, GuiSwitch):
        line = json.dumps(("s", self.serialize_switch(node, sts_node)))
        lines.append(line)
      else:   # Should never happen
        self.debug("Error in save_state: Node examined is neither switch nor host!")
        return
     
    for link in self.sts_topology.access_links:
      line = json.dumps(("al", self.serialize_access_link(link)))
      lines.append(line)
     
    for link in self.sts_topology.network_links:
      line = json.dumps(("nl", self.serialize_network_link(link)))
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
      "h" = host
      "s" = switch
      "al" = access link
      "nl" = network link
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
    
    new_gui_dpid2nodes = {}
    new_gui_links = []
    new_sts_hosts = []
    new_sts_dpid2switch = {}
    new_sts_port2access_link = {}
    new_sts_interface2access_link = {}
    new_sts_port2internal_link = {}
    
    while not line.isNull():
      (type, s) = json.loads(str(line))
      
      # Host
      if type == "h":
        (gui_host, sts_host) = self.deserialize_host(s)
        new_gui_dpid2nodes[gui_host.id] = gui_host
        new_sts_hosts.append(sts_host)
      
      # Switch
      elif type == "s":
        (gui_switch, sts_switch) = self.deserialize_switch(s)
        new_gui_dpid2nodes[gui_switch.id] = gui_switch
        new_sts_dpid2switch[int(gui_switch.id)] = sts_switch
    
      # Access link
      elif type == "al":
        (gui_link, sts_link) = self.deserialize_access_link(s,
                        new_sts_hosts, new_sts_dpid2switch, new_gui_dpid2nodes)
        new_sts_interface2access_link[sts_link.interface] = sts_link
        new_sts_port2access_link[sts_link.switch_port] = sts_link
        new_gui_links.append(gui_link)
      
      # Network link
      elif type == "nl":
        (gui_link, sts_link) = self.deserialize_network_link(s,
                        new_sts_dpid2switch, new_gui_dpid2nodes)
        new_sts_port2internal_link[sts_link.start_port] = sts_link
        new_gui_links.append(gui_link)
      
      else:
        self.debug("Error in load_state: Unparseable line detected!")
      line = f.readLine()
    f.close()
    
    # Essentially restart the entire topology in both GUI and STS
    self.sts_topology.restart(new_sts_hosts, new_sts_dpid2switch, new_sts_port2access_link,
                              new_sts_port2internal_link, new_sts_interface2access_link)
    
    for node_id in self.dpids:
      if self.dpid2nodes[node_id] in self.topology_scene.items():
        self.topology_scene.removeItem(self.dpid2nodes[node_id])
        del self.dpid2nodes[node_id]
    self.dpid2nodes = new_gui_dpid2nodes
    for node in self.nodes:
      self.topology_scene.addItem(node)
    
    for link in self.links:
      if link in self.topology_scene.items():
        self.topology_scene.removeItem(link)
    self.links = new_gui_links
    for link in self.links:
      self.topology_scene.addItem(link)

  def serialize_host(self, gui_host, sts_host):
    '''
    Format Example:
      {"host_id":"(00:00:00:01:00:01)",
       "host_number":6,
       "host_name":"host:[IPAddr('123.1.0.1')]",
       "host_interfaces":[(00:00:00:01:00:01,['123.1.0.1'],eth2)],
       "host_position":(-60.0,20.0)}
    '''
    host_id = gui_host.id
    host_number = gui_host.number
    host_name = sts_host.name
    
    # For each interface, save a list of tuple (MAC address, IP addresses list, name)
    host_interfaces = [(str(i.hw_addr), [str(ip) for ip in i.ips], i.name)  
                for i in sts_host.interfaces]
    host_position = (round(gui_host.x(), 2), round(gui_host.y(), 2))
    
    host_info = {}
    host_info["host_id"] = host_id
    host_info["host_number"] = host_number
    host_info["host_name"] = host_name
    host_info["host_interfaces"] = host_interfaces
    host_info["host_position"] = host_position
    return json.dumps(host_info)
  
  def serialize_switch(self, gui_switch, sts_switch):
    '''
    Format Example:
      {"switch_id":"5",
       "switch_number":4,
       "switch_name":"SoftSwitch(5)",
       "switch_host":[(00:00:00:00:05:01,1.1.5.1,1)],
       "switch_can_connect_to_end_hosts":True
       "switch_position":(-10.0,80.0)}
    '''
    switch_id = gui_switch.id
    switch_number = gui_switch.number
    switch_name = sts_switch.name
    
    # For each port, save a list of tuple (MAC Address, IP Address, Port number)
    switch_ports = [(str(p.hw_addr), str(p.ip_addr) if hasattr(p, "ip_addr") else "", p.port_no)
              for p in sts_switch.ports.values()]
    switch_can_connect_to_end_hosts = sts_switch.can_connect_to_endhosts
    switch_position = (round(gui_switch.x(), 2), round(gui_switch.y(), 2))
    
    switch_info = {}
    switch_info["switch_id"] = switch_id
    switch_info["switch_number"] = switch_number
    switch_info["switch_name"] = switch_name
    switch_info["switch_ports"] = switch_ports
    switch_info["switch_can_connect_to_end_hosts"] = switch_can_connect_to_end_hosts
    switch_info["switch_position"] = switch_position
    return json.dumps(switch_info)
  
  def serialize_access_link(self, sts_link):
    '''
    Format Example:
      {"host_id":"(00:00:00:01:00:01)",
       "host_interface_mac":"00:00:00:01:00:01",
       "switch_id":"2",
       "switch_port_mac","00:00:00:00:02:01"}
    '''
    host_id = self.get_gui_id(sts_link.host)
    host_interface_mac = str(sts_link.interface.hw_addr)
    switch_id = self.get_gui_id(sts_link.switch)
    switch_port_mac = str(sts_link.switch_port.hw_addr)
    
    link_info = {}
    link_info["host_id"] = host_id
    link_info["host_interface_mac"] = host_interface_mac
    link_info["switch_id"] = switch_id
    link_info["switch_port_mac"] = switch_port_mac
    return json.dumps(link_info)
  
  def serialize_network_link(self, sts_link):
    '''
    Format Example:
      {"from_switch_id":"5",
       "from_port_mac":"00:00:00:00:05:01",
       "to_switch_id":"3",
       "to_port_mac":"00:00:00:00:03:02"}
    '''
    from_switch_id = self.get_gui_id(sts_link.start_software_switch)
    from_port_mac = str(sts_link.start_port.hw_addr)
    to_switch_id = self.get_gui_id(sts_link.end_software_switch)
    to_port_mac = str(sts_link.end_port.hw_addr)
    
    link_info = {}
    link_info["from_switch_id"] = from_switch_id
    link_info["from_port_mac"] = from_port_mac
    link_info["to_switch_id"] = to_switch_id
    link_info["to_port_mac"] = to_port_mac
    return json.dumps(link_info)

  def deserialize_host(self, s):
    '''
    Returns tuple pair of (gui_host, sts_host)
    Format Example:
      {"host_id":"(00:00:00:01:00:01)",
       "host_number":6,
       "host_name":"host:[IPAddr('123.1.0.1')]",
       "host_interfaces":[(00:00:00:01:00:01,['123.1.0.1'],eth2)]",
       "host_position":(-60.0,20.0)}
    '''
    host_info = json.loads(s)
    
    interfaces = []
    interface_info = host_info["host_interfaces"]
    for hw_addr, ips, name in interface_info:
      ips = [IPAddr(str(ip)) for ip in ips]
      interface = STSHostInterface(EthAddr(hw_addr), ips, name)
      interfaces.append(interface)
    
    id = host_info["host_id"]
    number = host_info["host_number"] 
    name = host_info["host_name"]
    (position_x, position_y) = host_info["host_position"]
    
    gui_host = GuiHost(self.topology_view, id, number)
    gui_host.setPos(position_x, position_y)
    sts_host = STSHost(interfaces, name)
    return (gui_host, sts_host)
  
  def deserialize_switch(self, s):
    '''
    Returns tuple pair of (gui_switch, sts_switch)
    Format Example:
      {"switch_id":"5",
       "switch_number":4,
       "switch_name":"SoftSwitch(5)",
       "switch_ports":[(00:00:00:00:05:01,1.1.5.1,1)],
       "switch_can_connect_to_end_hosts":True
       "switch_position":(-10.0,80.0)}
    '''
    switch_info = json.loads(s)
    
    ports = []
    port_info = switch_info["switch_ports"]
    for hw_addr, ip_addr, port_no in port_info:
      port = ofp_phy_port(port_no=port_no, hw_addr=EthAddr(hw_addr))
      if ip_addr is not None and str(ip_addr) != "":
        port.ip_addr = IPAddr(str(ip_addr))
      ports.append(port)
    
    id = switch_info["switch_id"]
    number = switch_info["switch_number"]
    name = switch_info["switch_name"]
    can_connect_to_end_hosts = switch_info["switch_can_connect_to_end_hosts"]
    position_x, position_y = switch_info["switch_position"]
    
    gui_switch = GuiSwitch(self.topology_view, id, number)
    gui_switch.setPos(position_x, position_y)
    sts_switch = STSSwitch(dpid=int(id), name=name, ports=ports,
                    can_connect_to_endhosts=can_connect_to_end_hosts)
    return (gui_switch, sts_switch)
  
  def deserialize_access_link(self, s, sts_hosts, sts_dpid2switch, gui_nodes):
    '''
    Returns the tuple pair (gui_link, sts_link)
    Format Example:
      {"host_id":"(00:00:00:01:00:01)",
       "host_interface_mac":"00:00:00:01:00:01",
       "switch_id":"2",
       "switch_port_mac","00:00:00:00:02:01"}
    '''
    link_info = json.loads(s)
    
    host_id = link_info["host_id"]
    host_interface_mac = link_info["host_interface_mac"]
    switch_id = link_info["switch_id"]
    switch_port_mac = link_info["switch_port_mac"]
    
    sts_host = None
    sts_host_interface = None
    sts_switch = None
    sts_switch_port = None
    
    for host in sts_hosts:
      if host_id == self.get_gui_id(host):
        sts_host = host
        for interface in host.interfaces:
          if host_interface_mac == str(interface.hw_addr):
            sts_host_interface = interface
    
    if int(switch_id) in sts_dpid2switch.keys():
      sts_switch = sts_dpid2switch[int(switch_id)]
      for port in sts_switch.ports.values():
        if str(port.hw_addr) == switch_port_mac:
          sts_switch_port = port
    
    if sts_host is None or sts_host_interface is None or sts_switch is None or sts_switch_port is None:
      self.debug("Error in deserializing access link!")
      return
    
    gui_link = GuiLink(self.topology_view, gui_nodes[host_id], gui_nodes[switch_id])
    sts_link = STSAccessLink(sts_host, sts_host_interface, sts_switch, sts_switch_port)
    return (gui_link, sts_link)
    
  def deserialize_network_link(self, s, sts_dpid2switch, gui_nodes):
    '''
    Returns the tuple pair (gui_link, sts_link)
    Format Example:
      {"from_switch_id":"5",
       "from_port_mac":"00:00:00:00:05:01",
       "to_switch_id":"3",
       "to_port_mac":"00:00:00:00:03:02"}
    '''
    link_info = json.loads(s)
    
    from_switch_id = link_info["from_switch_id"]
    from_port_mac = link_info["from_port_mac"]
    to_switch_id = link_info["to_switch_id"]
    to_port_mac = link_info["to_port_mac"]
    
    sts_from_switch = None
    sts_from_port = None
    sts_to_switch = None
    sts_to_port = None
    
    if int(from_switch_id) in sts_dpid2switch.keys():
      sts_from_switch = sts_dpid2switch[int(from_switch_id)]
      for port in sts_from_switch.ports.values():
        if str(port.hw_addr) == from_port_mac:
          sts_from_port = port
    
    if int(to_switch_id) in sts_dpid2switch.keys():
      sts_to_switch = sts_dpid2switch[int(to_switch_id)]
      for port in sts_to_switch.ports.values():
        if str(port.hw_addr) == to_port_mac:
          sts_to_port = port
    
    if sts_from_switch is None or sts_from_port is None or\
      sts_to_switch is None and sts_to_port is None:
      self.debug("Error in deserializing network link!")
      return
    
    gui_link = GuiLink(self.topology_view, gui_nodes[from_switch_id], gui_nodes[to_switch_id])   
    sts_link = STSNetworkLink(sts_from_switch, sts_from_port, sts_to_switch, sts_to_port)
    return (gui_link, sts_link)
    