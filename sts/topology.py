# Copyright 2011-2013 Colin Scott
# Copyright 2012-2013 Andrew Or
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
from invariant_checker import InvariantChecker
from entities import FuzzSoftwareSwitch, Link, Host, HostInterface, AccessLink, NamespaceHost
from pox.openflow.software_switch import DpPacketOut, SoftwareSwitch
from pox.openflow.libopenflow_01 import *
from pox.lib.revent import EventMixin
from sts.util.console import msg
import itertools
import logging
from collections import defaultdict

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
  host = NamespaceHost(ip_addr_str, create_io_worker, cmd=cmd)
  interface = host.interfaces[0]
  access_link = AccessLink(host, interface, ingress_switch, get_switch_port(ingress_switch))
  return (host, [access_link]) # single item list to be consistent with create_host

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

class LinkTracker(object):
  def __init__(self, dpid2switch, port2access_link, interface2access_link,
               port2internal_link):
    self.dpid2switch = dpid2switch
    self.port2access_link = port2access_link
    self.interface2access_link = interface2access_link
    self.port2internal_link = port2internal_link
    # { (start dpid, end dpid) -> link }
    self.dpidpair2link = {
      (link.start_software_switch.dpid, link.end_software_switch.dpid) : link
      for link in self.network_links
    }
    # Metatdata for simulated failures
    # sts.entities.Link objects
    self.cut_links = set()

  @property
  def network_links(self):
    return self.port2internal_link.values()

  @property
  def access_links(self):
    return self.interface2access_link.values()

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
    link.start_software_switch.bring_port_up(link.start_port)
    self.cut_links.remove(link)
    # TODO(cs): the switch on the other end of the link should eventually
    # notice that the link has come back up!

  def create_access_link(self, host, interface, switch, port):
    '''
    Create an access link between a host and a switch
    If no interface is provided, an unused interface is used
    If no port is provided, an unused port is used
    '''
    if interface is None:
      interface = self.find_unused_interface(host)
    if port is None:
      port = self.find_unused_port(switch)
    link = AccessLink(host, interface, switch, port)
    self.port2access_link[port] = link
    self.interface2access_link[interface] = link
    return link

  def remove_access_link(self, host, switch):
    ''' Remove an access link between a host and a switch '''
    for port in switch.ports.values():
      if port in self.port2access_link.keys():
        link = self.port2access_link[port]
        if link.host is host and link.switch is switch:
          del self.port2access_link[port]
    for interface in host.interfaces:
      if interface in self.interface2access_link.keys():
        link = self.interface2access_link[interface]
        if link.host is host and link.switch is switch:
          del self.interface2access_link[interface]

  def create_network_link(self, from_switch, from_port, to_switch, to_port):
    '''
    Create a unidirectional network (internal) link between two switches
    If a port is not provided, an unused port in the corresponding switch is used
    '''
    if from_port is None:
      from_port = self.find_unused_port(from_switch)
    if to_port is None:
      to_port = self.find_unused_port(to_switch)
    link = Link(from_switch, from_port, to_switch, to_port)
    self.port2internal_link[from_port] = link
    self.dpidpair2link[(from_switch.dpid, to_switch.dpid)] = link
    return link

  def remove_network_link(self, from_switch, to_switch):
    ''' Remove a unidirectional network (internal) link between two switches '''
    for port in from_switch.ports.values():
      if port in self.port2internal_link.keys():
        link = self.port2internal_link[port]
        if link.start_software_switch is from_switch and\
           link.end_software_switch is to_switch:
          del self.port2internal_link[port]
          del self.dpid2pair2link[(link.start_software_switch.dpid,
                                   link.end_software_switch.dpid)]

  def find_unused_port(self, switch):
    ''' Find a switch's unused port; if no such port exists, create a new one '''
    for _, port in switch.ports.items():
      if port not in self.port2internal_link.keys() and \
        port not in self.port2access_link.keys():
        return port
    new_port_number = max([port_number for port_number in switch.ports.keys()])+1
    new_port = ofp_phy_port(port_no=new_port_number)
    switch.ports[new_port_number] = new_port
    return new_port

  def find_unused_interface(self, host):
    ''' Find a host's unused interface; if no such interface exists, create a new one '''
    for interface in host.interfaces:
      if interface not in self.interface2access_link.keys():
        return interface
    new_interface_addr = max([interface.hw_addr.toInt() for interface in host.interfaces])+1
    new_interface_addr = hex(new_interface_addr)[2:].zfill(12)
    new_interface_addr = new_interface_addr[0:2]+":"+new_interface_addr[2:4]+":"+\
                            new_interface_addr[4:6]+":"+new_interface_addr[6:8]+":"+\
                            new_interface_addr[8:10]+":"+new_interface_addr[10:12]
    new_interface_addr = EthAddr(new_interface_addr)
    new_interface = HostInterface(new_interface_addr)
    host.interfaces.append(new_interface)
    return new_interface

  def port_connected(self, port):
    ''' Return whether the port is currently connected to anything '''
    return (port in self.port2access_link or
            port in self.interface2access_link or
            port in self.port2internal_link)

  def __call__(self, node, port):
    '''
    Given a node and a port, return a tuple (node, port) that is directly
    connected to the port.

    This can be used in 2 ways
    - node is a Host type and port is a HostInterface type
    - node is a Switch type and port is a ofp_phy_port type.
    '''
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
      raise ValueError("Unknown port %s on node %s" % (str(port),str(node)))

  def _get_switch_by_dpid(self, dpid):
    if dpid not in self.dpid2switch:
      raise ValueError("Unknown switch dpid: %s" % str(dpid))

    return self.dpid2switch[dpid]

  def migrate_host(self, old_ingress_dpid, old_ingress_portno,
                   new_ingress_dpid, new_ingress_portno):
    '''
    Migrate the host from the old (ingress switch, port) to the new
    (ingress switch, port). Note that the new port must not already be
    present, otherwise an exception will be thrown (we treat all switches as
    configurable software switches for convenience, rather than hardware switches
    with a fixed number of ports)
    '''
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
    new_ingress_port = ofp_phy_port(port_no=new_ingress_portno,
                                    hw_addr=old_port.hw_addr,
                                    name="eth%d" % new_ingress_portno,
                                    config=old_port.config,
                                    state=old_port.state,
                                    curr=old_port.curr,
                                    advertised=old_port.advertised,
                                    supported=old_port.supported,
                                    peer=old_port.peer)
    new_ingress_switch.bring_port_up(new_ingress_port)
    new_access_link = AccessLink(host, interface, new_ingress_switch, new_ingress_port)
    self.port2access_link[new_ingress_port] = new_access_link
    self.interface2access_link[interface] = new_access_link

class Topology(object):
  '''
  Abstract base class of all topology types. Wraps the edges and vertices of
  the network.
  '''
  def __init__(self, create_io_worker=None, gui=False):
    self.create_io_worker = create_io_worker
    self.dpid2switch = {}
    self.hid2host = {}

    # SoftwareSwitch objects
    self.failed_switches = set()
    self.link_tracker = None

    self.gui = None
    if gui:
      from sts.gui.launcher import TopologyGui
      self.gui = TopologyGui(self)

  def _populate_dpid2switch(self, switches):
    self.dpid2switch = {
      switch.dpid : switch
      for switch in switches
    }

  @property
  def access_links(self):
    return self.link_tracker.access_links

  @property
  def network_links(self):
    return self.link_tracker.network_links

  @property
  def cut_links(self):
    return self.link_tracker.cut_links

  @property
  def switches(self):
    switches = self.dpid2switch.values()
    switches.sort(key=lambda sw: sw.dpid)
    return switches

  @property
  def hosts(self):
    hosts = self.hid2host.values()
    hosts.sort(key=lambda h: h.hid)
    return hosts

  def get_link(self, dpid1, dpid2):
    if (dpid1, dpid2) not in self.link_tracker.dpidpair2link:
      raise ValueError("Unknown link (%d -> %d)" % (dpid1, dpid2))
    return self.link_tracker.dpidpair2link[(dpid1, dpid2)]

  def create_switch(self, switch_id, num_ports, can_connect_to_endhosts=True):
    ''' Create a switch and register it in the topology '''
    switch = create_switch(switch_id, num_ports, can_connect_to_endhosts)
    self.dpid2switch[switch_id] = switch
    self.link_tracker.dpid2switch[switch_id] = switch
    return switch

  def remove_switch(self, switch):
    '''
    Remove a switch, along with all associated links and any dangling
    hosts previously attached
    '''
    if switch not in self.dpid2switch.values():
      return
    # Remove associated network links
    for network_link in self.network_links:
      if network_link.start_software_switch is switch or\
         network_link.end_software_switch is switch:
        port = network_link.start_port
        if port in self.link_tracker.port2internal_link.keys():
          del self.link_tracker.port2internal_link[port]
    # Remove associated access links
    for access_link in self.access_links:
      if access_link.switch is switch:
        port = access_link.switch_port
        interface = access_link.interface
        host = access_link.host
        if port in self.link_tracker.port2access_link.keys():
          del self.link_tracker.port2access_link[port]
        if interface in self.link_tracker.interface2access_link.keys():
          del self.link_tracker.interface2access_link[interface]
        # Remove dangling hosts, if any
        for i in host.interfaces:
          if i in self.link_tracker.interface2access_link.keys():
            break
        else:
          del self.hid2host[host.hid]
    del self.dpid2switch[switch.dpid]

  def create_host(self, ingress_switch_or_switches, mac_or_macs=None, ip_or_ips=None,
                get_switch_port=get_switchs_host_port):
    ''' Create a host, register it in the topology, and wire it to the given switch(es) '''
    (host, access_links) = create_host(ingress_switch_or_switches, mac_or_macs,
                                      ip_or_ips, get_switch_port)
    self.hid2host[host.hid] = host
    for access_link in access_links:
      interface = access_link.interface
      port = access_link.switch_port
      self.link_tracker.port2access_link[port] = access_link
      self.link_tracker.interface2access_link[interface] = access_link
    return host

  def remove_host(self, host):
    ''' Remove a host and all associated access links '''
    if host not in self.hid2host.values():
      return
    # Remove associated access links
    for access_link in self.access_links:
      if access_link.host is host:
        port = access_link.switch_port
        interface = access_link.interface
        if port in self.link_tracker.port2access_link.keys():
          del self.link_tracker.port2access_link[port]
        if interface in self.link_tracker.interface2access_link.keys():
          del self.link_tracker.interface2access_link[interface]
    del self.hid2host[host.hid]

  def get_switch(self, dpid):
    if dpid not in self.dpid2switch:
      raise RuntimeError("unknown dpid %d" % dpid)
    return self.dpid2switch[dpid]

  def get_host(self, hid):
    if hid not in self.hid2host:
      raise RuntimeError("unknown hid %d" % hid)
    return self.hid2host[hid]

  @property
  def live_switches(self):
    ''' Return the software_switchs which are currently up '''
    return set(self.switches) - self.failed_switches

  @property
  def live_edge_switches(self):
    '''
    Return the software_switchs which are currently up and can connect to
    hosts
    '''
    edge_switches = set(filter(lambda sw: sw.can_connect_to_endhosts, self.switches))
    return edge_switches - self.failed_switches

  def ok_to_send(self, dp_event):
    ''' Return True if it is ok to send the dp_event arg '''
    if not self.link_tracker.port_connected(dp_event.port):
      return False

    try:
      (next_hop, next_port) = self.get_connected_port(dp_event.switch,
                                                      dp_event.port)
    except ValueError:
      log.warn("no such port %s on node %s" % (str(dp_event.port), str(dp_event.switch)))
      return False

    if isinstance(dp_event.node, Host) or isinstance(next_hop, Host):
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

  def recover_switch(self, software_switch, down_controller_ids=None):
    msg.event("Rebooting software_switch %s" % str(software_switch))
    if down_controller_ids is None:
      down_controller_ids = set()
    if software_switch not in self.failed_switches:
      log.warn("Switch %s not currently down. (Currently down: %s)" %
                (str(software_switch), str(self.failed_switches)))
    connected_to_at_least_one = software_switch\
                                 .recover(down_controller_ids=down_controller_ids)
    if connected_to_at_least_one:
      self.failed_switches.remove(software_switch)
    return connected_to_at_least_one

  @property
  def live_links(self):
    return self.link_tracker.live_links

  def sever_link(self, link):
    self.link_tracker.sever_link(link)

  def repair_link(self, link):
    self.link_tracker.repair_link(link)

  def create_access_link(self, host, interface, switch, port):
    return self.link_tracker.create_access_link(host, interface, switch, port)

  def remove_access_link(self, host, switch):
    return self.link_tracker.remove_access_link(host, switch)

  def create_network_link(self, from_switch, from_port, to_switch, to_port):
    return self.link_tracker.create_network_link(from_switch, from_port, to_switch, to_port)

  def remove_network_link(self, from_switch, to_switch):
    return self.link_tracker.remove_network_link(from_switch, to_switch)

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
    '''
    Bind sockets from the software_switchs to the controllers. For now, assign each
    switch to the next controller in the list in a round robin fashion.

    Controller info list is a list of ControllerConfig tuples
        - create_io_worker is a factory method for creating IOWorker objects.
          Takes a socket as a parameter
        - create_connection is a factory method for creating Connection objects
          which are connected to controllers. Takes a ControllerConfig object
          as a parameter
    '''
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
    self.link_tracker.migrate_host(old_ingress_dpid, old_ingress_portno,
                                   new_ingress_dpid, new_ingress_portno)

  @staticmethod
  def populate_from_topology(graph):
    '''
    Take a pox.lib.graph.graph.Graph and generate arguments needed for the
    simulator
    '''
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
    '''
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
    '''
    Topology.__init__(self, create_io_worker=create_io_worker, gui=gui)

    # Every switch has a link to every other switch + 1 host,
    # for N*(N-1)+N = N^2 total ports
    ports_per_switch = (num_switches - 1) + 1

    # Initialize switches
    switches = [ create_switch(switch_id, ports_per_switch)
                  for switch_id in range(1, num_switches+1) ]
    self._populate_dpid2switch(switches)
    if netns_hosts:
      host_access_link_pairs = [ create_netns_host(create_io_worker, switch)
                                 for switch in self.switches ]
    else:
      host_access_link_pairs = [ create_host(switch, ip_format_str=ip_format_str) for switch in self.switches ]
    access_link_list_list = []
    for host, access_link_list in host_access_link_pairs:
      self.hid2host[host.hid] = host
      access_link_list_list.append(access_link_list)

    # this is python's .flatten:
    access_links = list(itertools.chain.from_iterable(access_link_list_list))

    # grab a fully meshed patch panel to wire up these guys
    self.link_tracker = MeshTopology.FullyMeshedLinks(self.dpid2switch, access_links)
    self.get_connected_port = self.link_tracker

    if self.gui is not None:
      self.gui.launch()

  class FullyMeshedLinks(LinkTracker):
    '''
    A factory method (inner class) for creating a fully meshed network.
    Connects every pair of switches. Ports are in ascending order of
    the dpid of connected switch, while skipping the self-connections.
    I.e., for (dpid, portno):
        (0, 0) <-> (1,0)
        (2, 1) <-> (1,1)
    '''
    def __init__(self, dpid2switch, access_links=[]):
      port2access_link = { access_link.switch_port: access_link
                           for access_link in access_links }
      interface2access_link = { access_link.interface: access_link
                                for access_link in access_links }

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

      LinkTracker.__init__(self, dpid2switch, port2access_link,
                           interface2access_link, port2internal_link)

class FatTree (Topology):
  ''' Construct a FatTree topology with a given number of pods '''
  def __init__(self, num_pods=4, create_io_worker=None, gui=False,
               use_portland_addressing=True, ip_format_str="10.%d.%d.255"):
    ''' If not use_portland_addressing, use a format string for assigning
        IP addresses to hosts. Takes two digits to be interpolated, the switch
        dpid and the port number.
        For example, "10.%d.%d.255" will assign hosts the IP address
        10.DPID.PORT_NUMBER.255, where DPID is the dpid of their ingress
        switch, and PORT_NUMBER is the number of the switch's access link.
    '''
    if num_pods < 2:
      raise ValueError("Can't handle Fat Trees with less than 2 pods")
    Topology.__init__(self, create_io_worker=create_io_worker, gui=gui)
    self.cores = []
    self.aggs = []
    self.edges = []
    self.use_portland_addressing = use_portland_addressing
    self.ip_format_str = ip_format_str

    self.dpid2switch = {}
    self.hid2host = {}
    self.link_tracker = None
    self.construct_tree(num_pods)

    if self.gui is not None:
      self.gui.launch()

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
      self.hid2host[host.hid] = host
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
    self._populate_dpid2switch(switches)
    self.wire_tree(access_links, network_links)
    self._sanity_check_tree(access_links, network_links)
    log.debug('''Fat tree construction: done (%d cores, %d aggs,'''
              '''%d edges, %d hosts)''' %
              (len(self.cores), len(self.aggs), len(self.edges), len(self.hosts)))

  def wire_tree(self, access_links, network_links):
    # Auxiliary data to make get_connected_port efficient
    port2internal_link = { link.start_port: link
                           for link in network_links }
    port2access_link = { access_link.switch_port: access_link
                         for access_link in access_links }
    interface2access_link = { access_link.interface: access_link
                              for access_link in access_links }

    link_tracker = self.FatTreeLinks(port2access_link, interface2access_link,
                                     port2internal_link, self.dpid2switch)
    self.get_connected_port = link_tracker
    self.link_tracker = link_tracker

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

  class FatTreeLinks(LinkTracker):
    # TODO(cs): perhaps we should not use inheritance here, since it is
    # essentially entirely trivial. Alternatively, we could just have an
    # overloaded constructor in the LinkTracker class?
    def __init__(self, port2access_link, interface2access_link, port2internal_link, dpid2switch):
      LinkTracker.__init__(self, dpid2switch, port2access_link,
                           interface2access_link, port2internal_link)
