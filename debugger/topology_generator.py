
# Nom nom nom nom

'''
If the user does not specify a topology to test on, use by default a full mesh
of switches, with one host connected to each switch. For example, with N = 3:

              controller
     host1                         host2
       |                            |
     switch1-(1)------------(3)--switch2
        \                       /
        (2)                   (4)
          \                   /
           \                 /
            \               /
             (6)-switch3-(5)
                    |
                  host3
'''

from debugger_entities import FuzzSwitchImpl, Link, Host, HostInterface, AccessLink
from pox.openflow.switch_impl import ofp_phy_port, DpPacketOut
from pox.lib.addresses import EthAddr, IPAddr
from pox.lib.util import connect_socket_with_backoff
from pox.lib.revent import EventMixin
import socket
import time
import errno
import sys
import itertools

class Cycler():
  """
  Abstraction for cycling through the given list circularly:

  c = Cycler([1,2,3])
  while True:
    print c.next()
  """
  def __init__(self, arr):
    self._list = list(arr)
    self._current_index = 0

  def next(self):
    if len(self._list) == 0:
      return None

    element = self._list[self._current_index]
    self._current_index += 1
    self._current_index %= len(self._list)
    return element

def create_switch(switch_id, num_ports):
  ports = []
  for port_no in range(1, num_ports+1):
    port = ofp_phy_port( port_no=port_no,
                          hw_addr=EthAddr("00:00:00:00:%02x:%02x" % (switch_id, port_no)) )
    # monkey patch an IP address onto the port for anteater purposes
    port.ip_addr = "1.1.%d.%d" % (switch_id, port_no)
    ports.append(port)

  def unitialized_io_worker(switch):
    raise SystemError("Not initialialized")

  return FuzzSwitchImpl(create_io_worker=unitialized_io_worker, dpid=switch_id, name="SoftSwitch(%d)" % switch_id, ports=ports)

def get_switchs_host_port(switch):
  ''' return the switch's ofp_phy_port connected to the host '''
  # We wire up the last port of the switch to the host
  return switch.ports[sorted(switch.ports.keys())[-1]]

def create_host(ingress_switch_or_switches):
  ''' Create a Host, wired up to the given ingress switches '''
  switches = ingress_switch_or_switches
  if type(switches) != list:
    switches = [ingress_switch_or_switches]
  
  interfaces = []
  interface_switch_pairs = []
  for switch in switches:
    port = get_switchs_host_port(switch)
    mac = EthAddr("12:34:56:78:%02x:%02x" % (switch.dpid, port.port_no)) 
    ip_addr = IPAddr("123.123.%d.%d" % (switch.dpid, port.port_no))
    name = "eth%d" % switch.dpid
    interface = HostInterface(mac, ip_addr, name)
    interface_switch_pairs.append((interface, switch))
    interfaces.append(interface)
    
  name = "host:" + ",".join(map(lambda switch: "%d" % switch.dpid, switches))
  host = Host(interfaces, name)
  access_links = [ AccessLink(host, interface, switch, get_switchs_host_port(switch)) for interface, switch in interface_switch_pairs ] 
  return (host, access_links)

def create_mesh(num_switches):
  ''' Returns (patch_panel, switches, network_links, hosts, access_links) '''
  
  # Every switch has a link to every other switch + 1 host, for N*(N-1)+N = N^2 total ports
  ports_per_switch = (num_switches - 1) + 1

  # Initialize switches
  switches = [ create_switch(switch_id, ports_per_switch) for switch_id in range(1, num_switches+1) ]
  host_access_link_pairs = [ create_host(switch) for switch in switches ]
  hosts = map(lambda pair: pair[0], host_access_link_pairs)
  access_link_list_list = map(lambda pair: pair[1], host_access_link_pairs)
  # this is python's .flatten:
  access_links = list(itertools.chain.from_iterable(access_link_list_list))
  
  # grab a fully meshed patch panel to wire up these guys
  link_topology = FullyMeshedLinks(switches, access_links)
  patch_panel = BufferedPatchPanel(switches, hosts, link_topology.get_connected_port)
  network_links = link_topology.get_network_links()

  return (patch_panel, switches, network_links, hosts, access_links)

def connect_to_controllers(controller_info_list, io_worker_generator, switch_impls):
  '''
  Bind sockets from the switch_impls to the controllers. For now, assign each switch to the next
  controller in the list in a round robin fashion.
  
  Controller info list is a list of (controller ip address, controller port number) tuples
  
  Return a list of socket objects
  '''
  controller_info_cycler = Cycler(controller_info_list)

  for switch_impl in switch_impls:
    # TODO: what if the controller is slow to boot?
    # Socket from the switch_impl to the controller
    controller_info = controller_info_cycler.next()
    def create_io_worker(switch):
      controller_socket = connect_socket_with_backoff(controller_info.address, controller_info.port)
      # Set non-blocking
      controller_socket.setblocking(0)
      return io_worker_generator(controller_socket)

    switch_impl.create_io_worker = create_io_worker
    switch_impl.connect()

def populate(controller_config_list, io_worker_constructor, num_switches=3):
  '''
  Populate the topology as a mesh of switches, connect the switches
  to the controllers, and return
  (PatchPanel, switches, network_links, hosts, access_links)
  '''
  (panel, switches, network_links, hosts, access_links) = create_mesh(num_switches)
  connect_to_controllers(controller_config_list, io_worker_constructor, switches)
  return (panel, switches, network_links, hosts, access_links) 

class PatchPanel(object):
  """ A Patch panel. Contains a bunch of wires to forward packets between switches.
      Listens to the SwitchDPPacketOut event on the switches.
  """
  def __init__(self, switches, hosts, connected_port_mapping):
    '''
    Constructor.
     - switches: a list of the switches in the network
     - hosts: a list of hosts in the network
     - connected_port_mapping: a function which takes (switch_no, port_no, dpid2switch),
                               and returns the adjacent (node, port) or None
    '''
    self.switches = sorted(switches, key=lambda(sw): sw.dpid)
    self.get_connected_port = connected_port_mapping
    self.hosts = hosts
    for i, s in enumerate(self.switches):
      s.addListener(DpPacketOut, self.handle_DpPacketOut)
    for host in self.hosts:
      host.addListener(DpPacketOut, self.handle_DpPacketOut)
      
  def handle_DpPacketOut(self, event):
    (node, port) = self.get_connected_port(event.node, event.port)
    if type(node) == Host:
      self.deliver_packet(node, event.packet, port)
    else:
      self.forward_packet(node, event.packet, port)
           
  def get_connected_port(self, node, port):
    return self.get_connected_port(node, port)
  
  def forward_packet(self, next_switch, packet, next_port):
    ''' Forward the packet to the given port '''
    next_switch.process_packet(packet, next_port.port_no)
      
  def deliver_packet(self, host, packet, host_interface):
    ''' Deliver the packet to its final destination '''
    host.receive(host_interface, packet)

class BufferedPatchPanel(PatchPanel, EventMixin):
  '''
  A Buffered Patch panel.Listens to SwitchDPPacketOut and HostDpPacketOut events,
  and re-raises them to listeners of this object. Does not traffic until given
  permission from a higher-level.
  '''
  _eventMixin_events = set([DpPacketOut])

  def __init__(self, switches, hosts, connected_port_mapping):
    self.get_connected_port = connected_port_mapping
    self.switches = sorted(switches, key=lambda(sw): sw.dpid)
    self.hosts = hosts
    self.buffered_dp_out_events = set()
    def handle_DpPacketOut(event):
      self.buffered_dp_out_events.add(event)
      self.raiseEventNoErrors(event)
    for i, s in enumerate(self.switches):
      s.addListener(DpPacketOut, handle_DpPacketOut)
    for host in self.hosts:
      host.addListener(DpPacketOut, handle_DpPacketOut)
      
  def permit_dp_event(self, event):
    ''' Given a SwitchDpPacketOut event, permit it to be forwarded  ''' 
    # TODO: self.forward_packet should not be externally visible!
    # Superclass DpPacketOut handler
    self.handle_DpPacketOut(event)
    self.buffered_dp_out_events.remove(event)
    
  def drop_dp_event(self, event):
    '''
    Given a SwitchDpPacketOut event, remove it from our buffer, and do not forward.
    Return the dropped event.
    ''' 
    self.buffered_dp_out_events.remove(event)
    return event
    
  def get_buffered_dp_events(self):
    ''' Return a set of all buffered SwitchDpPacketOut events ''' 
    return self.buffered_dp_out_events
     
class FullyMeshedLinks(object):
  """ A factory method for creating a fully meshed network. Connects every pair of switches. Ports are
      in ascending order of the dpid of connected switch, while skipping the self-connections.
      I.e., for (dpid, portno):
      (0, 0) <-> (1,0)
      (2, 1) <-> (1,1)
  """
  def __init__(self, switches, access_links=[]):
    self.switches = sorted(switches, key=lambda(sw): sw.dpid)
    self.switch_index_by_dpid = {}
    for i, s in enumerate(switches):
      self.switch_index_by_dpid[s.dpid] = i
    self.port2access_link = {}
    self.interface2access_link = {}
    for access_link in access_links:
      self.port2access_link[access_link.switch_port] = access_link
      self.interface2access_link[access_link.interface] = access_link
      
  def get_connected_port(self, node, port):
    ''' Given a node and a port, return a tuple (node, port) that is directly connected to the port '''
    if port in self.port2access_link:
      access_link = self.port2access_link[port]
      return (access_link.host, access_link.interface)
    if port in self.interface2access_link:
      access_link = self.interface2access_link[port]
      return (access_link.switch, access_link.switch_port)
    else:
      switch_no = self.switch_index_by_dpid[node.dpid]
      # when converting between switch and port, compensate for the skipped self port
      port_no = port.port_no - 1
      other_switch_no = port_no if port_no < switch_no else port_no + 1
      other_port_no = switch_no if switch_no < other_switch_no else switch_no - 1

      other_switch = self.switches[other_switch_no]
      return (other_switch, other_switch.ports[other_port_no+1])
  
  def get_network_links(self):
    ''' Return a list of all directed Link objects in the mesh '''
    # memoize the result 
    if hasattr(self, "all_network_links"):
      return self.all_network_links
    self.all_network_links = [] 
    for switch in self.switches:
      for port in set(switch.ports.values()) - set([get_switchs_host_port(switch)]):
        (other_switch, other_port) =  self.get_connected_port(switch, port)
        self.all_network_links.append(Link(switch, port, other_switch, other_port))
    return self.all_network_links
    
