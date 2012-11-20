'''
The main topology widget of the GUI 
'''

from sts.entities import FuzzSoftwareSwitch, Host, HostInterface, AccessLink, Link as NetworkLink
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

class TopoWidget(QtGui.QWidget):
  '''
  QWidget container for TopologyView
  '''
  def __init__(self, sts_topology, parent=None):
    QtGui.QWidget.__init__(self, parent)
    self.topology_view = TopologyView(sts_topology, self)
    vbox = QtGui.QVBoxLayout()
    vbox.addWidget(self.topology_view)
    self.setLayout(vbox)
    self.resize(300, 150)
    
class TopologyView(QtGui.QGraphicsView):
  '''
  QGraphicsView that provides a graphical representation of STS topology
  '''
  def __init__(self, sts_topology, parent=None):
    QtGui.QGraphicsView.__init__(self, parent)
    self.layout = "random"
    self.topo_scene = QtGui.QGraphicsScene(self)
    self.topo_scene.setItemIndexMethod(QtGui.QGraphicsScene.NoIndex)
    self.topo_scene.setSceneRect(-300, -300, 600, 600)
    self.setScene(self.topo_scene)
    self.setRenderHint(QtGui.QPainter.Antialiasing)
    self.setStyleSheet("background: black")
    self.scale(0.9, 0.9)
    self.setMinimumSize(400, 400)
    
    # Node and link QGraphicsItems
    self.nodes = {}
    self.links = []
    
    # Node boundaries
    self.minX, self.maxX = -300, 300
    self.minY, self.maxY = -200, 200
    
    # Cursor
    self.setDragMode(self.ScrollHandDrag)
    self.setCursor(QtCore.Qt.ArrowCursor)
    
    # Default to no debugging messages
    self.debugging = False
    
    # Sync with STS topology
    self.sts_topology = sts_topology
    self.sync_with_sts()
  
  def debug(self, msg):
    if self.debugging:
      log.debug(msg)
  
  def synced_with_sts(self):
    '''
    Returns True if TopologyView shares the same map of nodes and links with STS topology
    '''
    self.debug("\n======================= STS Sync Check =======================")
    self.debug("\tGui nodes: %s" % len(self.nodes))
    self.debug("\t\tSTS switches: %s" % len(self.sts_topology.dpid2switch))
    self.debug("\t\tSTS hosts: %s" % len(self.sts_topology.hosts))
    self.debug("\tGui links : %s" % len(self.links))
    self.debug("\t\tSTS access links : %s" % len(self.sts_topology.access_links))
    self.debug("\t\tSTS network links : %s" % len(self.sts_topology.network_links))
    self.debug("\n==============================================================\n")
    
    if len(self.nodes) != len(self.sts_topology.dpid2switch) + len(self.sts_topology.hosts) or\
        len(self.links) != len(self.sts_topology.access_links) + len(self.sts_topology.network_links):
      return False
    for node in self.nodes.values():
      if node.type == "host":    
        if str(node.id) not in [self.get_gui_id(host) for host in self.sts_topology.hosts]:
          return False 
      if node.type == "switch":
        if str(node.id) not in [self.get_gui_id(switch) for switch in self.sts_topology.dpid2switch.values()]:
          return False
    return True
  
  def sync_with_sts(self):
    Timer(2.0, self.sync_with_sts).start()
    if self.sts_topology == None:
      self.debug("Error: sts_topology is None!")
      return
     
    if not self.synced_with_sts():
      for link in self.links:
        if link in self.topo_scene.items():
          self.topo_scene.removeItem(link) 
      self.links = []
      
      sts_host_ids = [self.get_gui_id(host) for host in self.sts_topology.hosts]
      sts_switch_ids = [self.get_gui_id(switch) for switch in self.sts_topology.dpid2switch.values()]
      
      # Remove nodes found in GUI but not STS
      for node_id in self.nodes.keys():
        if node_id not in sts_host_ids and node_id not in sts_switch_ids:
          if self.nodes[node_id] in self.topo_scene.items():
            self.topo_scene.removeItem(self.nodes[node_id])
          del self.nodes[node_id]
      
      # Add switches found in STS but not in GUI
      for dpid in sts_switch_ids:
        self.addNode(dpid, "switch")
      
      # Add hosts found in STS but not in GUI
      for host in self.sts_topology.hosts:
        node_id = self.get_gui_id(host)
        self.addNode(node_id, "host")
      
      # Connect all access links
      for i, access_link in enumerate(self.sts_topology.access_links):
        sts_host = access_link.host
        sts_switch = access_link.switch
        host_id = self.get_gui_id(sts_host)
        switch_id = self.get_gui_id(sts_switch)
        self.addLink(host_id, switch_id)
      
      # Connect all network links
      for i, network_link in enumerate(self.sts_topology.network_links):
        sts_switch1 = network_link.start_software_switch
        sts_switch2 = network_link.end_software_switch
        switch1_id = self.get_gui_id(sts_switch1)
        switch2_id = self.get_gui_id(sts_switch2)
        self.addLink(switch1_id, switch2_id)
   
  def addNode(self, node_id=None, node_type=None):
    '''
    Add new node to topology Scene
    '''
    if node_id == None or (node_type != "host" and node_type != "switch"):
      return
    
    node_id = str(node_id)
    if node_id not in self.nodes.keys():
      node_number = len(self.nodes)  # Guarantees that a new node number is used
      node = Node(self, node_id, node_number, node_type)
      self.nodes[node_id] = node
      self.topo_scene.addItem(node)
      node.setPos(randint(self.minX, self.maxX), randint(self.minY, self.maxY))
  
  def addLink(self, node1_id, node2_id):
    '''
    Add new link to topology Scene
    '''
    if node1_id not in self.nodes.keys() or node2_id not in self.nodes.keys():
      return
    
    node1_id = str(node1_id)
    node2_id = str(node2_id)
    link = Link(self, self.nodes[node1_id], self.nodes[node2_id])
    self.links.append(link)
    self.topo_scene.addItem(link)
  
  def get_gui_id(self, sts_node):
    '''
    Given an STS node, constructs the corresponding GUI node's id
    If given node is host, then construct a comma delimited tuple string from its MAC addresses
    Otherwise, if given node is switch, then return the switch's dpid in string form
    '''
    if isinstance(sts_node, Host):
      return "(" + ",".join([str(interface.hw_addr) for interface in sts_node.interfaces]) + ")"
    elif isinstance(sts_node, FuzzSoftwareSwitch):
      return str(sts_node.dpid)
    else:   # Should never happen
      self.debug("Error: Node does not exist in STS!")
      return None
    
  def get_sts_node(self, gui_node):
    '''
    Given a GUI node, retrieves the corresponding STS node if it exists
    '''
    if not isinstance(gui_node, Node) or gui_node.id not in self.nodes.keys():
      self.debug("Error: Node does not exist in GUI!")
      return None
    
    # Switch
    if gui_node.type == "switch":
      if int(gui_node.id) not in self.sts_topology.dpid2switch.keys():
        self.debug("Error: Switch in GUI %s cannot be found in STS!" % host.id)
        return None
      return self.sts_topology.dpid2switch[int(gui_node.id)]
    
    # Host
    if gui_node.type == "host":
      sts_host = None
      for h in self.sts_topology.hosts:
        if gui_node.id == self.get_gui_id(h):
          sts_host = h
      if sts_host == None:
        self.debug("Error: Host in GUI %s cannot be found in STS!" % host.id)
      return sts_host
           
  def createSwitch(self, dpid=None):
    '''
    Create a new switch in both the gui and the original STS topology
    Assumes that STS topology's maximum dpid = number of switches 
    '''
    if dpid is None:
      dpid = max(self.sts_topology.dpid2switch.keys()) + 1
    num_ports = 1
    switch = self.sts_topology.create_switch(dpid, num_ports)
    self.addNode(dpid, "switch")
   
  def createLink(self, node1_id, node2_id):
    '''
    Create a new link in both the gui and the original STS topology
    '''
    if node1_id == None or node2_id == None:
      return
    
    node1_id = str(node1_id)
    node2_id = str(node2_id)
    if node1_id not in self.nodes.keys() or node2_id not in self.nodes.keys():
      return
    
    node1 = self.nodes[node1_id]
    node2 = self.nodes[node2_id]
    
    # Network link
    if node1.type == "switch" and node2.type == "switch":
      sts_switch1 = self.get_sts_node(node1)
      sts_switch2 = self.get_sts_node(node2)
      if sts_switch1 == None or sts_switch2 == None:
        return
      self.sts_topology.create_network_link(sts_switch1, None, sts_switch2, None)
      self.addLink(node1_id, node2_id)
      
    # Access link
    elif (node1.type == "switch" and node2.type == "host") or \
      (node1.type == "host" and node2.type == "switch"):
      host = node1 if node1.type == "host" else node2
      switch = node1 if node1.type == "switch" else node2
      sts_host = self.get_sts_node(host)
      sts_switch = self.get_sts_node(switch)
      if sts_host == None or sts_switch == None:
        return
      self.sts_topology.create_access_link(sts_host, None, sts_switch, None)
      self.addLink(node1_id, node2_id)
      
      # Update GUI host's id
      del self.nodes[host.id]
      host.id = self.get_gui_id(sts_host)
      self.nodes[host.id] = host
  
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
        
  def wheelEvent(self, event):
    '''
    Zoom
    '''
    self.scaleView(math.pow(2.0, event.delta() / 300.0))
    
  def scaleView(self, scaleFactor):
    factor = self.matrix().scale(scaleFactor, scaleFactor).mapRect(QtCore.QRectF(0, 0, 1, 1)).width()

    if factor < 0.07 or factor > 100:
      return

    self.scale(scaleFactor, scaleFactor)
  
  def mouseReleaseEvent(self, event):
    '''
    Show context menu when right-clicking on empty space on the scene.
    '''
    if not self.itemAt(event.pos()):
      if event.button() == QtCore.Qt.RightButton:
        popup = QtGui.QMenu()
        popup.addAction("Toggle Debug Messages", self.toggleDebugMessages)
        popup.addAction("Load State", self.load_state)
        popup.addAction("Save State", self.save_state)
        popup.addAction("Create Switch", self.createSwitch)
        popup.exec_(event.globalPos())
    QtGui.QGraphicsView.mouseReleaseEvent(self, event)
  
  def toggleDebugMessages(self):
    '''
    Toggles whether or not debug messages are printed to console
    '''
    self.debugging = not self.debugging
  
  def save_state(self):
    '''
    Save all JSON serialized entities of both the STS and GUI topologies to a file
    '''
    node_lines = []
    link_lines = []
    
    for node in self.nodes.values():
      sts_node = self.get_sts_node(node)
      
      if node.type == "host":
        line = json.dumps(("h", self.serialize_host(node, sts_node)))
        node_lines.append(line)
      elif node.type == "switch":
        line = json.dumps(("s", self.serialize_switch(node, sts_node)))
        node_lines.append(line)
      else:   # Should never happen
        self.debug("Error in save_state: Node examined is neither switch nor host!")
        return
     
    for link in self.sts_topology.access_links:
      line = json.dumps(("al", self.serialize_access_link(link)))
      link_lines.append(line)
     
    for link in self.sts_topology.network_links:
      line = json.dumps(("nl", self.serialize_network_link(link)))
      link_lines.append(line)
    
    title = "Specify file to store topology state"
    filename = QtGui.QFileDialog.getSaveFileName(self, title, "gui/layouts")
    f = QtCore.QFile(filename)
    f.open(QtCore.QIODevice.WriteOnly)

    for line in node_lines:
      f.write(QtCore.QByteArray(line + "\n"))
    for line in link_lines:
      f.write(QtCore.QByteArray(line + "\n"))
    f.close()
  
  def load_state(self):
    '''
    Load all JSON serialized entities of both the STS and GUI topologies from a file
    '''
    title = "Load topology layout from file"
    filename = QtGui.QFileDialog.getOpenFileName(self, title, "gui/layouts")
    f = QtCore.QFile(filename)
    if not f.open(QtCore.QIODevice.ReadOnly):
      self.debug("Error in load_state: Cannot open specified file!")
      return
    line = f.readLine()
    
    if line.isNull():
      self.debug("Error in load_state: Empty file!")
      return
    
    new_gui_nodes = {}
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
        new_gui_nodes[gui_host.id] = gui_host
        new_sts_hosts.append(sts_host)
      
      # Switch
      elif type == "s":
        (gui_switch, sts_switch) = self.deserialize_switch(s)
        new_gui_nodes[gui_switch.id] = gui_switch
        new_sts_dpid2switch[int(gui_switch.id)] = sts_switch
    
      # Access link
      elif type == "al":
        (gui_link, sts_link) = self.deserialize_access_link(s,
                        new_sts_hosts, new_sts_dpid2switch, new_gui_nodes)
        new_sts_interface2access_link[sts_link.interface] = sts_link
        new_sts_port2access_link[sts_link.switch_port] = sts_link
        new_gui_links.append(gui_link)
      
      # Network link
      elif type == "nl":
        (gui_link, sts_link) = self.deserialize_network_link(s,
                        new_sts_dpid2switch, new_gui_nodes)
        new_sts_port2internal_link[sts_link.start_port] = sts_link
        new_gui_links.append(gui_link)
      
      else:
        self.debug("Error in load_state: Unparseable line detected!")
      line = f.readLine()
    f.close()
    
    '''
    Essentially restart the entire topology in both GUI and STS
    '''
    self.sts_topology.restart(new_sts_hosts, new_sts_dpid2switch, new_sts_port2access_link,
                              new_sts_port2internal_link, new_sts_interface2access_link)
    
    for node_id in self.nodes.keys():
      if self.nodes[node_id] in self.topo_scene.items():
        self.topo_scene.removeItem(self.nodes[node_id])
        del self.nodes[node_id]
    self.nodes = new_gui_nodes
    for node in self.nodes.values():
      self.topo_scene.addItem(node)
    
    for link in self.links:
      if link in self.topo_scene.items():
        self.topo_scene.removeItem(link)
    self.links = new_gui_links
    for link in self.links:
      self.topo_scene.addItem(link)

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
      interface = HostInterface(EthAddr(hw_addr), ips, name)
      interfaces.append(interface)
    
    id = host_info["host_id"]
    number = host_info["host_number"] 
    name = host_info["host_name"]
    (position_x, position_y) = host_info["host_position"]
    
    gui_host = Node(self, id, number, "host")
    gui_host.setPos(position_x, position_y)
    sts_host = Host(interfaces, name)
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
    
    gui_switch = Node(self, id, number, "switch")
    gui_switch.setPos(position_x, position_y)
    sts_switch = FuzzSoftwareSwitch(dpid=int(id), name=name, ports=ports,
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
    
    if sts_host == None or sts_host_interface == None or sts_switch == None or sts_switch_port == None:
      self.debug("Error in deserializing access link!")
      return
    
    gui_link = Link(self, gui_nodes[host_id], gui_nodes[switch_id])
    sts_link = AccessLink(sts_host, sts_host_interface, sts_switch, sts_switch_port)
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
    
    if sts_from_switch == None or sts_from_port == None or\
      sts_to_switch == None and sts_to_port == None:
      self.debug("Error in deserializing network link!")
      return
    
    gui_link = Link(self, gui_nodes[from_switch_id], gui_nodes[to_switch_id])   
    sts_link = NetworkLink(sts_from_switch, sts_from_port, sts_to_switch, sts_to_port)
    return (gui_link, sts_link)

class Node(QtGui.QGraphicsItem):
  '''
  Interactive Node object
    If node is switch, then id = the switch's dpid;
    else, id = string form of the host's list of MAC addresses
  '''
  def __init__(self, graph_widget, _id, _number, _type, _layer=1):
    QtGui.QGraphicsItem.__init__(self)

    self.graph = graph_widget
    self.topo_widget = self.graph.parent
    self.id = _id
    self.number = _number
    self.type = _type
    self.linkList = []
    self.newPos = QtCore.QPointF()
    self.setFlag(QtGui.QGraphicsItem.ItemIsMovable)
    self.setFlag(QtGui.QGraphicsItem.ItemSendsGeometryChanges)
    self.setZValue(1)
    self.setAcceptHoverEvents(True)
    
    # Node attributes
    self.is_up = True    # up/down state   
    self.showNumber = True  # Draw node number
    self.showNode = True  # Draw node

  def addLink(self, link):
    self.linkList.append(link)
    
    # create localPort->neighborID mapping
    if link.source.id == self.id:
      neibID = link.dest.id
    else:
      neibID = link.source.id
    link.adjust()

  def links(self):
    return self.linkList

    self.setPos(self.newPos)
    return True

  def boundingRect(self):
    adjust = 2.0
    return QtCore.QRectF(-10 - adjust, -10 - adjust, 23 + adjust, 23 + adjust)

  def shape(self):
    path = QtGui.QPainterPath()
    path.addEllipse(-10, -10, 20, 20)
    return path

  def paint(self, painter, option, widget):
    if self.showNode:
      painter.setPen(QtCore.Qt.NoPen)
      painter.setBrush(QtGui.QColor(QtCore.Qt.darkGray).light(25))
      if self.type == "host":
        painter.drawRect(-9, -9, 15, 15)
      else:
        painter.drawEllipse(-9, -9, 20, 20)

      gradient = QtGui.QRadialGradient(-3, -3, 10)
      color = QtGui.QColor(QtCore.Qt.green)
      
      if self.type == "host":
        color = QtGui.QColor(QtCore.Qt.yellow)
      
      if option.state & QtGui.QStyle.State_Sunken:
        gradient.setCenter(3, 3)
        gradient.setFocalPoint(3, 3)
        if self.is_up:
          gradient.setColorAt(1, color.light(100))
          gradient.setColorAt(0, color.light(30))
        else:
          gradient.setColorAt(1, QtGui.QColor(QtCore.Qt.gray).light(80))
          gradient.setColorAt(0, QtGui.QColor(QtCore.Qt.gray).light(20))
      else:
        if self.is_up:
          gradient.setColorAt(0, color.light(85))
          gradient.setColorAt(1, color.light(25))
        else:
          gradient.setColorAt(0, QtGui.QColor(QtCore.Qt.gray).light(60))
          gradient.setColorAt(1, QtGui.QColor(QtCore.Qt.gray).light(10))

      painter.setBrush(QtGui.QBrush(gradient))
      painter.setPen(QtGui.QPen(QtCore.Qt.black, 0))
      if self.type == "host":
        painter.drawRect(-10, -10, 15, 15)
      else:
        painter.drawEllipse(-10, -10, 20, 20)
    
    if self.showNumber:
      # Text.
      text_rect = self.boundingRect()
      message = str(self.number)

      font = painter.font()
      font.setBold(True)
      painter.setFont(font)
      painter.setPen(QtCore.Qt.gray)
      painter.drawText(text_rect.translated(0.1, 0.1), message)
      painter.setPen(QtGui.QColor(QtCore.Qt.gray).light(130))
      painter.drawText(text_rect.translated(0, 0), message)
    
  def itemChange(self, change, value):
    if change == QtGui.QGraphicsItem.ItemPositionChange:
      for link in self.linkList:
        link.adjust()
    return QtGui.QGraphicsItem.itemChange(self, change, value)

  def mousePressEvent(self, event):
    self.still_hover = False
    self.update()
    QtGui.QGraphicsItem.mousePressEvent(self, event)

  def mouseDoubleClickEvent(self, event):
    QtGui.QGraphicsItem.mouseDoubleClickEvent(self, event)
    
  def mouseReleaseEvent(self, event):
    if event.button() == QtCore.Qt.RightButton:
      popup = QtGui.QMenu()
      if self.type == "switch":
        
        # Creates a link to another unconnected node 
        linkToMenu = QtGui.QMenu("Link to")
        
        # Hack against python scoping
        def createLinkLambda(fromID, toID):
          return lambda: self.graph.createLink(fromID, toID)
        
        for node in sorted(self.graph.nodes.values()):
          if node == self:
            continue
          for link in self.linkList:
            if (link.source == self and link.dest == node) or\
              (link.source == node and link.dest == self and node.type == "host"):
              break
          else:
            linkToMenu.addAction(str(node.number), createLinkLambda(self.id, node.id))    
        popup.addMenu(linkToMenu)
        
      # Host Details Menu
      if self.type == "host":
        popup.addMenu(self.node_details)
        
      popup.exec_(event.lastScreenPos())
    self.update()
    QtGui.QGraphicsItem.mouseReleaseEvent(self, event)
       
  def hoverEnterEvent(self, event):
    self.still_hover = True
    # Refresh node_details menu
    self.node_details = QtGui.QMenu('&Node Details')
    if self.type == "switch":
      self.node_details.addAction('Datapath ID: 0x%s' % self.id)
    elif self.type == "host":
      self.node_details.addAction('Host ID: 0x%s' % self.id)
    self.hover_pos = event.lastScreenPos() + QtCore.QPoint(10, 10)
    self.hover_timer = QtCore.QTimer()
    self.hover_timer.singleShot(500, self.popupnode_detailsMenu)
  
  @QtCore.pyqtSlot()  
  def popupnode_detailsMenu(self):
    if self.still_hover:
      self.node_details.exec_(self.hover_pos)
    
  def hoverLeaveEvent(self, event):
    self.still_hover = False
    
class Link(QtGui.QGraphicsItem):
  '''
  Interactive Link 
  '''
  def __init__(self, graph_widget, source_node, dest_node):
    QtGui.QGraphicsItem.__init__(self)
    self.graph = graph_widget
    self.topo_widget = self.graph.parent
    self.arrow_size = 10.0
    self.source_point = QtCore.QPointF()
    self.dest_point = QtCore.QPointF()
    self.setFlag(QtGui.QGraphicsItem.ItemIsMovable)
    self.setAcceptedMouseButtons(QtCore.Qt.RightButton)
    self.setAcceptHoverEvents(False)
    self.source = source_node
    self.dest = dest_node
    self.draw_arrow = False
    self.source.addLink(self)
    self.dest.addLink(self)
    self.adjust()
    
    # Link attributes
    self.is_up = True    # up/down state  
    self.show_link = True  # Draw link
    self.show_id = False   # Draw link ID   
    self.show_ports = True   # Draw connecting ports  
    
    # Link details menu
    self.link_details = QtGui.QMenu('&Link Details')
    self.link_details.addAction("Node IDs: %s - %s" % (self.source.id, self.dest.id))

  def adjust(self):
    if not self.source or not self.dest:
      return

    line = QtCore.QLineF(self.mapFromItem(self.source, 0, 0), \
                self.mapFromItem(self.dest, 0, 0))
    length = line.length()
    
    if length == 0.0:
      return
    
    linkOffset = QtCore.QPointF((line.dx() * 10) / length, (line.dy() * 10) / length)

    self.prepareGeometryChange()
    self.source_point = line.p1() + linkOffset
    self.dest_point = line.p2() - linkOffset

  def boundingRect(self):
    if not self.source or not self.dest:
      return QtCore.QRectF()
    penWidth = 1
    extra = (penWidth + self.arrow_size) / 2.0
    return QtCore.QRectF(self.source_point,
               QtCore.QSizeF(self.dest_point.x() - self.source_point.x(),
                       self.dest_point.y() - self.source_point.y())).normalized().adjusted(-extra, -extra, extra, extra)
    
  def paint(self, painter, option, widget):
    if not self.source or not self.dest:
      return

    # Draw the line itself.
    if self.show_link:
      line = QtCore.QLineF(self.source_point, self.dest_point)
      if line.length() == 0.0:
        return
      
      color = QtCore.Qt.gray
      pattern = QtCore.Qt.SolidLine
      
      # Select pen for line (color for util, pattern for state)
      if self.is_up:
        # Highlight when clicked/held
        if option.state & QtGui.QStyle.State_Sunken:
          color = QtGui.QColor(color).light(256)
        else:
          color = QtGui.QColor(color).light(90)
      else:
        color = QtCore.Qt.darkGray
        pattern = QtCore.Qt.DashLine
              
      painter.setPen(QtGui.QPen(color, 1,
        pattern, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
      painter.drawLine(line)
    
      # Draw the arrows if there's enough room.
      angle = math.acos(line.dx() / line.length())
      if line.dy() >= 0:
        angle = 2 * math.pi - angle

      dest_arrow_p1 = self.dest_point + \
        QtCore.QPointF(math.sin(angle - math.pi / 3) * self.arrow_size,
        math.cos(angle - math.pi / 3) * self.arrow_size)
      dest_arrow_p2 = self.dest_point + \
        QtCore.QPointF(math.sin(angle - math.pi + math.pi / 3) * self.arrow_size,
        math.cos(angle - math.pi + math.pi / 3) * self.arrow_size)
      
      if self.draw_arrow:
        painter.setBrush(color)
        painter.drawPolygon(QtGui.QPolygonF([line.p2(), \
          dest_arrow_p1, dest_arrow_p2]))
    
  def mouseReleaseEvent(self, event):
    if event.button() == QtCore.Qt.RightButton:
      popup = QtGui.QMenu()
      popup.addMenu(self.link_details)
      popup.exec_(event.lastScreenPos())
    self.update()
    QtGui.QGraphicsItem.mouseReleaseEvent(self, event)
  