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

"""
Basic representation of network topology.
"""


import logging

from pox.openflow.libopenflow_01 import ofp_phy_port

from sts.entities.hosts import HostAbstractClass
from sts.entities.hosts import Host
from sts.entities.sts_entities import HostInterface
from sts.entities.sts_entities import FuzzSoftwareSwitch
from sts.entities.sts_entities import Link
from sts.entities.sts_entities import AccessLink
from sts.topology.graph import Graph
from sts.topology.graph import TopologyGraph

from sts.util.console import msg


class Topology(object):
  """
  Keeps track of the network elements.

  When extending this class, make sure to revisit and change the policies (if
  necessary) for example changing can_add_host, can_add_switch, can_add_link,
  can_change_link_status, can_crash_switch.
  """
  def __init__(self, patch_panel, topo_graph=None,
               hosts=None, switches=None, controllers=None,
               links=None, host_cls=Host, switch_cls=FuzzSoftwareSwitch,
               link_cls=Link, access_link_cls=AccessLink,
               interface_cls=HostInterface, port_cls=ofp_phy_port,
               sts_console=msg):
    super(Topology, self).__init__()
    self.host_cls = host_cls
    self.switch_cls = switch_cls
    self.link_cls = link_cls
    self.access_link_cls = access_link_cls
    self.interface_cls = interface_cls
    self.port_cls = port_cls
    self.patch_panel = patch_panel
    self._g = Graph()
    self._topo_graph = topo_graph or TopologyGraph()
    self._dpid2vertex = {}
    self.failed_switches = set()
    self.msg = sts_console
    self.log = logging.getLogger("sts.topology.base.Topology")

  def _host_check(self, vertex, attrs):
    """Some basic check for host type"""
    return isinstance(attrs.get('obj', None), self.host_cls)

  @property
  def can_add_host(self):
    """Return True if hosts can be added to the topology.

    Some topologies are mutable while others are not.
    """
    return True

  @property
  def can_add_switch(self):
    """Return True if switches can be added to the topology.

    Some topologies are mutable while others are not.
    """
    return True

  @property
  def can_add_link(self):
    """Return True if links can be added to the topology.

    Some topologies are mutable while others are not.
    """
    return True

  @property
  def can_change_link_status(self):
    """
    True if links can change status (up or down).

    Some topologies are mutable while others are not.
    """
    return True

  @property
  def can_crash_switch(self):
    """
    True if the switches in the topology can shutdown and reboot switches.
    """
    return True

  @property
  def config_graph(self):
    """Return the graph of the configuration of each network element."""
    return self._topo_graph

  @property
  def switches(self):
    """List of switches in the topology"""
    switches = [switch for _, switch in self.switches_iter(True)]
    switches.sort(key=lambda sw: sw.dpid)
    return switches

  @property
  def hosts(self):
    """List of hosts in the topology"""
    hosts = [host for _, host in self.hosts_iter(True)]
    hosts.sort(key=lambda h: h.hid)
    return hosts

  def hosts_iter(self, include_obj=True):
    """
    Iterate over hosts in the topology

    Args:
      include_obj: If true not only host id is returned but the object as well
    """
    for name, attrs in self._g.vertices_iter_with_check(self._host_check, True):
      if include_obj:
        yield name, attrs['obj']
      else:
        yield name

  def switches_iter(self, include_obj=True):
    """
    Iterate over switches in the topology

    Args:
      include_obj: If true not only switch id is returned but the object as well
    """
    for key, value in self._g.vertices_iter(include_attrs=True):
      #if isinstance(value.get('obj', None), self.switch_cls):
      if isinstance(value.get('obj', None), self.switch_cls):
        if include_obj:
          yield key, value['obj']
        else:
          yield key

  def _host_vertex_id(self, host):
    """Utility method to get the vertex ID for a host"""
    return getattr(host, 'name', getattr(host, 'hid', host))

  def add_host(self, host):
    """
    Add Host to the topology.

    Args:
      host: Must be an instance of sts.entities.hosts.HostAbstractClass
    """
    assert self.can_add_host
    assert isinstance(host, HostAbstractClass)
    vertex_id = self._host_vertex_id(host)
    assert not self.has_host(vertex_id), "Host '%s' already added" % host
    self._g.add_vertex(vertex_id, obj=host)
    return vertex_id

  def remove_host(self, host):
    """Remove host from the topology

    Also remove all associated links
    """
    assert self.has_host(host)
    vertex_id = self._host_vertex_id(host)
    # Remove associated links
    for interface in host.interfaces:
      iface_edges = self._g.edges_src(interface) + self._g.edges_dst(interface)
      for edge in iface_edges:
        self._g.remove_edge(*edge)
    self._g.remove_vertex(vertex_id)
    self.patch_panel.remove_host(host)

  def has_host(self, host):
    """Return host (or name of the host) exists."""
    return self._g.has_vertex(self._host_vertex_id(host))

  def get_host(self, hid):
    """Given the host id return the host object"""
    vertex_id = self._host_vertex_id(hid)
    return self._g.vertices[vertex_id]['obj']

  def _switch_vertex_id(self, switch):
    if switch in self._dpid2vertex:
      return self._dpid2vertex[switch]
    return getattr(switch, 'name', getattr(switch, 'dpid', switch))

  def has_switch(self, switch):
    """Return switch (or name of the switch) exists."""
    vertex_id = self._switch_vertex_id(switch)
    return self._g.has_vertex(vertex_id)

  def get_switch(self, dpid):
    """Given the switch dpid return the switch object"""
    if dpid in self._dpid2vertex:
      vertex_id = self._dpid2vertex[dpid]
    else:
      vertex_id = self._switch_vertex_id(dpid)
    return self._g.vertices[vertex_id]['obj']

  def add_switch(self, switch):
    """Add switch to the topology"""
    assert self.can_add_switch
    assert hasattr(switch, 'dpid')
    assert not self.has_switch(switch), ("Switch '%s' "
                                         "already added" % switch.dpid)
    vertex_id = self._switch_vertex_id(switch)
    switch.name = vertex_id
    self._dpid2vertex[switch.dpid] = vertex_id
    self._g.add_vertex(vertex_id, obj=switch)
    return switch

  def remove_switch(self, switch):
    assert self.has_switch(switch)
    vertex_id = self._switch_vertex_id(switch)
    del self._dpid2vertex[switch.dpid]
    # Remove associated links
    for port in switch.ports.values():
      edges = self._g.edges_src(port) + self._g.edges_dst(port)
      for edge in edges:
        self._g.remove_edge(*edge)
    self._g.remove_vertex(vertex_id)

  def add_link(self, link):
    """Add link to the topology"""
    assert self.can_add_link
    print "LINK TYPE", type(link)
    print "EX", self.link_cls, self.access_link_cls
    assert isinstance(link, (self.link_cls, self.access_link_cls))
    assert not self.has_link(link)
    if hasattr(link, 'start_node'):
      self._g.add_edge(link.start_node, link.start_port)
      self._g.add_edge(link.start_port, link.start_node)
      self._g.add_edge(link.start_port, link.end_port, obj=link)
    else:
      self._g.add_edge(link.node1, link.port1)
      self._g.add_edge(link.node2, link.port2)
      self._g.add_edge(link.port1, link.node1)
      self._g.add_edge(link.port2, link.node2)
      self._g.add_edge(link.port1, link.port2, obj=link)
      self._g.add_edge(link.port2, link.port1, obj=link)
    # Make sure the patch panel do whatever physically necessary to connect
    # the link
    if isinstance(link, self.access_link_cls):
      self.patch_panel.add_access_link(link)
    elif isinstance(link, self.link_cls):
      self.patch_panel.add_link(link)
    return link

  def has_link(self, link):
    assert isinstance(link, (self.link_cls, self.access_link_cls))
    if hasattr(link, 'start_node'):
      return self._g.has_edge(link.start_port, link.end_port)
    else:
      return self._g.has_edge(link.port1, link.port2)

  def remove_link(self, link):
    assert self.has_link(link)
    if hasattr(link, 'start_node'):
      self._g.remove_edge(link.start_port, link.end_port)
      self.patch_panel.remove_network_link(link.start_node, link.start_port,
                                           link.end_node, link.end_port)
    else:
      self._g.remove_edge(link.port1, link.port2)
      self._g.remove_edge(link.port2, link.port1)
      self.patch_panel.remove_access_link(link.host, link.interface,
                                          link.switch, link.switch_port)

  def get_link(self, s1, s2):
    """Return list of Links between two switches"""
    switch1 = self.get_switch(s1)
    switch2 = self.get_switch(s2)
    links = []
    for src_port in switch1.ports.itervalues():
      for dst_port in switch2.ports.itervalues():
        if self._g.has_edge(src_port, dst_port):
          links.append(self._g.get_edge(src_port, dst_port)['obj'])
        if self._g.has_edge(dst_port, src_port):
          links.append(self._g.get_edge(dst_port, src_port)['obj'])
    return links

  def crash_switch(self, switch):
    """Make the switch crash (or just turn it off)"""
    assert self.can_crash_switch, "Topology doesn't support crashing switches"
    assert self.has_switch(switch)
    s = self.get_switch(switch)
    self.msg.event("Crashing switch %s" % str(s))
    s.fail()
    self.failed_switches.add(s)

  @property
  def live_switches(self):
    """Return the software_switchs which are currently up"""
    return set(self.switches) - self.failed_switches

  @property
  def live_edge_switches(self):
    """Return the switches which are currently up and can connect to hosts"""
    edge_switches = set([sw for sw in self.switches if sw.can_connect_to_endhosts])
    return edge_switches - self.failed_switches

  def recover_switch(self, switch, down_controller_ids=None):
    """Reboot previously crashed switch"""
    s = self.get_switch(switch)
    self.msg.event("Rebooting switch %s" % str(s))
    if down_controller_ids is None:
      down_controller_ids = set()
    if s not in self.failed_switches:
      self.log.warn("Switch %s not currently down. (Currently down: %s)" %
                    (str(s), str(self.failed_switches)))
    connected_to_at_least_one = s.recover(down_controller_ids=down_controller_ids)
    if connected_to_at_least_one:
      self.failed_switches.remove(s)
    return connected_to_at_least_one

  def migrate_host(self, old_switch, old_port, new_switch, new_port):
    """
    Migrate the host from the old (ingress switch, port) to the new
    (ingress switch, port). Note that the new port must not already be
    present, otherwise an exception will be thrown (we treat all switches as
    configurable software switches for convenience, rather than hardware switches
    with a fixed number of ports)
    """
    # TODO (AH): Implement migrate host
    return None
    """
    old_switch = self.get_switch(old_switch)
    new_switch = self.get_switch(new_switch)

    if old_port in old_switch.ports:
      old_port = old_switch.ports[old_port]

    if old_port not in old_port.ports.values():
      raise ValueError("unknown old port %d" % old_port)

    if new_port in old_switch.ports:
      new_port = old_switch.ports[new_port]

    if new_port not in new_port.ports.values():
      raise ValueError("unknown new port %d" % new_port)


    (host, interface) = self.patch_panel.get_other_side(old_switch, old_port)

    if (not (isinstance(host, self.host_cls) and
               isinstance(interface, self.interface_cls))):
      raise ValueError("(%s,%s) does not connect to a host!" %
                       (str(old_switch), str(old_port)))


    if self.patch_panel.is_port_connected(new_port):
      raise RuntimeError("new ingress port %d already connected!" % new_port)

    # now that we've verified everything, actually make the change!
    # first, drop the old mappings
    del self.port2access_link[old_port]
    del self.interface2access_link[interface]
    old_ingress_switch.take_port_down(old_port)

    # now add new mappings
    # For now, make the new port have the same ip address as the old port.
    # TODO(cs): this would break PORTLAND routing! Need to specify the
    #           new mac and IP addresses
    new_ingress_port = self.port_cls(port_no=new_ingress_portno,
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
    """

#################################
  @property
  def access_links(self):
    return self.patch_panel.access_links

  @property
  def network_links(self):
    return self.patch_panel.network_links

  @property
  def cut_links(self):
    return self.patch_panel.cut_links


  @property
  def live_links(self):
    return self.patch_panel.live_links

  def sever_link(self, link):
    self.patch_panel.sever_link(link)

  def repair_link(self, link):
    self.patch_panel.repair_link(link)

  def create_access_link(self, host, interface, switch, port):
    assert self.has_host(host)
    assert self.has_switch(switch)
    assert interface in host.interfaces
    assert port in switch.ports or port in switch.ports.values()
    return self.patch_panel.create_access_link(host, interface, switch, port)

  def remove_access_link(self, host, interface, switch, port, remove_all=True):
    assert self.has_host(host)
    assert self.has_switch(switch)
    assert interface is None or interface in host.interfaces
    assert port is None or port in switch.ports or port in switch.ports.values()
    if interface is not None:
      interfaces = [interface]
    else:
      interfaces = host.interfaces
    if port is not None:
      ports = [port]
    else:
      ports = switch.ports.values()

    edges = []
    for iface in interfaces:
      for p in ports:
        if self._g.has_edge(iface, p):
          edges.append((iface, p))
        if self._g.has_edge(iface, p):
          edges.append((p, iface))
    if len(edges) > 2 and remove_all == False:
      raise ValueError("Multiple links connecting '%s'->'%s'" % (host,
                                                                 switch))
    assert len(edges) > 0, "No link connecting '%s'->'%s'" % (host,
                                                              switch)
    for edge in edges:
      self._g.remove_edge(*edge)
    return self.patch_panel.remove_access_link(host, interface, switch, port,
                                               remove_all=remove_all)

  def remove_network_link(self, src_switch, src_port, dst_switch, dst_port,
                          remove_all=True):
    assert self.has_switch(src_switch)
    assert self.has_switch(dst_switch)
    assert src_port is None or src_port in src_switch.ports or\
           src_port in src_switch.ports.values()
    assert dst_port is None or dst_port in dst_switch.ports or\
           dst_port in dst_switch.ports.values()
    if src_port is not None:
      src_ports = [src_port]
    else:
      src_ports = src_switch.ports.values()
    if dst_port is not None:
      dst_ports = [dst_port]
    else:
      dst_ports = dst_switch.ports.values()

    edges = []
    for sp in src_ports:
      for dp in dst_ports:
        if self._g.has_edge(sp, dp):
          edges.append((sp, dp))

    if len(edges) > 1 and remove_all == False:
      raise ValueError("Multiple links connecting '%s'->'%s'" % (src_switch,
                                                                 dst_switch))
    assert len(edges) > 0, "No link connecting '%s'->'%s'" % (src_switch,
                                                              dst_switch)
    for edge in edges:
      self._g.remove_edge(*edge)
    return self.patch_panel.remove_network_link(src_switch, src_port,
                                                dst_switch, dst_ports,
                                                remove_all=remove_all)
