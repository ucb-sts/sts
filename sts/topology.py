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
from pox.openflow.switch_impl import ofp_phy_port, DpPacketOut, SwitchImpl
from pox.lib.addresses import EthAddr, IPAddr
from pox.openflow.libopenflow_01 import *
from pox.lib.util import connect_socket_with_backoff
from pox.lib.revent import EventMixin
import socket
import abc
import time
import errno
import sys
import itertools
import logging

logger = logging.getLogger("sts.topology_generator")

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

def create_host(ingress_switch_or_switches, mac_or_macs=None, ip_or_ips=None, get_switch_port=get_switchs_host_port):
  ''' Create a Host, wired up to the given ingress switches '''
  switches = ingress_switch_or_switches
  if type(switches) != list:
    switches = [ingress_switch_or_switches]

  macs = mac_or_macs
  if mac_or_macs and type(mac_or_macs) != list:
    macs = [mac_or_macs]

  ips = ip_or_ips
  if ip_or_ips and type(ip_or_ips) != list:
    ips = [ip_or_ips]

  interfaces = []
  interface_switch_pairs = []
  for switch in switches:
    port = get_switch_port(switch)
    if macs:
      mac = macs.pop(0)
    else:
      mac = EthAddr("12:34:56:78:%02x:%02x" % (switch.dpid, port.port_no))
    if ips:
      ip_addr = ips.pop(0)
    else:
      ip_addr = IPAddr("123.123.2.2") #hard coded for measurement (irrelevant)

    name = "eth%d" % switch.dpid
    interface = HostInterface(mac, ip_addr, name)
    interface_switch_pairs.append((interface, switch))
    interfaces.append(interface)

  name = "host:" + ",".join(map(lambda interface: "%s" % str(interface.ips), interfaces)) 
  host = Host(interfaces, name)
  access_links = [ AccessLink(host, interface, switch, get_switch_port(switch)) for interface, switch in interface_switch_pairs ]
  return (host, access_links)

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
    if type(next_port) != int:
      next_port = next_port.port_no
    next_switch.process_packet(packet, next_port)

  def deliver_packet(self, host, packet, host_interface):
    ''' Deliver the packet to its final destination '''
    host.receive(host_interface, packet)

def BufferedPatchPanelForTopology(topology):
  """
  Given a pox.lib.graph.graph object with hosts, switches, and other things,
  produce an appropriate BufferedPatchPanel
  """
  return BufferedPatchPanel(topology.find(is_a=SwitchImpl), topology.find(is_a=Host), \
                            lambda node, port:topology.port_for_node(node, port))

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
    # TODO(cs): self.forward_packet should not be externally visible!
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

class Topology(object):
  '''
  Abstract base class of all topology types. Wraps the edges and vertices of
  the network.
  '''
  def __init__(self):
    self.switches = []

  # TODO(cs): add a bunch of other methods to kill switches and stuff like that
  def connect_to_controllers(self, controller_info_list, io_worker_generator):
    '''
    Bind sockets from the switch_impls to the controllers. For now, assign each switch to the next
    controller in the list in a round robin fashion.

    Controller info list is a list of (controller ip address, controller port number) tuples

    Return a list of socket objects
    '''
    controller_info_cycler = itertools.cycle(controller_info_list)
    connections_per_switch = len(controller_info_list)

    logger.debug("Connecting %d switches to %d controllers (setting up %d conns per switch)..." %
            (len(switch_impls), len(controller_info_list), connections_per_switch))

    for (idx, switch_impl) in enumerate(self.switches):
      if len(self.switches) < 20 or not idx % 250:
        logger.debug("Connecting switch %d / %d" % (idx, len(self.switches)))

      def create_io_worker(switch, controller_info):
        controller_socket = connect_socket_with_backoff(controller_info.address, controller_info.port)
        # Set non-blocking
        controller_socket.setblocking(0)
        return io_worker_generator(controller_socket)
      switch_impl.create_io_worker = create_io_worker

      # TODO(cs): what if the controller is slow to boot?
      # Socket from the switch_impl to the controller
      for i in xrange(connections_per_switch):
        controller_info = controller_info_cycler.next()
        switch_impl.add_controller_info(controller_info)

      switch_impl.connect()

    logger.debug("Controller connections done")

class MeshTopology(Topology):
  def __init__(self, patch_panel_class, num_switches=3):
    '''
    Populate the topology as a mesh of switches, connect the switches
    to the controllers
    '''
    # Every switch has a link to every other switch + 1 host, for N*(N-1)+N = N^2 total ports
    ports_per_switch = (num_switches - 1) + 1

    # Initialize switches
    self.switches = [ create_switch(switch_id, ports_per_switch) for switch_id in range(1, num_switches+1) ]
    host_access_link_pairs = [ create_host(switch) for switch in switches ]
    self.hosts = map(lambda pair: pair[0], host_access_link_pairs)
    access_link_list_list = map(lambda pair: pair[1], host_access_link_pairs)
    # this is python's .flatten:
    self.access_links = list(itertools.chain.from_iterable(access_link_list_list))

    # grab a fully meshed patch panel to wire up these guys
    link_topology = MeshTopology.FullyMeshedLinks(switches, access_links)
    self.panel = patch_panel_class(switches, hosts, link_topology.get_connected_port)
    self.network_links = link_topology.get_network_links()

  class FullyMeshedLinks(object):
    """ A factory method (inner class) for creating a fully meshed network. Connects every pair
        of switches. Ports are in ascending order of the dpid of connected switch, while skipping
        the self-connections. I.e., for (dpid, portno):
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

class FatTree (Topology):
  ''' Construct a FatTree topology with a given number of pods '''
  def __init__(self, patch_panel_class, num_pods=4):
    if num_pods < 2:
      raise "Can't handle Fat Trees with less than 2 pods"
    self.hosts = []
    self.cores = []
    self.aggs = []
    self.edges = []
    # Note that access links are bi-directional
    self.access_links = set()
    # But internal links are uni-directional?
    self.network_links = set()

    self.switches = []
    self.construct_tree(num_pods)

    self.panel = patch_panel_class(self.switches, self.hosts,
                                   self.get_connected_port)

  def construct_tree(self, num_pods):
    '''
    According to  "A Scalable, Commodity Data Center Network Architecture",
    k = number of ports per switch = number of pods
    number core switches =  (k/2)^2
    number of edge switches per pod = k / 2
    number of agg switches per pod = k / 2
    number of hosts attached to each edge switch = k / 2
    number of hosts per pod = (k/2)^2
    total number of hosts  = k^3 / 4
    '''
    logger.debug("Constructing fat tree with %d pods" % num_pods)

    # self == store these numbers for later
    k = self.k = self.ports_per_switch = self.num_pods = num_pods
    self.hosts_per_pod = self.total_core = (k/2)**2
    self.edge_per_pod = self.agg_per_pod = self.hosts_per_edge = k / 2
    self.total_hosts = self.hosts_per_pod * num_pods

    current_pod_id = -1
    # zero is not a valid dpid -- (first dpid is 0+1)
    current_dpid = 0
    # We construct it from bottom up, starting at host <-> edge
    for i in range(self.total_hosts):
      if not i % 1000:
        logger.debug("Host %d / %d" % (i, self.total_hosts))

      if (i % self.hosts_per_pod) == 0:
        current_pod_id += 1

      if (i % self.hosts_per_edge) == 0:
        current_dpid += 1
        edge_switch = create_switch(current_dpid, self.ports_per_switch)
        edge_switch.pod_id = current_pod_id
        self.edges.append(edge_switch)

      edge = self.edges[-1]
      # edge ports 1 through (k/2) are dedicated to hosts, and (k/2)+1 through k are for agg
      edge_port_no = (i % self.hosts_per_edge) + 1
      # We give it a portland pseudo mac, just for giggles
      # Slightly modified from portland (no vmid, assume 8 bit pod id):
      # 00:00:00:<pod>:<position>:<port>
      # position and pod are 0-indexed, port is 1-indexed
      position = (len(self.edges)-1) % self.edge_per_pod
      edge.position = position
      portland_mac = EthAddr("00:00:00:%02x:%02x:%02x" % (current_pod_id, position, edge_port_no))
      # Uhh, unfortunately, OpenFlow 1.0 doesn't support prefix matching on MAC addresses.
      # So we do prefix matching on IP addresses, which yields exactly the same # of flow
      # entries for HSA, right?
      portland_ip_addr = IPAddr("123.%d.%d.%d" % (current_pod_id, position, edge_port_no))
      (host, host_access_links) = create_host(edge, portland_mac, portland_ip_addr, lambda switch: switch.ports[edge_port_no])
      host.pod_id = current_pod_id
      self.hosts.append(host)
      self.access_links = self.access_links.union(set(host_access_links))

    # Now edge <-> agg
    for pod_id in range(num_pods):
      if not pod_id % 10:
        logger.debug("edge<->agg for pod %d / %d" % (pod_id, num_pods))
      current_aggs = []
      for _ in  range(self.agg_per_pod):
        current_dpid += 1
        agg = create_switch(current_dpid, self.ports_per_switch)
        agg.pod_id = pod_id
        current_aggs.append(agg)

      current_edges = self.edges[pod_id * self.edge_per_pod : (pod_id * self.edge_per_pod) + self.edge_per_pod]
      # edge ports (k/2)+1 through k connect to aggs
      # agg port k+1 connects to edge switch k in the pod
      current_agg_port_no = 1
      for edge in current_edges:
        current_edge_port_no = (k/2)+1
        for agg in current_aggs:
          self.network_links.add(Link(edge, edge.ports[current_edge_port_no], agg, agg.ports[current_agg_port_no]))
          self.network_links.add(Link(agg, agg.ports[current_agg_port_no], edge, edge.ports[current_edge_port_no]))
          current_edge_port_no += 1
        current_agg_port_no += 1

      self.aggs += current_aggs

    # Finally, agg <-> core
    for i in range(self.total_core):
      if not i % 100:
        logger.debug("agg<->core %d / %d" % (i, self.total_core))
      current_dpid += 1
      self.cores.append(create_switch(current_dpid, self.ports_per_switch))

    core_cycler = itertools.cycle(self.cores)
    for agg in self.aggs:
      # agg ports (k/2)+1 through k connect to cores
      # core port i+1 connects to pod i
      for agg_port_no in range(k/2+1, k+1):
        core = core_cycler.next()
        core_port_no = agg.pod_id + 1
        self.network_links.add(Link(agg, agg.ports[agg_port_no], core, core.ports[core_port_no]))
        self.network_links.add(Link(core, core.ports[core_port_no], agg, agg.ports[agg_port_no]))

    self.switches = self.cores + self.aggs + self.edges
    self.wire_tree()
    self._sanity_check_tree()
    logger.debug("Fat tree construction: done (%d cores, %d aggs, %d edges, %d hosts)" %
        (len(self.cores), len(self.aggs), len(self.edges), len(self.hosts)))

  def wire_tree(self):
    # Auxiliary data to make get_connected_port efficient
    self.port2internal_link = {}
    for link in self.network_links:
      #if link.start_port in self.port2internal_link:
        #raise RuntimeError("%s Already there %s" % (str(link), str(self.port2internal_link[link.start_port])))
      self.port2internal_link[link.start_port] = link
      
    # TODO(cs): this should be in a unit test, not here
    #if len(self.port2internal_link) != len(self.network_links):
    #  raise RuntimeError("Not enough port2network_links(%d s/b %d)" % \
    #                    (len(self.port2internal_link), len(self.network_links)))

    self.port2access_link = {}
    self.interface2access_link = {}
    for access_link in self.access_links:
      self.port2access_link[access_link.switch_port] = access_link
      self.interface2access_link[access_link.interface] = access_link
      
    # TODO(cs): this should be in a unit test, not here
    #if len(self.port2access_link) != len(self.access_links):
    #  raise RuntimeError("Not enough port2accesslinks (%d s/b %d)" % \
    #                    (len(self.port2access_link), len(self.access_links)))
      
    # TODO(cs): this should be in a unit test, not here
    #if len(self.interface2access_link) != len(self.access_links):
    #  raise RuntimeError("Not enough interface2accesslinks (%d s/b %d)" % \
    #                    (len(self.interface2accesslinks), len(self.access_links)))

  def _sanity_check_tree(self):
    # TODO(cs): this should be in a unit test, not here
    if len(self.access_links) != self.total_hosts:
      raise RuntimeError("incorrect # of access links (%d, s/b %d)" % \
                          (len(self.access_links),len(self.total_hosts)))  
    
    # k = number of ports per switch = number of pods
    # number core switches =  (k/2)^2
    # number of edge switches per pod = k / 2
    # number of agg switches per pod = k / 2
    total_switches = self.total_core + ((self.edge_per_pod + self.agg_per_pod) * self.k)
    print "total_switches: %d" % total_switches
    # uni-directional links (on in both directions):
    total_network_links = (total_switches * self.k) - self.total_hosts
    if len(self.network_links) != total_network_links:
      raise RuntimeError("incorrect # of internal links (%d, s/b %d)" % \
                          (len(self.network_links),total_network_links))  

  def install_default_routes(self):
    '''
    Install static routes as proposed in Section 3 of "A Scalable, Commodity Data Center Network Architecture".
    This is really a strawman routing scheme. PORTLAND, et. al. are much better
    '''
    pass

  def install_portland_routes(self):
    '''
    We use a modified version of PORTLAND. We make two changes: OpenFlow 1.0 doesn't support prefix matching
    on MAC addresses, so we use IP addresses instead. (same # of flow entries, and we don't model flooding anyway)
    Second, we ignore vmid and assume 8 bit pod ids. So, IPs are of the form:
    123.pod.position.port
    '''
    k = self.k

    for core in self.cores:
      # When forwarding a packet, the core switch simply inspects the bits corresponding to the pod
      # number in the PMAC destination address to determine the appropriate output port.
      for port_no in core.ports.keys():
        # port_no i+1 corresponds to pod i
        match = ofp_match(nw_dst="123.%d.0.0/16" % (port_no-1))
        flow_mod = ofp_flow_mod(match=match, actions=[ofp_action_output(port=port_no)])
        core._receive_flow_mod(flow_mod)

    for agg in self.aggs:
      # Aggregation switches must determine whether a packet is destined for a host
      # in the same or different pod by inspecting the PMAC. If in the same pod,
      # the packet must be forwarded to an output port corresponding to the position
      # entry in the PMAC. If in a different pod, the packet may be forwarded along
      # any of the aggregation switch's links to the core layer in the fault-free case.
      pod_id = agg.pod_id
      for port_no in range(1, k/2+1):
        # ports 1 through k/2 are connected to edge switches 0 through k/2-1
        position = port_no - 1
        match = ofp_match(nw_dst="123.%d.%d.0/24" % (pod_id, position))
        flow_mod = ofp_flow_mod(match=match, actions=[ofp_action_output(port=port_no)])
        agg._receive_flow_mod(flow_mod)

      # We model load balancing to uplinks as a single flow entry -- h/w supports ecmp efficiently
      # while only requiring a single TCAM entry
      match = ofp_match(nw_dst="123.0.0.0/8")
      # Forward to the right-most uplink
      flow_mod = ofp_flow_mod(match=match, actions=[ofp_action_output(port=k)])
      agg._receive_flow_mod(flow_mod)

    for edge in self.edges:
      # if a connected host, deliver to host. Else, ECMP over uplinks
      pod_id = edge.pod_id
      position = edge.position
      for port_no in range(1,k/2+1):
        # Route down to the host
        match = ofp_match(nw_dst="123.%d.%d.%d" % (pod_id, position, port_no))
        flow_mod = ofp_flow_mod(match=match, actions=[ofp_action_output(port=port_no)])
        edge._receive_flow_mod(flow_mod)

      # We model load balancing to uplinks as a single flow entry -- h/w supports ecmp efficiently
      # while only requiring a single TCAM entry
      match = ofp_match(nw_dst="123.0.0.0/8")
      # Forward to the right-most uplink
      flow_mod = ofp_flow_mod(match=match, actions=[ofp_action_output(port=k)])
      edge._receive_flow_mod(flow_mod)

  def get_connected_port(self, node, port):
    ''' Given a node and a port, return a tuple (node, port) that is directly connected to the port '''
    # TODO(cs): use a $@#*$! graph library
    if port in self.port2access_link:
      access_link = self.port2access_link[port]
      return (access_link.host, access_link.interface)
    if port in self.interface2access_link:
      access_link = self.interface2access_link[port]
      return (access_link.switch, access_link.switch_port)
    if port in self.port2internal_link:
      link = self.port2internal_link[port]
      return (link.end_switch_impl, link.end_port)
    raise RuntimeError("Node %s Port %s not in network" % (str(node), str(port)))
