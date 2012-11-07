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
        self.topologyView = TopologyView(sts_topology, self)
        vbox = QtGui.QVBoxLayout()
        vbox.addWidget(self.topologyView)
        self.setLayout(vbox)
        self.resize(300, 150)
        
class TopologyView(QtGui.QGraphicsView):
    '''
    QGraphicsView that provides a graphical representation of STS topology
    '''
    
    def __init__(self, sts_topology, parent=None):
        QtGui.QGraphicsView.__init__(self, parent)
        self.layout = "random"
        self.setStyleSheet("background: black")
        self.topoScene = QtGui.QGraphicsScene(self)
        self.topoScene.setItemIndexMethod(QtGui.QGraphicsScene.NoIndex)
        self.topoScene.setSceneRect(-300, -300, 600, 600)
        self.setScene(self.topoScene)
        self.setRenderHint(QtGui.QPainter.Antialiasing)
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
        
        # Sync with STS topology
        self.sts_topology = sts_topology
        self.syncWithSTS()
        
    def syncedWithSTS(self):
        '''
        Returns True if TopologyView shares the same map of nodes and links with STS topology
        '''
        
        log.debug("\n======================= STS Sync Check =======================")
        log.debug("\tGui nodes: %s" % len(self.nodes))
        log.debug("\t\tSTS switches: %s" % len(self.sts_topology.dpid2switch))
        log.debug("\t\tSTS hosts: %s" % len(self.sts_topology.hosts))
        log.debug("\tGui links : %s" % len(self.links))
        log.debug("\t\tSTS access links : %s" % len(self.sts_topology.access_links))
        log.debug("\t\tSTS network links : %s" % len(self.sts_topology.network_links))
        log.debug("\n==============================================================\n")
        
        if len(self.nodes) != len(self.sts_topology.dpid2switch) + len(self.sts_topology.hosts):
            return False
        if len(self.links) != len(self.sts_topology.access_links) + len(self.sts_topology.network_links):
            return False
        for node in self.nodes.values():
            if node.type=="host":        
                if str(node.id) not in ["("+",".join(map(lambda i: str(i.hw_addr), host.interfaces))+")" for host in self.sts_topology.hosts]:
                    return False 
            elif node.type=="switch":
                if str(node.id) not in [str(switch.dpid) for switch in self.sts_topology.switches]:
                    return False
            else: return False  # should never happen
        return True
    
    def syncWithSTS(self):
        Timer(2.0, self.syncWithSTS).start()
        if self.sts_topology==None:
            log.debug("\tError: sts_topology is None!")
            return
       
        if not self.syncedWithSTS():
            
            log.debug("\tSyncing!")
            log.debug("\t>> Removing all links!")
            
            for link in self.links:
                if link in self.topoScene.items():
                    self.topoScene.removeItem(link) 
            self.links = []
            
            sts_hostIDs = ["("+",".join(map(lambda interface: str(interface.hw_addr), host.interfaces))+")"
                            for host in self.sts_topology.hosts]
            sts_switchIDs = [str(dpid) for dpid in self.sts_topology.dpid2switch.keys()]
            
            log.debug("\t>> Removing nodes found in GUI but not STS")
            
            # Remove nodes found in GUI but not STS
            for nodeID in self.nodes.keys():
                if nodeID not in sts_hostIDs and nodeID not in sts_switchIDs:
                    if self.nodes[nodeID] in self.topoScene.items():
                        log.debug("\t\t##### Removing node %s!" % nodeID)
                        self.topoScene.removeItem(self.nodes[nodeID])
                    del self.nodes[nodeID]
            
            log.debug("\t>> Adding switches found in STS but not GUI")
            
            # Add switches found in STS but not in GUI
            for dpid in sts_switchIDs: self.addNode(dpid, "switch")
            
            log.debug("\t>> Adding hosts found in STS but not GUI")
            
            # Add hosts found in STS but not in GUI
            for host in self.sts_topology.hosts:
                nodeID = "("+",".join(map(lambda interface: str(interface.hw_addr), host.interfaces))+")"
                self.addNode(nodeID, "host")
            
            log.debug("\t>> Adding access links")
            
            # Connect all access links
            for i, accessLink in enumerate(self.sts_topology.access_links):
                sts_host = accessLink.host
                sts_switch = accessLink.switch
                hostID = "("+",".join(map(lambda interface: str(interface.hw_addr), sts_host.interfaces))+")"
                log.debug("\t\t##### Adding access Link %s: %s<==>%s!" % (i, hostID, sts_switch.dpid))
                switchID = str(sts_switch.dpid)
                self.addLink(hostID, switchID)
                
            log.debug("\t>> Adding network links")
            
            # Connect all network links
            for i, networkLink in enumerate(self.sts_topology.network_links):
                sts_switch1 = networkLink.start_software_switch
                sts_switch2 = networkLink.end_software_switch
                log.debug("\t\t##### Network Link %s: %s<==>%s!" % (i, sts_switch1.dpid, sts_switch2.dpid))
                switch1ID = str(sts_switch1.dpid)
                switch2ID = str(sts_switch2.dpid)
                self.addLink(switch1ID, switch2ID)
            
            log.debug("\n========================== ALL DONE ==========================")    
   
    def addNode(self, nodeID=None, nodeType=None):
        '''
        Add new node to topology Scene
        '''
        if nodeID==None or (nodeType!="host" and nodeType!="switch"): return
        
        nodeID = str(nodeID)
        if nodeID not in self.nodes.keys():
            nodeNumber = len(self.nodes)    # Guarantees that a new node number is used
            node = Node(self, nodeID, nodeNumber, nodeType)
            self.nodes[nodeID] = node
            self.topoScene.addItem(node)
            node.setPos(randint(self.minX,self.maxX), randint(self.minY,self.maxY))
    
    def addLink(self, nodeID1, nodeID2):
        '''
        Add new link to topology Scene
        '''
        if nodeID1 not in self.nodes.keys() or nodeID2 not in self.nodes.keys(): return
        
        nodeID1 = str(nodeID1)
        nodeID2 = str(nodeID2)
        link = Link(self, self.nodes[nodeID1], self.nodes[nodeID2], 0, 0, 0)
        self.links.append(link)
        self.topoScene.addItem(link)
    
    def getSTSNode(self, node):
        '''
        Given a GUI node, retrieves the corresponding STS node if it exists
        '''
        
        if not isinstance(node, Node) or node.id not in self.nodes.keys():
            log.debug("\tError: Node does not exist in GUI!")
            return None
        
        # Switch
        if node.type=="switch":
          if int(node.id) not in self.sts_topology.dpid2switch.keys():
            log.debug("\tError: Switch in GUI %s cannot be found in STS!" % host.id)
            return None
          return self.sts_topology.dpid2switch[int(node.id)]
        
        # Host
        elif node.type=="host":
          sts_host = None
          for h in self.sts_topology.hosts:
            if node.id=="("+",".join(map(lambda i: str(i.hw_addr), h.interfaces))+")":
              sts_host = h
          if sts_host==None:
            log.debug("\tError: Host in GUI %s cannot be found in STS!" % host.id)
          return sts_host
            
        # Should never happen
        else:
          log.debug("\tError: Node in GUI %s is neither host nor switch!!" % node.id)
          return None  
                   
    def createSwitch(self, dpid=None):
        '''
        Create a new switch in both the gui and the original STS topology
        Assumes that STS topology's maximum dpid = number of switches 
        '''
        log.debug("Creating switch!")
        if dpid==None:
            dpid = len(self.sts_topology.dpid2switch)+1
        num_ports = 1                                   #arbitrary, TODO: change
        switch = self.sts_topology.create_switch(dpid, num_ports)
        self.sts_topology.dpid2switch[dpid] = switch
        self.addNode(dpid, "switch")
   
    def createLink(self, node1ID, node2ID):
        '''
        Create a new link in both the gui and the original STS topology
        '''
        log.debug("Creating link %s==>%s!" % (node1ID, node2ID))
        
        if node1ID==None or node2ID==None: return
        
        node1ID = str(node1ID)
        node2ID = str(node2ID)
        if node1ID not in self.nodes.keys() or node2ID not in self.nodes.keys(): return
        
        node1 = self.nodes[node1ID]
        node2 = self.nodes[node2ID]
        
        # Network link
        if node1.type=="switch" and node2.type=="switch":
          log.debug("\tCreating network link in STS!")
          sts_switch1 = self.getSTSNode(node1)
          sts_switch2 = self.getSTSNode(node2)
          if sts_switch1==None or sts_switch2==None: return
          self.sts_topology.create_network_link(sts_switch1, None, sts_switch2, None)
          self.addLink(node1ID, node2ID)
          
        # Access link
        elif (node1.type=="switch" and node2.type=="host") or \
            (node1.type=="host" and node2.type=="switch"):
          log.debug("\tCreating access link in STS")
          host = node1 if node1.type=="host" else node2
          switch = node1 if node1.type=="switch" else node2
          sts_host = self.getSTSNode(host)
          sts_switch = self.getSTSNode(switch)
          if sts_host==None or sts_switch==None: return
          self.sts_topology.create_access_link(sts_host, None, sts_switch, None)
          self.addLink(node1ID, node2ID)
          
          # Update GUI host's id
          del self.nodes[host.id]
          host.id = "("+",".join(map(lambda i: str(i.hw_addr), sts_host.interfaces))+")"
          self.nodes[host.id] = host
          
        
    def positionNodes(self, new_nodes):
        '''
        Position nodes according to current loaded layout (or random if none)
        '''
        
        log.debug("Position nodes")
        if self.layout == "random":
            for node in new_nodes:
                node.setPos(randint(self.minX,self.maxX), randint(self.minY,self.maxY))
        
        else:
            '''
            If node position is described in current layout file, choose that,
            otherwise place randomly
            '''        
            # Optimize: scan file into a dictionary. same for load.
            f = QtCore.QFile("gui/layouts/"+self.layout)
            f.open(QtCore.QIODevice.ReadOnly)
            for node in new_nodes:
                line = f.readLine()
                found = False
                while not line.isNull():
                    nodeid,x,y = str(line).split()
                    line = f.readLine()
                    if str(node.id) == nodeid:
                        node.setPos(float(x), float(y))
                        found = True
                if not found:
                    node.setPos(randint(minX,maxX), randint(minY,maxY))
            f.close()
        
    def itemMoved(self): pass
    
    def disableAllLinks(self):
        log.debug("disableAllLinks")
        for e in self.links:
            e.setLinkDown()
            e.update()

    def enableAllLinks(self):
        log.debug("enableAllLinks")
        for e in self.links:
            e.setLinkUp()
            e.update()

    def disableAllNodes(self):
        log.debug("disableAllNodes")
        for n in self.nodes:
            n.bringSwitchDown()
            n.update()

    def enableAllNodes(self):
        log.debug("enableAllNodes")
        for n in self.nodes:
            n.bringSwitchUp()
            n.update()

    def updateAllNodes(self):
        '''
        Refresh all Nodes
        '''
        log.debug("updateAllNodes")
        for n in self.nodes.values():
            n.update()
            
    def updateAllLinks(self):
        '''
        Refresh all Links
        '''
        for e in self.links:
            e.update()
            e.adjust()
            
    def updateAll(self):
        '''
        Refresh all Items
        '''
        self.updateAllNodes()
        self.updateAllLinks()
            
    def keyPressEvent(self, event):
        '''
        Topology View hotkeys
        '''
        key = event.key()
        #log.debug("keyPressEvent: key = "+str(key))
        if key == QtCore.Qt.Key_Plus:
            self.scaleView(1.2)
        elif key == QtCore.Qt.Key_Minus:
            self.scaleView(1 / 1.2)
        elif key == QtCore.Qt.Key_N:
            self.toggleNodes()
        elif key == QtCore.Qt.Key_I:
            self.toggleNodeIDs()
        elif key == QtCore.Qt.Key_K:
            self.toggleLinks()
        elif key == QtCore.Qt.Key_L:
            # Backend counts a biderctional link as 2 links, so IDs overlap
            self.toggleLinkIDs()
            self.updateAllLinks()
        elif key == QtCore.Qt.Key_P:
            self.togglePorts()
            self.updateAllLinks()
        elif key == QtCore.Qt.Key_H:
            self.toggleHosts()
            self.updateAllNodes()
        elif key == QtCore.Qt.Key_Space or key == QtCore.Qt.Key_Enter:
            # Redraw topology
            self.positionNodes(self.nodes.values())
            self.updateAll()
        else:
            QtGui.QGraphicsView.keyPressEvent(self, event)
    '''
    Toggle display of drawn items
    '''
    def toggleNodes(self):
        log.debug("toggleNodes")
        for node in self.nodes.values():
            node.showNode = not node.showNode
            node.update()
            
    def toggleNodeIDs(self):
        log.debug("toggleNodeIDs")
        for node in self.nodes.values():
            node.showID = not node.showID
            node.update()            

    def toggleLinks(self):
        log.debug("toggleLinks")
        for link in self.links:
            link.showLink = not link.showLink
            link.update()
            
    def toggleLinkIDs(self):
        log.debug("toggleLinkIDs")
        for link in self.links:
            link.showID = not link.showID
            link.update()
            
    def togglePorts(self):
        log.debug("togglePorts")
        for link in self.links:
            link.showPorts = not link.showPorts
            link.update()
            
    def toggleHosts(self):
        log.debug("toggleHosts")        
        for node in self.nodes.values():
            if node.layer == 3:
                for l in node.linkList:
                    l.showLink = not l.showLink
                    l.update()
                node.showID = not node.showID
                node.showNode = not node.showNode
                node.update()

    def drawBackground(self, painter, rect):
        '''
        Draw background. For now just some text
        '''
        sceneRect = self.sceneRect()
        textRect = QtCore.QRectF(sceneRect.left() -5, sceneRect.top() + 60,
                                 sceneRect.width() - 4, sceneRect.height() - 4)
        
        message = self.tr("Topology")
        font = painter.font()
        font.setPointSize(12)
        painter.setFont(font)
        painter.setPen(QtCore.Qt.darkGray)
        painter.drawText(textRect.translated(20.8, 5.8), message)
        painter.setPen(QtCore.Qt.white)
        painter.setPen(QtGui.QColor(QtCore.Qt.gray).light(130))
        painter.drawText(textRect.translated(20, 5), message)
                
    def wheelEvent(self, event):
        '''
        Zoom
        '''
        log.debug("wheelEvent")
        self.scaleView(math.pow(2.0, event.delta() / 300.0))
        
    def scaleView(self, scaleFactor):
        log.debug("scaleView by scaleFactor "+str(scaleFactor))
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
                popup.addAction("Load State", self.loadState)
                popup.addAction("Save State", self.saveState)
                popup.addAction("Create Switch", self.createSwitch)
                popup.exec_(event.globalPos())
        QtGui.QGraphicsView.mouseReleaseEvent(self, event)
    
    def saveState(self):
        '''
        Save all JSON serialized entities of both the STS and GUI topologies to a file
        '''
        
        nodelines = []
        linklines = []
        
        for node in self.nodes.values():
          sts_node = self.getSTSNode(node)
          
          if node.type=="host":
            '''
            Host
            Format: ("h", hostID, hostNumber, hostName, hostInterfaces, hostPosition) 
            Example:
              (1) hostID (Gui)            = (00:00:00:01:00:01)
              (2) hostNumber (Gui)        = 6
              (3) hostName (STS)          = host:[IPAddr('123.1.0.1')]
              (4) hostInterfaces (STS)    = [(00:00:00:01:00:01,['123.1.0.1'],eth2)]
              (5) hostPosition (Gui)      = (-60.0,20.0)
            '''
            hostID = node.id
            hostNumber = node.number
            hostName = sts_node.name
            
            # For each interface, save a list of tuple (MAC address, IP addresses list, name)
            hostInterfaces = json.dumps([
                                json.dumps((str(i.hw_addr),
                                            json.dumps([str(ip) for ip in i.ips]),
                                            i.name))  
                                    for i in sts_node.interfaces])
            hostPosition = json.dumps((round(node.x(), 2),
                                       round(node.y(), 2)))
            
            line = json.dumps(("h", hostID, hostNumber, hostName, hostInterfaces, hostPosition))
            nodelines.append(line)
            
          elif node.type=="switch":
            '''
            Switch
            Format: ("s", switchID, switchNumber, switchName, switchPorts,
                            switchCanConnectToEndHosts, switchPosition) 
            Example:
              (1) switchID (Gui)                        = 5
              (2) switchNumber (Gui)                    = 4
              (3) switchName (STS)                      = SoftSwitch(5)
              (4) switchPorts (STS)                     = [(00:00:00:00:05:01,1.1.5.1,1)]
              (5) switchCanConnectToEndHosts (STS)      = True
              (6) switchPosition (Gui)                  = (-10.0,80.0)
            ''' 
            switchID = node.id
            switchNumber = node.number
            switchName = sts_node.name
            switchPorts = json.dumps([
                            json.dumps((str(p.hw_addr),
                                        str(p.ip_addr) if hasattr(p, "ip_addr") else "",
                                        str(p.port_no)))
                              for p in sts_node.ports.values()])
            switchCanConnectToEndHosts = sts_node.can_connect_to_endhosts
            switchPosition = json.dumps((round(node.x(), 2),
                                         round(node.y(), 2)))
            
            line = json.dumps(("s", switchID, switchNumber, switchName, switchPorts, switchCanConnectToEndHosts, switchPosition))
            nodelines.append(line)
          else:     # Should never happen
            log.debug("Error in saveState: Node examined is neither switch nor host!")
            return
        
        '''
        Access Link
        Format: ("al", hostID, hostInterfaceMac, switchID, switchPortMac)
        Example:
          (1) hostID (Gui)              = (00:00:00:01:00:01)
          (2) hostInterfaceMac (STS)    = 00:00:00:01:00:01
          (3) switchID (Gui)            = 2
          (4) switchPortMac (STS)       = 00:00:00:00:02:01
        ''' 
        for link in self.sts_topology.access_links:
          hostID = "("+",".join(map(lambda i: str(i.hw_addr), link.host.interfaces))+")"
          hostInterfaceMac = str(link.interface.hw_addr)
          switchID = str(link.switch.dpid)
          switchPortMac = str(link.switch_port.hw_addr)
          line = json.dumps(("al", hostID, hostInterfaceMac, switchID, switchPortMac))
          linklines.append(line)
        
        '''
        Network Link
        Format: ("nl", fromSwitchID, fromPortMac, toSwitchID, toPortMac)
        Example:
          (1) fromSwitchID   = 5
          (2) fromPortMac    = 00:00:00:00:05:01
          (3) toSwitchID     = 3
          (4) toPortMac      = 00:00:00:00:03:02
          ''' 
        for link in self.sts_topology.network_links:
          fromSwitchID = str(link.start_software_switch.dpid)
          fromPortMac = str(link.start_port.hw_addr)
          toSwitchID = str(link.end_software_switch.dpid)
          toPortMac = str(link.end_port.hw_addr)
          line = json.dumps(("nl", fromSwitchID, fromPortMac, toSwitchID, toPortMac))
          linklines.append(line)
        
        title = "Specify file to store topology state"
        filename = QtGui.QFileDialog.getSaveFileName(self,title,"gui/layouts")
        f = QtCore.QFile(filename)
        f.open(QtCore.QIODevice.WriteOnly)

        for line in nodelines: f.write(QtCore.QByteArray(line+"\n"))
        for line in linklines: f.write(QtCore.QByteArray(line+"\n"))
        f.close()
        
    def loadState(self):
        '''
        Load all JSON serialized entities of both the STS and GUI topologies from a file
        '''
        title = "Load topology layout from file"
        filename = QtGui.QFileDialog.getOpenFileName(self,title,"gui/layouts")
        f = QtCore.QFile(filename)
        if not f.open(QtCore.QIODevice.ReadOnly):
          log.debug("Error in loadState: Cannot open specified file!")
          return
        line = f.readLine()
        
        if line.isNull():
          log.debug("Error in loadState: Empty file!")
          return
        
        new_gui_nodes = {}
        new_gui_links = []
        
        new_sts_hosts = []
        new_sts_dpid2switch = {}
        new_sts_port2access_link = {}
        new_sts_interface2access_link = {}
        new_sts_port2internal_link = {}
        
        while not line.isNull():
        
          components = json.loads(str(line))
          
          if components[0]=="h":
            '''
            Host: ("h", hostID, hostNumber, hostName, hostInterfaces, hostPosition)
            
            3 things to unpack from json:
                1) List of interfaces
                2) (Mac address, IP address list, name) tuple for each interface, and
                3) list of IP addresses
            '''
            interfaces = []
            interface_info = [json.loads(info) for info in json.loads(components[4])]
            for hw_addr, ips, name in interface_info:
              ips = [IPAddr(str(ip)) for ip in json.loads(str(ips))]
              interface = HostInterface(EthAddr(hw_addr), ips, name)
              interfaces.append(interface)
            
            hostID = components[1]
            hostNumber = components[2]
            hostName = components[3]
            hostPosition = json.loads(components[5])
            
            gui_host = Node(self, hostID, hostNumber, "host")
            gui_host.setPos(int(hostPosition[0]), int(hostPosition[1]))
            new_gui_nodes[hostID] = gui_host
            
            sts_host = Host(interfaces, hostName)
            new_sts_hosts.append(sts_host)
            
          elif components[0]=="s":
            '''
            Switch: ("s", switchID, switchNumber, switchName, switchPorts,
                            switchCanConnectToEndHosts, switchPosition) 
            '''
            ports = []
            
            port_info = [json.loads(info) for info in json.loads(components[4])]
            for hw_addr, ip_addr, port_no in port_info:
              port = ofp_phy_port( port_no=int(port_no), hw_addr=EthAddr(str(hw_addr)) )
              if ip_addr!=None and str(ip_addr)!="":
                port.ip_addr = IPAddr(str(ip_addr))
              ports.append(port)
            
            switchID = components[1]
            switchNumber = components[2]
            switchName = components[3]
            switchCanConnectToEndHosts = components[5]=="True"
            switchPosition = json.loads(components[6])
            
            gui_switch = Node(self, switchID, switchNumber, "switch")
            gui_switch.setPos(int(switchPosition[0]), int(switchPosition[1]))
            new_gui_nodes[switchID] = gui_switch
            
            sts_switch = FuzzSoftwareSwitch(dpid=int(switchID), name=switchName, ports=ports,
                                            can_connect_to_endhosts=switchCanConnectToEndHosts)
            new_sts_dpid2switch[int(switchID)] = sts_switch
        
          elif components[0]=="al":
            '''
            Access Link: ("al", hostID, hostInterfaceMac, switchID, switchPortMac)
            '''
            hostID = components[1]
            hostInterfaceMac = components[2]
            switchID = components[3]
            switchPortMac = components[4]
            
            sts_host = None
            sts_hostInterface = None
            sts_switch = None
            sts_switchPort = None
            
            for host in new_sts_hosts:
              if hostID=="("+",".join(map(lambda i: str(i.hw_addr), host.interfaces))+")":
                sts_host = host
                for interface in host.interfaces:
                  if hostInterfaceMac==str(interface.hw_addr): sts_hostInterface = interface
            
            if int(switchID) in new_sts_dpid2switch.keys():
              sts_switch = new_sts_dpid2switch[int(switchID)]
              for port in sts_switch.ports.values():
                if str(port.hw_addr)==switchPortMac: sts_switchPort = port
            
            if sts_host==None or sts_hostInterface==None or sts_switch==None or sts_switchPort==None:
              log.debug("Error in loadState: Access link cannot be created!")
              return
          
            sts_link = AccessLink(sts_host, sts_hostInterface, sts_switch, sts_switchPort)
            new_sts_interface2access_link[sts_hostInterface] = sts_link
            new_sts_port2access_link[sts_switchPort] = sts_link
            
            gui_link = Link(self, new_gui_nodes[hostID], new_gui_nodes[switchID], 0, 0, 0)
            new_gui_links.append(gui_link)
            
          elif components[0]=="nl":
            '''  
            Network Link: ("nl", fromSwitchID, fromPortMac, toSwitchID, toPortMac)
            '''
            fromSwitchID = components[1]
            fromPortMac = components[2]
            toSwitchID = components[3]
            toPortMac = components[4]
            
            sts_fromSwitch = None
            sts_fromPort = None
            sts_toSwitch = None
            sts_toPort = None
            
            if int(fromSwitchID) in new_sts_dpid2switch.keys():
              sts_fromSwitch = new_sts_dpid2switch[int(fromSwitchID)]
              for port in sts_fromSwitch.ports.values():
                if str(port.hw_addr)==fromPortMac: sts_fromPort = port
              sts_toSwitch = new_sts_dpid2switch[int(toSwitchID)]
              for port in sts_toSwitch.ports.values():
                if str(port.hw_addr)==toPortMac: sts_toPort = port
            
            if sts_fromSwitch==None or sts_fromPort==None or\
                sts_toSwitch==None and sts_toPort==None:
              log.debug("Error in loadState: Network link cannot be created!")
              return
                
            sts_link = NetworkLink(sts_fromSwitch, sts_fromPort, sts_toSwitch, sts_toPort)
            new_sts_port2internal_link[sts_fromPort] = sts_link
            
            gui_link = Link(self, new_gui_nodes[fromSwitchID], new_gui_nodes[toSwitchID], 0, 0, 0)
            new_gui_links.append(gui_link)
            
          else: log.debug("Error in loadState: Unparseable line detected!")
          line = f.readLine()
        
        f.close()
        
        '''
        Essentially restart the entire topology in both GUI and STS
        '''
        
        self.sts_topology.hosts = new_sts_hosts
        self.sts_topology.dpid2switch = new_sts_dpid2switch
        self.sts_topology.link_tracker.dpid2switch = new_sts_dpid2switch
        self.sts_topology.link_tracker.port2access_link = new_sts_port2access_link
        self.sts_topology.link_tracker.interface2access_link = new_sts_interface2access_link
        self.sts_topology.link_tracker.port2internal_link = new_sts_port2internal_link
        
        for nodeID in self.nodes.keys():
          if self.nodes[nodeID] in self.topoScene.items():
            self.topoScene.removeItem(self.nodes[nodeID])
            del self.nodes[nodeID]
        self.nodes = new_gui_nodes
        for node in self.nodes.values(): self.topoScene.addItem(node)
        
        for link in self.links:
          if link in self.topoScene.items():
            self.topoScene.removeItem(link)
        self.links = new_gui_links
        for link in self.links: self.topoScene.addItem(link)

class Node(QtGui.QGraphicsItem):
    '''
    Interactive Node object
        If node is switch, then id = the switch's dpid;
        else, id = string form of the host's list of MAC addresses
    '''
    Type = QtGui.QGraphicsItem.UserType + 1
     
    def __init__(self, graphWidget, _id, _number, _type, _layer=1):
        QtGui.QGraphicsItem.__init__(self)

        self.graph = graphWidget
        self.topoWidget = self.graph.parent
        self.id = _id
        self.number = _number
        self.type = _type
        self.linkList = []
        self.neighbors = {}  # "str(port) : str(neigh.ID)"
        self.newPos = QtCore.QPointF()
        self.setFlag(QtGui.QGraphicsItem.ItemIsMovable)
        self.setFlag(QtGui.QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(1)
        self.setAcceptHoverEvents(True)
        
        # Node attributes
        self.isUp = True        # up/down state   
        self.showNumber = True  # Draw node number
        self.showNode = True    # Draw node
        self.isSilent = False   # is switch unresponsive? - draw X
        
    def type(self):
        return Node.Type

    def addLink(self, link):
        self.linkList.append(link)
        
        # create localPort->neighborID mapping
        if link.source.id == self.id:
            neibID = link.dest.id
        else:
            neibID = link.source.id
        
        self.neighbors[link.dport] = neibID
        link.adjust()

    def links(self):
        return self.linkList

        self.setPos(self.newPos)
        return True

    def boundingRect(self):
        adjust = 2.0
        return QtCore.QRectF(-10-adjust, -10-adjust, 23+adjust, 23+adjust)

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
                if self.isUp:
                    gradient.setColorAt(1, color.light(100))
                    gradient.setColorAt(0, color.light(30))
                else:
                    gradient.setColorAt(1, QtGui.QColor(QtCore.Qt.gray).light(80))
                    gradient.setColorAt(0, QtGui.QColor(QtCore.Qt.gray).light(20))
            else:
                if self.isUp:
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
            textRect = self.boundingRect()
            message = str(self.number)

            font = painter.font()
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QtCore.Qt.gray)
            painter.drawText(textRect.translated(0.1, 0.1), message)
            painter.setPen(QtGui.QColor(QtCore.Qt.gray).light(130))
            painter.drawText(textRect.translated(0, 0), message)
        
        if self.isSilent: # remove
            # Big red X.
            textRect = self.boundingRect()
            message = "X"

            font = painter.font()
            font.setBold(True)
            font.setPointSize(16)
            painter.setFont(font)
            painter.setPen(QtGui.QColor(QtCore.Qt.red).light(30))
            painter.drawText(textRect.translated(4, 2), message)
            painter.setPen(QtGui.QColor(QtCore.Qt.red).light(90))
            painter.drawText(textRect.translated(3, 1), message)

    def itemChange(self, change, value):
        if change == QtGui.QGraphicsItem.ItemPositionChange:
            for link in self.linkList:
                link.adjust()
            self.graph.itemMoved()

        return QtGui.QGraphicsItem.itemChange(self, change, value)

    def mousePressEvent(self, event):
        self.stillHover = False
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
              
              def createLinkLambda(fromID, toID):
                  return lambda: self.graph.createLink(fromID, toID)
              
              for node in sorted(self.graph.nodes.values()):
                if node==self: continue
                for link in self.linkList:
                  if (link.source==self and link.dest==node) or\
                        (link.source==node and link.dest==self and node.type=="host"): break
                else: linkToMenu.addAction(str(node.number), createLinkLambda(self.id, node.id))
              popup.addMenu(linkToMenu)
            # Host Details Menu
            if self.type == "host":
                popup.addMenu(self.nodeDetails)
                
            popup.exec_(event.lastScreenPos())
        self.update()
        QtGui.QGraphicsItem.mouseReleaseEvent(self, event)
            
    def bringSwitchDown(self):
        log.debug("Node.bringSwitchDown")
        self.isUp = False
        for l in self.linkList:
            l.isUp = False
            l.update()
        self.update()

    def bringSwitchUp(self, allLinks = True):
        log.debug("Node.bringSwitchUp")
        self.isUp = True
        if allLinks:
            for l in self.linkList:
                l.isUp = True
                l.update()
        self.update()
       
    def hoverEnterEvent(self, event):
        self.stillHover = True
        
        # refresh nodeDetails menu
        self.nodeDetails = QtGui.QMenu('&Node Details')
        if self.type == "switch":
            self.nodeDetails.addAction('Datapath ID: 0x%s' % self.id)
            self.nodeDetails.addAction('Table Size: '+ '')
        elif self.type == "host":
            self.nodeDetails.addAction('Host ID: 0x%s' % self.id)
        self.nodeDetails.addAction('Links: ' + str(len(self.linkList)))
        
        self.hoverPos = event.lastScreenPos() + QtCore.QPoint(10,10)
        self.hoverTimer = QtCore.QTimer()
        self.hoverTimer.singleShot(500, self.popupNodeDetailsMenu)
    
    @QtCore.pyqtSlot()    
    def popupNodeDetailsMenu(self):
        if self.stillHover:
            #pos = self.mapToItem(self,self.pos() + QtCore.QPointF(10,10))
            self.nodeDetails.exec_(self.hoverPos)
        
    def hoverLeaveEvent(self, event):
        self.stillHover = False
        # hide popup...(currently user has to click somewhere)
        
class Link(QtGui.QGraphicsItem):
    '''
    Interactive Link 
    '''    
    Type = QtGui.QGraphicsItem.UserType + 2

    def __init__(self, graphWidget, sourceNode, destNode, sport, dport, uid):
        #log.debug("Link.__init__ with uid="+str(uid)+", sourceNode="+str(sourceNode)+", destNode="+str(destNode))
        QtGui.QGraphicsItem.__init__(self)
        
        self.graph = graphWidget
        self.topoWidget = self.graph.parent
        self.uid = uid
        self.arrowSize = 10.0
        self.sourcePoint = QtCore.QPointF()
        self.destPoint = QtCore.QPointF()
        self.setFlag(QtGui.QGraphicsItem.ItemIsMovable)
        self.setAcceptedMouseButtons(QtCore.Qt.RightButton)
        self.setAcceptHoverEvents(False)
        self.source = sourceNode
        self.dest = destNode
        self.sport = sport
        self.dport = dport
        self.drawArrow = False
        self.source.addLink(self)
        self.dest.addLink(self)
        self.adjust()
        
        # Link attributes
        self.isUp = True        # up/down state  
        self.showLink = True    # Draw link
        self.showID = False     # Draw link ID   
        self.showPorts = True   # Draw connecting ports  
        
        # Link details menu
        self.linkDetails = QtGui.QMenu('&Link Details')
        self.linkDetails.addAction('Link ID: %s'%self.uid)
        self.linkDetails.addAction("Ends: %s:%s - %s:%s"%(self.source.id,
                                   self.sport, self.dest.id, self.dport))
        self.linkDetails.addAction('Capacity: ')

    def type(self):
        return Link.Type

    def sourceNode(self):
        return self.source

    def setSourceNode(self, node):
        self.source = node
        self.adjust()

    def destNode(self):
        return self.dest

    def setDestNode(self, node):
        self.dest = node
        self.adjust()

    def adjust(self):
        if not self.source or not self.dest:
            return

        line = QtCore.QLineF(self.mapFromItem(self.source, 0, 0),\
                                self.mapFromItem(self.dest, 0, 0))
        length = line.length()
        
        if length == 0.0:
            return
        
        linkOffset = QtCore.QPointF((line.dx() * 10) / length, (line.dy() * 10) / length)

        self.prepareGeometryChange()
        self.sourcePoint = line.p1() + linkOffset
        self.destPoint = line.p2() - linkOffset

    def boundingRect(self):
        if not self.source or not self.dest:
            return QtCore.QRectF()
        '''
        return QtCore.QRectF(self.sourcePoint,
                             QtCore.QSizeF(self.destPoint.x() - self.sourcePoint.x(),
                                           self.destPoint.y() - self.sourcePoint.y())).normalized()
        
        '''
        penWidth = 1
        extra = (penWidth + self.arrowSize) / 2.0

        return QtCore.QRectF(self.sourcePoint,
                             QtCore.QSizeF(self.destPoint.x() - self.sourcePoint.x(),
                                           self.destPoint.y() - self.sourcePoint.y())).normalized().adjusted(-extra, -extra, extra, extra)
        
        
    def paint(self, painter, option, widget):
        #log.debug("Link.paint")
        if not self.source or not self.dest:
            return

        # Draw the line itself.
        if self.showLink:
            line = QtCore.QLineF(self.sourcePoint, self.destPoint)
            if line.length() == 0.0:
                return
            
            color = QtCore.Qt.gray
            pattern = QtCore.Qt.SolidLine
            
            # Select pen for line (color for util, pattern for state)
            if self.isUp:
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
                angle = 2*math.pi - angle

            destArrowP1 = self.destPoint + \
                QtCore.QPointF(math.sin(angle-math.pi/3)*self.arrowSize,
                math.cos(angle-math.pi/3)*self.arrowSize)
            destArrowP2 = self.destPoint + \
                QtCore.QPointF(math.sin(angle-math.pi+math.pi/3)*self.arrowSize,
                math.cos(angle-math.pi+math.pi/3)*self.arrowSize)
            
            if self.drawArrow:
                painter.setBrush(color)
                painter.drawPolygon(QtGui.QPolygonF([line.p2(), \
                    destArrowP1, destArrowP2]))
        
    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.RightButton:
            popup = QtGui.QMenu()
            popup.addMenu(self.linkDetails)
            popup.exec_(event.lastScreenPos())
        self.update()
        QtGui.QGraphicsItem.mouseReleaseEvent(self, event)

    def setLinkUp(self):
        log.debug("Link.setLinkUp")
        self.isUp = True
        self.update()

    def setLinkDown(self):
        log.debug("Link.setLinkDown")
        self.isUp = False
        self.update()
