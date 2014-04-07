# Copyright 2011-2013 Colin Scott
# Copyright 2012-2013 Andrew Or
# Copyright 2011-2013 Andreas Wundsam
# Copyright 2012-2013 Sam Whitlock
# Copyright 2012-2012 Kyriakos Zarifis
# Copyright 2014      Ahmed El-Hassany
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

from sts.fingerprints.messages import DPFingerprint
from sts.invariant_checker import InvariantChecker
from sts.entities import FuzzSoftwareSwitch, Link, Host, HostInterface, AccessLink, NamespaceHost
from pox.openflow.software_switch import DpPacketOut, SoftwareSwitch
from pox.openflow.libopenflow_01 import *
from pox.lib.revent import EventMixin
from sts.util.console import msg
import itertools
import logging
from collections import defaultdict

from sts.topology.base import Topology as BaseTopology
from sts.topology.base import PatchPanel as BasePatchPanel

log = logging.getLogger("sts.topology")

def create_switch(switch_id, num_ports, can_connect_to_endhosts=True):
  ports = []
  for port_no in range(1, num_ports+1):
    eth_addr = EthAddr("00:00:00:00:%02x:%02x" % (switch_id, port_no))
    port = ofp_phy_port( port_no=port_no, hw_addr=eth_addr, name="eth%d" % port_no )
    # monkey patch an IP address onto the port for anteater purposes
    port.ip_addr = "1.1.%d.%d" % (switch_id, port_no)
    ports.append(port)

  def unitialized_io_worker(switch):
    raise SystemError("Not initialialized")

  return FuzzSoftwareSwitch(dpid=switch_id, name="SoftSwitch(%d)" % switch_id,
                            ports=ports,
                            can_connect_to_endhosts=can_connect_to_endhosts)

def get_switchs_host_port(switch):
  ''' Return the switch's ofp_phy_port connected to the host '''
  # We wire up the last port of the switch to the host
  # TODO(cs): this is arbitrary and hacky
  return switch.ports[sorted(switch.ports.keys())[-1]]

def create_host(ingress_switch_or_switches, mac_or_macs=None, ip_or_ips=None,
                get_switch_port=get_switchs_host_port,
                ip_format_str="10.%d.%d.2"):
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
      ip_addr = IPAddr(ip_format_str % (switch.dpid, port.port_no))

    name = "eth%d" % switch.dpid
    interface = HostInterface(mac, ip_addr, name)
    interface_switch_pairs.append((interface, switch))
    interfaces.append(interface)

  name = "host:" + ",".join(map(lambda interface: "%s" % str(interface.ips), interfaces))
  host = Host(interfaces, name)
  access_links = [ AccessLink(host, interface, switch, get_switch_port(switch))
                   for interface, switch in interface_switch_pairs ]
  return (host, access_links)

def create_netns_host(create_io_worker, ingress_switch,
                      ip_addr_str="",
                      ip_format_str="10.%d.%d.2",
                      get_switch_port=get_switchs_host_port, cmd='xterm'):
  '''
  Create a host with a process running in a separate network namespace.
  The netns can only communicate with a single interface (for now) because it must
  correspond to the physical interface in the network namespace guest.

  Because there is only 1 logical interface possible, this means that there can only be
  1 switch as well.

  - ip_addr_str must be a string! not a IpAddr object
  '''
  if ip_addr_str == "":
    ip_addr_str = ip_format_str % (ingress_switch.dpid, get_switch_port(ingress_switch).port_no)
  host = NamespaceHost(HostInterface(None, ip_addr_str),
                       create_io_worker, cmd=cmd)
  interface = host.interfaces[0]
  access_link = AccessLink(host, interface, ingress_switch, get_switch_port(ingress_switch))
  return (host, [access_link]) # single item list to be consistent with create_host


class STSPatchPanel(BasePatchPanel):
  def __init__(self):
    super(STSPatchPanel, self).__init__(link_cls=Link,
                                        access_link_cls=AccessLink,
                                        port_cls=ofp_phy_port,
                                        host_interface_cls=HostInterface,
                                        sts_console=msg)
  def sever_link(self, link):
    """
    Disconnect link
    """
    self.msg.event("Cutting link %s" % str(link))
    if link not in self.network_links:
      raise ValueError("unknown link %s" % str(link))
    if link in self.cut_links:
      raise RuntimeError("link %s already cut!" % str(link))
    self.cut_links.add(link)
    link.start_software_switch.take_port_down(link.start_port)
    # TODO(cs): the switch on the other end of the link should eventually
    # notice that the link has gone down!

  def repair_link(self, link):
    """Bring a link back online"""
    self.msg.event("Restoring link %s" % str(link))
    if link not in self.network_links:
      raise ValueError("Unknown link %s" % str(link))
    link.start_software_switch.bring_port_up(link.start_port)
    self.cut_links.remove(link)
    # TODO(cs): the switch on the other end of the link should eventually
    # notice that the link has come back up!

  def sever_access_link(self, link):
    """
    Disconnect host-switch link
    """
    self.msg.event("Cutting access link %s" % str(link))
    if link not in self.access_links:
      raise ValueError("unknown access link %s" % str(link))
    if link in self.cut_access_links:
      raise RuntimeError("Access link %s already cut!" % str(link))
    self.cut_access_links.add(link)
    link.switch.take_port_down(link.switch_port)
    # TODO(cs): the host on the other end of the link should eventually
    # notice that the link has gone down!


  def repair_access_link(self, link):
    """Bring a link back online"""

    self.msg.event("Restoring access link %s" % str(link))
    if link not in self.access_links:
      raise ValueError("Unknown access link %s" % str(link))
    link.switch.bring_port_up(link.switch_port)
    self.cut_access_links.remove(link)
    # TODO(cs): the host on the other end of the link should eventually
    # notice that the link has come back up!



class PatchPanel(object):
  '''
  A Patch panel. Contains a bunch of wires to forward packets between switches.
  Listens to the SwitchDPPacketOut event on the switches.
  '''
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

  def register_interface_pair(self, event):
    (src_addr, dst_addr) = (event.packet.src, event.packet.dst)
    if src_addr is not None and dst_addr is not None:
      InvariantChecker.register_interface_pair(src_addr, dst_addr)

  def handle_DpPacketOut(self, event):
    self.register_interface_pair(event)
    try:
      (node, port) = self.get_connected_port(event.node, event.port)
    except ValueError:
      log.warn("no such port %s on node %s" % (str(event.port), str(event.node)))
      return

    if isinstance(node, Host):
      self.deliver_packet(node, event.packet, port)
    else:
      self.forward_packet(node, event.packet, port)

  def forward_packet(self, next_switch, packet, next_port):
    ''' Forward the packet to the given port '''
    if type(next_port) != int:
      next_port = next_port.port_no
    next_switch.process_packet(packet, next_port)

  def deliver_packet(self, host, packet, host_interface):
    ''' Deliver the packet to its final destination '''
    host.receive(host_interface, packet)

def BufferedPatchPanelForTopology(topology):
  '''
  Given a pox.lib.graph.graph object with hosts, switches, and other things,
  produce an appropriate BufferedPatchPanel
  '''
  return BufferedPatchPanel(topology.find(is_a=SoftwareSwitch), topology.find(is_a=Host), \
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
    # Buffered dp out events
    self.fingerprint2dp_outs = defaultdict(list)
    def handle_DpPacketOut(event):
      fingerprint = (DPFingerprint.from_pkt(event.packet),
                     event.node.dpid, event.port.port_no)
      # Monkey patch on a fingerprint for this event
      event.fingerprint = fingerprint
      self.fingerprint2dp_outs[fingerprint].append(event)
      self.raiseEvent(event)
    for _, s in enumerate(self.switches):
      s.addListener(DpPacketOut, handle_DpPacketOut)
    for host in self.hosts:
      host.addListener(DpPacketOut, handle_DpPacketOut)

  @property
  def queued_dataplane_events(self):
    list_of_lists = self.fingerprint2dp_outs.values()
    return list(itertools.chain(*list_of_lists))

  def permit_dp_event(self, dp_event):
    ''' Given a SwitchDpPacketOut event, permit it to be forwarded '''
    # TODO(cs): self.forward_packet should not be externally visible!
    msg.event("Forwarding dataplane event")
    # Invoke superclass DpPacketOut handler
    self.handle_DpPacketOut(dp_event)
    self._remove_dp_event(dp_event)

  def drop_dp_event(self, dp_event):
    '''
    Given a SwitchDpPacketOut event, remove it from our buffer, and do not forward.
    Return the dropped event.
    '''
    msg.event("Dropping dataplane event")
    self._remove_dp_event(dp_event)
    return dp_event

  def _remove_dp_event(self, dp_event):
    # Pre: dp_event.fingerprint in self.fingerprint2dp_outs
    self.fingerprint2dp_outs[dp_event.fingerprint].remove(dp_event)
    if self.fingerprint2dp_outs[dp_event.fingerprint] == []:
      del self.fingerprint2dp_outs[dp_event.fingerprint]

  def get_buffered_dp_event(self, fingerprint):
    if fingerprint in self.fingerprint2dp_outs:
      return self.fingerprint2dp_outs[fingerprint][0]
    return None


class Topology(BaseTopology):
  """
  Abstract base class of all topology types. Wraps the edges and vertices of
  the network.
  """
  def __init__(self, create_io_worker=None, gui=False, host_cls=Host):
    super(Topology, self).__init__(host_cls=Host, switch_cls=FuzzSoftwareSwitch,
                                   link_cls=host_cls,
                                   access_link_cls=AccessLink,
                                   interface_cls=HostInterface,
                                   patch_panel=STSPatchPanel())
    self.create_io_worker = create_io_worker
    self.gui = None
    if gui:
      from sts.gui.launcher import TopologyGui
      self.gui = TopologyGui(self)


  def _populate_dpid2switch(self, switches):
    """BBB This entire method need to be removed
    self.dpid2switch = {
      switch.dpid : switch
      for switch in switches
    }
    """
    for switch in switches:
      if not self.has_switch(switch):
        self.add_switch(switch)

  def create_switch(self, switch_id, num_ports, can_connect_to_endhosts=True):
    ''' Create a switch and register it in the topology '''
    switch = create_switch(switch_id, num_ports, can_connect_to_endhosts)
    self.add_switch(switch)
    return switch

  def create_host(self, ingress_switch_or_switches, mac_or_macs=None, ip_or_ips=None,
                get_switch_port=get_switchs_host_port):
    """
    Create a host, register it in the topology, and wire it to the given switch(es)
    """
    (host, access_links) = create_host(ingress_switch_or_switches, mac_or_macs,
                                      ip_or_ips, get_switch_port)
    for access_link in access_links:
      self.add_link(access_link)
    self.add_host(host)
    return host

  def ok_to_send(self, dp_event):
    """Return True if it is ok to send the dp_event arg"""
    if not self.patch_panel.is_port_connected(dp_event.port):
      return False

    try:
      (next_hop, next_port) = self.get_connected_port(dp_event.switch,
                                                      dp_event.port)
    except ValueError:
      self.log.warn("no such port %s on node %s" % (str(dp_event.port),
                                               str(dp_event.switch)))
      return False

    if isinstance(dp_event.node, Host) or isinstance(next_hop, Host):
      # TODO(cs): model access link failures
      return True
    else:
      link = Link(dp_event.switch, dp_event.port, next_hop, next_port)
      if not link in self.cut_links:
        return True
      return False


  def remove_access_link(self, host, switch):
    return super(Topology, self).remove_access_link(host, None, switch, None,
                                                    remove_all=True)

  @property
  def blocked_controller_connections(self):
    for switch in self.switches:
      for connection in switch.connections:
        if connection.io_worker.currently_blocked:
          yield (switch, connection)

  @property
  def unblocked_controller_connections(self):
    for switch in self.switches:
      for connection in switch.connections:
        if not connection.io_worker.currently_blocked:
          yield (switch, connection)

  def block_connection(self, connection):
    msg.event("Blocking connection %s" % connection)
    return connection.io_worker.block()

  def unblock_connection(self, connection):
    msg.event("Unblocking connection %s" % connection)
    return connection.io_worker.unblock()

  def connect_to_controllers(self, controller_info_list, create_connection):
    """
    Bind sockets from the software_switchs to the controllers. For now, assign each
    switch to the next controller in the list in a round robin fashion.

    Controller info list is a list of ControllerConfig tuples
        - create_io_worker is a factory method for creating IOWorker objects.
          Takes a socket as a parameter
        - create_connection is a factory method for creating Connection objects
          which are connected to controllers. Takes a ControllerConfig object
          as a parameter
    """
    controller_info_cycler = itertools.cycle(controller_info_list)
    connections_per_switch = len(controller_info_list)

    log.debug('''Connecting %d switches to %d controllers (setting up %d'''
              ''' conns per switch)...''' %
              (len(self.switches), len(controller_info_list), connections_per_switch))

    for (idx, software_switch) in enumerate(self.switches):
      if len(self.switches) < 20 or not idx % 250:
        log.debug("Connecting switch %d / %d" % (idx, len(self.switches)))

      # Socket from the software_switch to the controller
      for _ in xrange(connections_per_switch):
        controller_info = controller_info_cycler.next()
        software_switch.add_controller_info(controller_info)

      software_switch.connect(create_connection)

    log.debug("Controller connections done")

  def migrate_host(self, old_ingress_dpid, old_ingress_portno,
                   new_ingress_dpid, new_ingress_portno):
    # TODO (AH): Implement migrate host
    #self.link_tracker.migrate_host(old_ingress_dpid, old_ingress_portno,
    #                               new_ingress_dpid, new_ingress_portno)
    pass

  @staticmethod
  def populate_from_topology(graph):
    """
    Take a pox.lib.graph.graph.Graph and generate arguments needed for the
    simulator
    """
    topology = Topology()
    topology.hosts = graph.find(is_a=Host)
    # TODO(cs): broken: can't set attribute
    topology.switches = graph.find(is_a=SoftwareSwitch)
    topology.access_links = [AccessLink(host, switch[0], switch[1][0], switch[1][1])
                              for host in topology.hosts
                              for switch in filter(
                                  lambda n: isinstance(n[1][0], SoftwareSwitch),
                                  graph.ports_for_node(host).iteritems())]
    return topology

  def reset(self):
    ''' Reset topology without new controllers '''
    self.dpid2switch = {}
    self.hid2host = {}
    self.failed_switches = set()
    if self.link_tracker is not None:
      self.link_tracker.dpid2switch = {}
      self.link_tracker.port2access_link = {}
      self.link_tracker.interface2access_link = {}
      self.link_tracker.port2internal_link = {}


class MeshTopology(Topology):
  def __init__(self, num_switches=3, create_io_worker=None, netns_hosts=False,
               gui=False, ip_format_str="123.123.%d.%d"):
    """
    Populate the topology as a mesh of switches, connect the switches
    to the controllers

    Optional argument(s):
      - num_switches. The total number of switches to include in the mesh
      - netns_switches. Whether to create network namespace hosts instead of
        normal hosts.
      - ip_format_str: a format string for assigning IP addresses to hosts.
        Takes two digits to be interpolated, the switch dpid and the port
        number. For example, "10.%d.%d.255" will assign hosts the IP address
        10.DPID.PORT_NUMBER.255, where DPID is the dpid of their ingress
        switch, and PORT_NUMBER is the number of the switch's access link.
    """
    host_cls = NamespaceHost if netns_hosts == True else Host
    super(MeshTopology, self).__init__(create_io_worker=create_io_worker,
                                       gui=gui, host_cls=host_cls)

    # Every switch has a link to every other switch + 1 host,
    # for N*(N-1)+N = N^2 total ports
    ports_per_switch = (num_switches - 1) + 1

    # Initialize switches
    switches = [create_switch(switch_id, ports_per_switch)
                for switch_id in range(1, num_switches + 1)]
    for switch in switches:
      self.add_switch(switch)

    if netns_hosts:
      host_access_link_pairs = [create_netns_host(create_io_worker, switch)
                                 for switch in self.switches]
    else:
      host_access_link_pairs = [create_host(switch, ip_format_str=ip_format_str)
                                for switch in self.switches]
    access_link_list_list = []
    for host, access_link_list in host_access_link_pairs:
      access_link_list_list.append(access_link_list)
      self.add_host(host)

    # this is python's .flatten:
    access_links = list(itertools.chain.from_iterable(access_link_list_list))
    for access_link in access_links:
      self.add_link(access_link)

    # grab a fully meshed patch panel to wire up these guys
    self.patch_panel = MeshTopology.FullyMeshedLinks(self.switches, access_links)
    self.get_connected_port = self.patch_panel.get_other_side
    if self.gui is not None:
      self.gui.launch()

  class FullyMeshedLinks(STSPatchPanel):
    """
    A factory method (inner class) for creating a fully meshed network.
    Connects every pair of switches. Ports are in ascending order of
    the dpid of connected switch, while skipping the self-connections.
    I.e., for (dpid, portno):
        (0, 0) <-> (1,0)
        (2, 1) <-> (1,1)
    """
    def __init__(self, switches, access_links=[]):
      STSPatchPanel.__init__(self)
      for link in access_links:
        self.add_access_link(link)

      switch2unclaimed_ports = {switch: filter(lambda p: p not in
                                                         self.port2access_link,
                                               switch.ports.values())
                                for switch in switches}

      for i, switch_i in enumerate(switches):
        for switch_j in switches[i+1:]:
          switch_i_port = switch2unclaimed_ports[switch_i].pop()
          switch_j_port = switch2unclaimed_ports[switch_j].pop()
          link_i2j = Link(switch_i, switch_i_port, switch_j, switch_j_port)
          link_j2i = link_i2j.reversed_link()
          self.add_link(link_i2j)
          self.add_link(link_j2i)


class FatTree (Topology):
  """Construct a FatTree topology with a given number of pods"""
  def __init__(self, num_pods=4, create_io_worker=None, gui=False,
               use_portland_addressing=True, ip_format_str="123.123..%d.%d",
               netns_hosts=True):
    """
    If not use_portland_addressing, use a format string for assigning
    IP addresses to hosts. Takes two digits to be interpolated, the switch
    dpid and the port number.

    For example, "10.%d.%d.255" will assign hosts the IP address
    10.DPID.PORT_NUMBER.255, where DPID is the dpid of their ingress
    switch, and PORT_NUMBER is the number of the switch's access link.
    """
    host_cls = NamespaceHost if netns_hosts == True else Host
    super(FatTree, self).__init__(create_io_worker=create_io_worker,
                                  gui=gui, host_cls=host_cls)
    if num_pods < 2:
      raise ValueError("Can't handle Fat Trees with less than 2 pods")
    Topology.__init__(self, create_io_worker=create_io_worker, gui=gui)
    self.cores = []
    self.aggs = []
    self.edges = []
    self.use_portland_addressing = use_portland_addressing
    self.ip_format_str = ip_format_str

    self.construct_tree(num_pods)

    if self.gui is not None:
      self.gui.launch()

  def construct_tree(self, num_pods):
    """
    According to  "A Scalable, Commodity Data Center Network Architecture",
    k = number of ports per switch = number of pods
    number core switches =  (k/2)^2
    number of edge switches per pod = k / 2
    number of agg switches per pod = k / 2
    number of hosts attached to each edge switch = k / 2
    number of hosts per pod = (k/2)^2
    total number of hosts  = k^3 / 4
    """
    self.log.debug("Constructing fat tree with %d pods" % num_pods)

    # self == store these numbers for later
    k = self.k = self.ports_per_switch = self.num_pods = num_pods
    self.hosts_per_pod = self.total_core = (k/2)**2
    self.edge_per_pod = self.agg_per_pod = self.hosts_per_edge = k / 2
    self.total_hosts = self.hosts_per_pod * num_pods

    access_links = set()
    network_links = set()

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
      if self.use_portland_addressing:
        portland_ip_addr = IPAddr("123.%d.%d.%d" %
                         (current_pod_id, position, edge_port_no))
        (host, host_access_links) = create_host(edge, portland_mac, portland_ip_addr,
                                                lambda switch: switch.ports[edge_port_no])
      else:
        (host, host_access_links) = create_host(edge, mac_or_macs=portland_mac, ip_format_str=self.ip_format_str,
                                                get_switch_port=lambda switch: switch.ports[edge_port_no])
      host.pod_id = current_pod_id
      self.add_host(host)
      access_links = access_links.union(set(host_access_links))

    # Now edge <-> agg
    for pod_id in range(num_pods):
      if not pod_id % 10:
        log.debug("edge<->agg for pod %d / %d" % (pod_id, num_pods))
      current_aggs = []
      for _ in  range(self.agg_per_pod):
        current_dpid += 1
        agg = create_switch(current_dpid, self.ports_per_switch,
                            can_connect_to_endhosts=False)
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
          network_links.add(Link(edge, edge.ports[current_edge_port_no],
                                      agg, agg.ports[current_agg_port_no]))
          network_links.add(Link(agg, agg.ports[current_agg_port_no],
                                      edge, edge.ports[current_edge_port_no]))
          current_edge_port_no += 1
        current_agg_port_no += 1

      self.aggs += current_aggs

    # Finally, agg <-> core
    for i in range(self.total_core):
      if not i % 100:
        log.debug("agg<->core %d / %d" % (i, self.total_core))
      current_dpid += 1
      self.cores.append(create_switch(current_dpid, self.ports_per_switch,
                                      can_connect_to_endhosts=False))

    core_cycler = itertools.cycle(self.cores)
    for agg in self.aggs:
      # agg ports (k/2)+1 through k connect to cores
      # core port i+1 connects to pod i
      for agg_port_no in range(k/2+1, k+1):
        core = core_cycler.next()
        core_port_no = agg.pod_id + 1
        network_links.add(Link(agg, agg.ports[agg_port_no], core,
                                    core.ports[core_port_no]))
        network_links.add(Link(core, core.ports[core_port_no], agg,
                                    agg.ports[agg_port_no]))

    switches = self.cores + self.aggs + self.edges
    #self._populate_dpid2switch(switches)
    for switch in switches:
      if not self.has_switch(switch):
        self.add_switch(switch)
    self.wire_tree(access_links, network_links)
    self._sanity_check_tree(access_links, network_links)
    self.log.debug("Fat tree construction: done (%d cores, %d aggs,"
                   "%d edges, %d hosts)" %
                   (len(self.cores), len(self.aggs), len(self.edges),
                    len(self.hosts)))

  def wire_tree(self, access_links, network_links):
    # Auxiliary data to make get_connected_port efficient
    for access_link in access_links:
      self.patch_panel.add_access_link(access_link)
    for link in network_links:
      self.patch_panel.add_link(link)
    self.get_connected_port = self.patch_panel.get_other_side

  def _sanity_check_tree(self, access_links, network_links):
    # TODO(cs): this should be in a unit test, not here
    if len(access_links) != self.total_hosts:
      raise RuntimeError("incorrect # of access links (%d, s/b %d)" % \
                          (len(access_links),len(self.total_hosts)))

    # k = number of ports per switch = number of pods
    # number core switches =  (k/2)^2
    # number of edge switches per pod = k / 2
    # number of agg switches per pod = k / 2
    total_switches = self.total_core + ((self.edge_per_pod + self.agg_per_pod) * self.k)
    # uni-directional links (on in both directions):
    total_network_links = (total_switches * self.k) - self.total_hosts
    if len(network_links) != total_network_links:
      raise RuntimeError("incorrect # of internal links (%d, s/b %d)" % \
                          (len(network_links),total_network_links))

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
