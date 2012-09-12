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

from entities import FuzzSoftwareSwitch, Link, Host, HostInterface, AccessLink
from pox.openflow.software_switch import ofp_phy_port, DpPacketOut, SoftwareSwitch
from pox.lib.addresses import EthAddr, IPAddr
from pox.openflow.libopenflow_01 import *
from pox.lib.util import connect_socket_with_backoff
from pox.lib.revent import EventMixin
from console import msg
import socket
import abc
import time
import errno
import sys
import itertools
import logging

log = logging.getLogger("sts.topology")

def create_switch(switch_id, num_ports):
  ports = []
  for port_no in range(1, num_ports+1):
    eth_addr = EthAddr("00:00:00:00:%02x:%02x" % (switch_id, port_no))
    port = ofp_phy_port( port_no=port_no, hw_addr=eth_addr )
    # monkey patch an IP address onto the port for anteater purposes
    port.ip_addr = "1.1.%d.%d" % (switch_id, port_no)
    ports.append(port)

  def unitialized_io_worker(switch):
    raise SystemError("Not initialialized")

  return FuzzSoftwareSwitch(create_io_worker=unitialized_io_worker,
                        dpid=switch_id, name="SoftSwitch(%d)" % switch_id,
                        ports=ports)

def get_switchs_host_port(switch):
  ''' return the switch's ofp_phy_port connected to the host '''
  # We wire up the last port of the switch to the host
  # TODO(cs): this is arbitrary and hacky
  return switch.ports[sorted(switch.ports.keys())[-1]]

def create_host(ingress_switch_or_switches, mac_or_macs=None, ip_or_ips=None,
                get_switch_port=get_switchs_host_port):
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
      ip_addr = IPAddr("123.123.%d.%d" % (switch.dpid, port.port_no))

    name = "eth%d" % switch.dpid
    interface = HostInterface(mac, ip_addr, name)
    interface_switch_pairs.append((interface, switch))
    interfaces.append(interface)

  name = "host:" + ",".join(map(lambda interface: "%s" % str(interface.ips), interfaces))
  host = Host(interfaces, name)
  access_links = [ AccessLink(host, interface, switch, get_switch_port(switch))
                   for interface, switch in interface_switch_pairs ]
  return (host, access_links)

class LinkTracker(object):
  def __init__(self, dpid2switch, port2access_link, interface2access_link):
    self.dpid2switch = dpid2switch
    self.port2access_link = port2access_link
    self.interface2access_link = interface2access_link
    self.port2internal_link = {}

  @property
  def network_links(self):
    return self.port2internal_link.values()

  def __call__(self, node, port):
    ''' Given a node and a port, return a tuple (node, port) that is directly
    connected to the port.

    This can be used in 2 ways
    - node is a Host type and port is a HostInterface type
    - node is a Switch type and port is a ofp_phy_port type.'''
    if port in self.port2access_link:
      access_link = self.port2access_link[port]
      return (access_link.host, access_link.interface)
    if port in self.interface2access_link:
      access_link = self.interface2access_link[port]
      return (access_link.switch, access_link.switch_port)
    elif port in self.port2internal_link:
      network_link = self.port2internal_link[port]
      return (network_link.end_software_switch, network_link.end_port)
    else:
      raise ValueError("Unknown port: %s" % str(port))

  def _get_switch_by_dpid(self, dpid):
    if dpid not in self.dpid2switch:
      raise ValueError("Unknown switch dpid: %s" % str(dpid))

    return self.dpid2switch[dpid]

  def migrate_host(self, old_ingress_dpid, old_ingress_portno,
                   new_ingress_dpid, new_ingress_portno):
    '''Migrate the host from the old (ingress switch, port) to the new
    (ingress switch, port). Note that the new port must not already be
    present, otherwise an exception will be thrown (we treat all switches as
    configurable software switches for convenience, rather than hardware switches
    with a fixed number of ports)'''
    old_ingress_switch = self._get_switch_by_dpid(old_ingress_dpid)

    if old_ingress_portno not in old_ingress_switch.ports:
      raise ValueError("unknown old_ingress_portno %d" % old_ingress_portno)

    old_port = old_ingress_switch.ports[old_ingress_portno]

    (host, interface) = self(old_ingress_switch, old_port) # using __call__

    if not (isinstance(host, Host) and isinstance(interface, HostInterface)):
      raise ValueError("(%s,%s) does not connect to a host!" %
                       (str(old_ingress_switch), str(old_port)))

    new_ingress_switch = self._get_switch_by_dpid(new_ingress_dpid)

    if new_ingress_portno in new_ingress_switch.ports:
      raise RuntimeError("new ingress port %d already exists!" % new_ingress_portno)

    # now that we've verified everything, actually make the change!
    # first, drop the old mappings
    del self.port2access_link[old_port]
    del self.interface2access_link[interface]
    old_ingress_switch.take_port_down(old_port)

    # now add new mappings
    # For now, make the new port have the same ip address as the old port.
    # TODO(cs): this would break PORTLAND routing! Need to specify the
    #           new mac and IP addresses
    new_ingress_port = ofp_phy_port(hw_addr=old_port.hw_addr,
                                    port_no=new_ingress_portno)
    new_ingress_switch.bring_port_up(new_ingress_port)
    new_access_link = AccessLink(host, interface, new_ingress_switch, new_ingress_port)
    self.port2access_link[new_ingress_port] = new_access_link
    self.interface2access_link[interface] = new_access_link

class PatchPanel(object):
  """ A Patch panel. Contains a bunch of wires to forward packets between switches.
      Listens to the SwitchDPPacketOut event on the switches.
  """
  def __init__(self, switches, hosts, connected_port_mapping):
    '''
    Constructor
     - switches: a list of the switches in the network
     - hosts: a list of hosts in the network
     - connected_port_mapping: a function which takes (switch_no, port_no, dpid2switch),
                               and returns the adjacent (node, port) or None
    '''
    self.switches = sorted(switches, key=lambda(sw): sw.dpid)
    self.get_connected_port = connected_port_mapping
    self.hosts = hosts
    for s in self.switches:
      s.addListener(DpPacketOut, self.handle_DpPacketOut)
    for host in self.hosts:
      host.addListener(DpPacketOut, self.handle_DpPacketOut)

  def handle_DpPacketOut(self, event):
    (node, port) = self.get_connected_port(event.node, event.port)
    if type(node) == Host:
      self.deliver_packet(node, event.packet, port)
    else:
      self.forward_packet(node, event.packet, port)

  def get_connected_port(self, node, port): # TODO(sw): is this actually necessary?
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
  return BufferedPatchPanel(topology.find(is_a=SoftwareSwitch), topology.find(is_a=Host), \
                            lambda node, port:topology.port_for_node(node, port))

class BufferedPatchPanel(PatchPanel, EventMixin):
  '''
  A Buffered Patch panel.Listens to SwitchDPPacketOut and HostDpPacketOut events,
  and re-raises them to listeners of this object. Does not traffic until given
  permission from a higher-level.
  '''
  _eventMixin_events = set([DpPacketOut])
  # TODO(cs): these ids need to be unique across runs, and assigning the ids based
  # on order may be dangerous if control connections have different delays!
  _dpout_id_gen = itertools.count(1)

  def __init__(self, switches, hosts, connected_port_mapping):
    self.get_connected_port = connected_port_mapping
    self.switches = sorted(switches, key=lambda(sw): sw.dpid)
    self.hosts = hosts
    # dp out id -> dp_out object
    self.buffered_dp_out_events = {}
    self.dropped_dp_events = []
    def handle_DpPacketOut(event):
      # Monkey patch on a unique id for this event
      event.dpout_id = self._dpout_id_gen.next()
      self.buffered_dp_out_events[event.dpout_id] = event
      self.raiseEventNoErrors(event)
    for i, s in enumerate(self.switches):
      s.addListener(DpPacketOut, handle_DpPacketOut)
    for host in self.hosts:
      host.addListener(DpPacketOut, handle_DpPacketOut)

  @property
  def queued_dataplane_events(self):
    return self.buffered_dp_out_events.values()

  def permit_dp_event(self, dp_event):
    ''' Given a SwitchDpPacketOut event, permit it to be forwarded  '''
    # TODO(cs): self.forward_packet should not be externally visible!
    msg.event("Forwarding dataplane event")
    # Invoke superclass DpPacketOut handler
    self.handle_DpPacketOut(dp_event)
    del self.buffered_dp_out_events[dp_event.dpout_id]

  def drop_dp_event(self, dp_event):
    '''
    Given a SwitchDpPacketOut event, remove it from our buffer, and do not forward.
    Return the dropped event.
    '''
    msg.event("Dropping dataplane event")
    del self.buffered_dp_out_events[dp_event.dpout_id]
    self.dropped_dp_events.append(dp_event)
    return dp_event

  def delay_dp_event(self, dp_event):
    msg.event("Delaying dataplane event")
    # (Monkey patch on a delay counter)
    if not hasattr(dp_event, "delayed_rounds"):
      dp_event.delayed_rounds = 0
    dp_event.delayed_rounds += 1

  def get_buffered_dp_event(self, id):
    if id not in self.buffered_dp_out_events:
      return None
    return self.buffered_dp_out_events[id]

class Topology(object):
  '''
  Abstract base class of all topology types. Wraps the edges and vertices of
  the network.
  '''
  def __init__(self):
    self.dpid2switch = {}
    self.network_links = set()

    # Metatdata for simulated failures
    # sts.entities.Link objects
    self.cut_links = set()
    # SoftwareSwitch objects
    self.failed_switches = set()

  def _populate_dpid2switch(self, switches):
    self.dpid2switch = {
      switch.dpid : switch
      for switch in switches
    }

  @property
  def switches(self):
    return self.dpid2switch.values()

  def get_switch(self, dpid):
    if dpid not in self.dpid2switch:
      raise RuntimeError("unknown dpid %d" % dpid)
    return self.dpid2switch[dpid]

  @property
  def live_switches(self):
    """ Return the software_switchs which are currently up """
    return set(self.switches) - self.failed_switches

  def ok_to_send(self, dp_event):
    """Returns True if it is ok to send the dp_event arg."""
    (next_hop, next_port) = self.get_connected_port(dp_event.switch,
                                                    dp_event.port)
    if type(dp_event.node) == Host or type(next_hop) == Host:
      # TODO(cs): model access link failures
      return True
    else:
      link = Link(dp_event.switch, dp_event.port, next_hop, next_port)
      if not link in self.cut_links:
        return True
      return False

  def crash_switch(self, software_switch):
    msg.event("Crashing software_switch %s" % str(software_switch))
    software_switch.fail()
    self.failed_switches.add(software_switch)

  def recover_switch(self, software_switch):
    msg.event("Rebooting software_switch %s" % str(software_switch))
    if software_switch not in self.failed_switches:
      raise RuntimeError("Switch %s not currently down. (Currently down: %s)" %
                         (str(software_switch), str(self.failed_switches)))
    software_switch.recover()
    self.failed_switches.remove(software_switch)

  @property
  def live_links(self):
    return set(self.network_links) - self.cut_links

  def sever_link(self, link):
    msg.event("Cutting link %s" % str(link))
    if link not in self.network_links:
      raise ValueError("unknown link %s" % str(link))
    if link in self.cut_links:
      raise RuntimeError("link %s already cut!" % str(link))
    self.cut_links.add(link)
    link.start_software_switch.take_port_down(link.start_port)
    # TODO(cs): the switch on the other end of the link should eventually
    # notice that the link has gone down!

  def repair_link(self, link):
    msg.event("Restoring link %s" % str(link))
    if link not in self.network_links:
      raise ValueError("Unknown link %s" % str(link))
    port = ofp_phy_port(port_no=link.start_port)
    link.start_software_switch.bring_port_up(link.start_port)
    self.cut_links.remove(link)
    # TODO(cs): the switch on the other end of the link should eventually
    # notice that the link has come back up!

  def permit_cp_send(self, connection):
    # pre: software_switch.io_worker.has_pending_sends()
    msg.event("Giving permission for control plane send for %s" % connection)
    connection.io_worker.permit_send()

  def delay_cp_send(self, connection):
    msg.event("Delaying control plane send for %s" % connection)
    # update # delayed rounds?

  def permit_cp_receive(self, connection):
    # pre: software_switch.io_worker.has_pending_sends()
    msg.event("Giving permission for control plane receive for %s" % connection)
    connection.io_worker.permit_receive()

  def delay_cp_receive(self, connection):
    msg.event("Delaying control plane receive for %s" % connection)
    # update # delayed rounds?

  @property
  def cp_connections_with_pending_receives(self):
    for software_switch in self.live_switches:
      for c in software_switch.connections:
        if c.io_worker.has_pending_receives():
          yield (software_switch, c)

  @property
  def cp_connections_with_pending_sends(self):
    for software_switch in self.live_switches:
      for c in software_switch.connections:
        if c.io_worker.has_pending_sends():
          yield (software_switch, c)

  # convenience method: allow all buffered control plane packets through
  # TODO(cs): alternative implementation: use non-deferred io workers
  def flush_controlplane_buffers(self):
    for (_, connection) in self.cp_connections_with_pending_receives:
      self.permit_cp_receive(connection)
    for (_, connection) in self.cp_connections_with_pending_sends:
      self.permit_cp_sends(connection)

  def connect_to_controllers(self, controller_info_list, io_worker_generator):
    '''
    Bind sockets from the software_switchs to the controllers. For now, assign each
    switch to the next controller in the list in a round robin fashion.

    Controller info list is a list of
    (controller ip address, controller port number) tuples

    Return a list of socket objects
    '''
    controller_info_cycler = itertools.cycle(controller_info_list)
    connections_per_switch = len(controller_info_list)

    log.debug('''Connecting %d switches to %d controllers (setting up %d'''
              ''' conns per switch)...''' %
              (len(self.switches), len(controller_info_list), connections_per_switch))

    for (idx, software_switch) in enumerate(self.switches):
      if len(self.switches) < 20 or not idx % 250:
        log.debug("Connecting switch %d / %d" % (idx, len(self.switches)))

      def create_io_worker(switch, controller_info):
        controller_socket = connect_socket_with_backoff(controller_info.address,
                                                        controller_info.port)
        # Set non-blocking
        controller_socket.setblocking(0)
        return io_worker_generator(controller_socket)
      software_switch.create_io_worker = create_io_worker

      # Socket from the software_switch to the controller
      for i in xrange(connections_per_switch):
        controller_info = controller_info_cycler.next()
        software_switch.add_controller_info(controller_info)

      software_switch.connect()

    log.debug("Controller connections done")

  def migrate_host(self, old_ingress_dpid, old_ingress_portno,
                   new_ingress_dpid, new_ingress_portno):
    self.get_connected_port.migrate_host(old_ingress_dpid, old_ingress_portno,
                                         new_ingress_dpid, new_ingress_portno)

  @staticmethod
  def populate_from_topology(graph):
     """
     Take a pox.lib.graph.graph.Graph and generate arguments needed for the
     simulator
     """
     topology = Topology()
     topology.hosts = graph.find(is_a=Host)
     topology.switches = graph.find(is_a=SoftwareSwitch)
     topology.access_links = [AccessLink(host, switch[0], switch[1][0], switch[1][1])
                              for host in hosts
                              for switch in filter(
                                  lambda n: isinstance(n[1][0], SoftwareSwitch),
                                  graph.ports_for_node(host).iteritems())]
     return topology

class MeshTopology(Topology):
  def __init__(self, num_switches=3):
    '''
    Populate the topology as a mesh of switches, connect the switches
    to the controllers

    Optional argument(s):
      - num_switches. The total number of switches to include in the mesh
    '''
    Topology.__init__(self)

    # Every switch has a link to every other switch + 1 host,
    # for N*(N-1)+N = N^2 total ports
    ports_per_switch = (num_switches - 1) + 1

    # Initialize switches
    switches = [ create_switch(switch_id, ports_per_switch)
                  for switch_id in range(1, num_switches+1) ]
    self._populate_dpid2switch(switches)
    host_access_link_pairs = [ create_host(switch) for switch in self.switches ]
    self.hosts = map(lambda pair: pair[0], host_access_link_pairs)
    access_link_list_list = map(lambda pair: pair[1], host_access_link_pairs)
    # this is python's .flatten:
    self.access_links = list(itertools.chain.from_iterable(access_link_list_list))

    # grab a fully meshed patch panel to wire up these guys
    link_topology = MeshTopology.FullyMeshedLinks(self.dpid2switch, self.access_links)
    self.get_connected_port = link_topology
    self.network_links = link_topology.network_links

  class FullyMeshedLinks(LinkTracker):
    """
    A factory method (inner class) for creating a fully meshed network.
    Connects every pair of switches. Ports are in ascending order of
    the dpid of connected switch, while skipping the self-connections.
    I.e., for (dpid, portno):
        (0, 0) <-> (1,0)
        (2, 1) <-> (1,1)
    """
    def __init__(self, dpid2switch, access_links=[]):
      port2access_link = { access_link.switch_port: access_link
                           for access_link in access_links }
      interface2access_link = { access_link.interface: access_link
                                for access_link in access_links }
      LinkTracker.__init__(self, dpid2switch, port2access_link, interface2access_link)

      switches = dpid2switch.values()
      # Access links to hosts are already claimed, all other internal links
      # are not yet claimed
      switch2unclaimed_ports = { switch : filter(lambda p: p not in port2access_link,
                                                 switch.ports.values())
                                 for switch in switches }
      port2internal_link = {}
      for i, switch_i in enumerate(switches):
        for switch_j in switches[i+1:]:
          switch_i_port = switch2unclaimed_ports[switch_i].pop()
          switch_j_port = switch2unclaimed_ports[switch_j].pop()
          link_i2j = Link(switch_i, switch_i_port, switch_j, switch_j_port)
          link_j2i = link_i2j.reversed_link()
          port2internal_link[switch_i_port] = link_i2j
          port2internal_link[switch_j_port] = link_j2i
      self.port2internal_link = port2internal_link

class FatTree (Topology):
  ''' Construct a FatTree topology with a given number of pods '''
  def __init__(self, num_pods=4):
    if num_pods < 2:
      raise "Can't handle Fat Trees with less than 2 pods"
    Topology.__init__(self)
    self.hosts = []
    self.cores = []
    self.aggs = []
    self.edges = []
    # Note that access links are bi-directional
    self.access_links = set()
    # But internal links are uni-directional?
    self.network_links = set()

    self.dpid2switch = {}
    self.construct_tree(num_pods)

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
    log.debug("Constructing fat tree with %d pods" % num_pods)

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
        log.debug("Host %d / %d" % (i, self.total_hosts))

      if (i % self.hosts_per_pod) == 0:
        current_pod_id += 1

      if (i % self.hosts_per_edge) == 0:
        current_dpid += 1
        edge_switch = create_switch(current_dpid, self.ports_per_switch)
        edge_switch.pod_id = current_pod_id
        self.edges.append(edge_switch)

      edge = self.edges[-1]
      # edge ports 1 through (k/2) are dedicated to hosts, and (k/2)+1 through
      # k are for agg
      edge_port_no = (i % self.hosts_per_edge) + 1
      # We give it a portland pseudo mac, just for giggles
      # Slightly modified from portland (no vmid, assume 8 bit pod id):
      # 00:00:00:<pod>:<position>:<port>
      # position and pod are 0-indexed, port is 1-indexed
      position = (len(self.edges)-1) % self.edge_per_pod
      edge.position = position
      portland_mac = EthAddr("00:00:00:%02x:%02x:%02x" %
                             (current_pod_id, position, edge_port_no))
      # Uhh, unfortunately, OpenFlow 1.0 doesn't support prefix matching on MAC
      # addresses. So we do prefix matching on IP addresses, which yields
      # exactly the same # of flow entries for HSA, right?
      portland_ip_addr = IPAddr("123.%d.%d.%d" %
                                (current_pod_id, position, edge_port_no))
      (host, host_access_links) = create_host(edge, portland_mac, portland_ip_addr,
                                              lambda switch: switch.ports[edge_port_no])
      host.pod_id = current_pod_id
      self.hosts.append(host)
      self.access_links = self.access_links.union(set(host_access_links))

    # Now edge <-> agg
    for pod_id in range(num_pods):
      if not pod_id % 10:
        log.debug("edge<->agg for pod %d / %d" % (pod_id, num_pods))
      current_aggs = []
      for _ in  range(self.agg_per_pod):
        current_dpid += 1
        agg = create_switch(current_dpid, self.ports_per_switch)
        agg.pod_id = pod_id
        current_aggs.append(agg)

      current_edges = self.edges[pod_id * self.edge_per_pod : \
                                (pod_id * self.edge_per_pod) + self.edge_per_pod]
      # edge ports (k/2)+1 through k connect to aggs
      # agg port k+1 connects to edge switch k in the pod
      current_agg_port_no = 1
      for edge in current_edges:
        current_edge_port_no = (k/2)+1
        for agg in current_aggs:
          self.network_links.add(Link(edge, edge.ports[current_edge_port_no],
                                      agg, agg.ports[current_agg_port_no]))
          self.network_links.add(Link(agg, agg.ports[current_agg_port_no],
                                      edge, edge.ports[current_edge_port_no]))
          current_edge_port_no += 1
        current_agg_port_no += 1

      self.aggs += current_aggs

    # Finally, agg <-> core
    for i in range(self.total_core):
      if not i % 100:
        log.debug("agg<->core %d / %d" % (i, self.total_core))
      current_dpid += 1
      self.cores.append(create_switch(current_dpid, self.ports_per_switch))

    core_cycler = itertools.cycle(self.cores)
    for agg in self.aggs:
      # agg ports (k/2)+1 through k connect to cores
      # core port i+1 connects to pod i
      for agg_port_no in range(k/2+1, k+1):
        core = core_cycler.next()
        core_port_no = agg.pod_id + 1
        self.network_links.add(Link(agg, agg.ports[agg_port_no], core,
                                    core.ports[core_port_no]))
        self.network_links.add(Link(core, core.ports[core_port_no], agg,
                                    agg.ports[agg_port_no]))

    switches = self.cores + self.aggs + self.edges
    self._populate_dpid2switch(switches)
    self.wire_tree()
    self._sanity_check_tree()
    log.debug('''Fat tree construction: done (%d cores, %d aggs,'''
              '''%d edges, %d hosts)''' %
              (len(self.cores), len(self.aggs), len(self.edges), len(self.hosts)))

  def wire_tree(self):
    # Auxiliary data to make get_connected_port efficient
    port2internal_link = { link.start_port: link
                           for link in self.network_links }
    port2access_link = { access_link.switch_port: access_link
                         for access_link in self.access_links }
    interface2access_link = { access_link.interface: access_link
                              for access_link in self.access_links }

    self.get_connected_port = self.FatTreeLinks(port2access_link, interface2access_link, port2internal_link, self.dpid2switch)

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
    Install static routes as proposed in Section 3 of
    "A Scalable, Commodity Data Center Network Architecture".
    This is really a strawman routing scheme. PORTLAND, et. al. are much better
    '''
    pass

  def install_portland_routes(self):
    '''
    We use a modified version of PORTLAND. We make two changes: OpenFlow 1.0
    doesn't support prefix matching on MAC addresses, so we use IP addresses
    instead. (same # of flow entries, and we don't model flooding anyway)
    Second, we ignore vmid and assume 8 bit pod ids. So, IPs are of the form:
    123.pod.position.port
    '''
    k = self.k

    for core in self.cores:
      # When forwarding a packet, the core switch simply inspects the bits
      # corresponding to the pod number in the PMAC destination address to
      # determine the appropriate output port.
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

      # We model load balancing to uplinks as a single flow entry -- h/w supports
      # ecmp efficiently while only requiring a single TCAM entry
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

      # We model load balancing to uplinks as a single flow entry --
      # h/w supports ecmp efficiently while only requiring a single TCAM entry
      match = ofp_match(nw_dst="123.0.0.0/8")
      # Forward to the right-most uplink
      flow_mod = ofp_flow_mod(match=match, actions=[ofp_action_output(port=k)])
      edge._receive_flow_mod(flow_mod)

  class FatTreeLinks(LinkTracker):
    # TODO(cs): perhaps we should not use inheritance here, since it is
    # essentially entirely trivial. Alternatively, we could just have an
    # overloaded constructor in the LinkTracker class?
    def __init__(self, port2access_link, interface2access_link, port2internal_link, dpid2switch):
      LinkTracker.__init__(self, dpid2switch, port2access_link, interface2access_link)
      self.port2internal_link = port2internal_link
