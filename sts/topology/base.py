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


import abc
import logging
from itertools import count

from pox.openflow.libopenflow_01 import ofp_phy_port
from pox.lib.addresses import EthAddr

from sts.entities.hosts import HostAbstractClass
from sts.entities.hosts import HostInterfaceAbstractClass
from sts.entities.hosts import Host
from sts.entities.base import DirectedLinkAbstractClass
from sts.entities.base import BiDirectionalLinkAbstractClass
from sts.entities.sts_entities import HostInterface
from sts.entities.sts_entities import FuzzSoftwareSwitch
from sts.entities.sts_entities import Link
from sts.entities.sts_entities import AccessLink

from sts.util.console import msg
from sts.util.convenience import class_fullname
from sts.util.convenience import object_fullname
from sts.util.convenience import random_eth_addr


class Graph(object):
  """
  A generic graph representation
  """

  def __init__(self, vertices=None, edges=None):
    """
    Args:
      vertices: dict of vertex_id->attrs
      edge: adjacency matrix
    """
    self._vertices = {}
    self._edges = {}
    if vertices is not None:
      assert isinstance(vertices, dict)
      for vertex, attrs in vertices.iteritems():
        attrs = attrs or {}
        self.add_vertex(vertex, **attrs)
    if edges is not None:
      assert isinstance(edges, dict)
      for v1, val1 in edges.iteritems():
        for v2, attrs in val1.iteritems():
          attrs = attrs or {}
          self.add_edge(v1, v2, **attrs)

  @property
  def vertices(self):
    """Returns a dict of the vertices in the graph."""
    return self._vertices

  def vertices_iter(self, include_attrs=False):
    """Return an iterator over vertices"""
    for vertex, attrs in self._vertices.iteritems():
      if include_attrs:
        yield vertex, attrs
      else:
        yield vertex

  def vertices_iter_with_check(self, check, include_attrs=False):
    """
    Iterate over vertices in the topology and return vertices which
    check(vertex_id, attrs) is True
    """
    for vertex, attrs in self.vertices_iter(include_attrs=True):
      if check(vertex, attrs):
        if include_attrs:
          yield vertex, attrs
        else:
          yield vertex

  @property
  def edges(self):
    """
    Returns a list of the edges in the graph.

    Each edge is represented as a tuple of start, end vertices and attrs dict.
    """
    edges = []
    for v1, val1 in self._edges.iteritems():
      for v2, attrs in val1.iteritems():
        edges.append((v1, v2, attrs))
    return edges

  def add_vertex(self, vertex, **attrs):
    """Add vertex to the graph."""
    self._vertices[vertex] = attrs
    return vertex

  def remove_vertex(self, vertex, remove_edges=True):
    assert self.has_vertex(vertex)
    edges = []
    for edge in self.edges_iter(include_attrs=False):
      if vertex in edge:
        edges.append(edge)
    if remove_edges == False:
      assert len(edges) == 0, "Vertex is part of some edges"
    for edge in edges:
      self.remove_edge(*edge)
    del self._vertices[vertex]

  def has_vertex(self, vertex):
    """Return True if the graph contains the vertex"""
    return vertex in self.vertices

  def edges_iter(self, include_attrs=False):
    """
    Returns an iterator of the edges in the graph.

    Each edge is represented as a tuple of start, end vertices and attrs dict.
    """
    for v1, val1 in self._edges.iteritems():
      for v2, attrs in val1.iteritems():
        if include_attrs:
          yield v1, v2, attrs
        else:
          yield v1, v2

  def edges_iter_with_check(self, check, include_attrs=False):
    """
    Iterate over edges in the topology and return edges which
    check(v1, v2, attrs) is True
    """
    for v1, v2, attrs in self.edges_iter(include_attrs=True):
      if check(v1, v2, attrs):
        if include_attrs:
          yield v1, v2, attrs
        else:
          yield v1, v2

  def get_edge(self, v1, v2):
    """Return the edge between v1 and v2."""
    return self._edges[v1][v2]

  def add_edge(self, v1, v2, **attrs):
    """Add edge between v1 and v2."""
    if v1 not in self.vertices:
      self.add_vertex(v1)
    if v2 not in self.vertices:
      self.add_vertex(v2)
    if self._edges.get(v1, None) is None:
      self._edges[v1] = {}
    self._edges[v1][v2] = attrs
    return v1, v2

  def remove_edge(self, v1, v2):
    assert self.has_edge(v1, v2)
    del self._edges[v1][v2]

  def has_edge(self, v1, v2):
    """Return True if an edge exists between two vertices v1 and v2"""
    try:
      self.get_edge(v1, v2)
      return True
    except KeyError:
      return False

  def edges_src(self, v1):
    """Return list of edges in which v1 is source"""
    adj = self._edges.get(v1, {})
    edges = []
    for vertex in adj:
      edges.append((v1, vertex))
    return edges

  def edges_dst(self, v2):
    """Return list of edges in which v2 is destination"""
    edges = []
    for v1, adj in self._edges.iteritems():
      if v2 in adj:
        edges.append((v1, v2))
    return edges


class VertexType(object):
  """Vertices Type for Network graph"""
  HOST = 'host'
  SWITCH = 'switch'
  PORT = 'PORT'
  INTERFACE = 'INTERFACE'


class TopologyGraph(object):
  """
  A high level graph of the network topology.
  """

  _host_hids = count(1) # host id counter
  _dpids = count(1) # dpid counter


  def __init__(self, hosts=None, switches=None, links=None):
    super(TopologyGraph, self).__init__()
    self._g = Graph()

    # Some basic checks to deal the graph
    self._host_check = lambda vertex, attrs: attrs.get('vtype', None) == VertexType.HOST
    self._interface_check = lambda vertex, attrs: attrs.get('vtype', None) == VertexType.INTERFACE
    self._switch_check = lambda vertex, attrs: attrs.get('vtype', None) == VertexType.SWITCH
    self._port_check = lambda vertex, attrs: attrs.get('vtype', None) == VertexType.PORT
    def link_check(v1, v2, attrs):
      # Check if it's an actual link
      src_node = attrs.get('src_node', None)
      dst_node = attrs.get('dst_node', None)
      return src_node is not None and dst_node is not None
    self._link_check = link_check

    # Load initial configurations
    hosts = hosts or []
    switches = switches or []
    links = links or []
    for host in hosts:
      self.add_host(**host)
    for switch in switches:
      self.add_switch(**switch)
    for link in links:
      self.add_link(**link)

  def hosts_iter(self, include_attrs=False):
    """
    Iterate over hosts in the topology

    Args:
      include_attr: If true not only host is returned but the attributes as well
    """
    return self._g.vertices_iter_with_check(check=self._host_check,
                                            include_attrs=include_attrs)

  def interfaces_iter(self, include_attrs=False):
    """
    Iterate over host interfaces in the topology

    Args:
      include_attr: If true not only interfaces are returned but the attributes
                    as well
    """
    return self._g.vertices_iter_with_check(check=self._interface_check,
                                            include_attrs=include_attrs)

  def ports_iter(self, include_attrs=False):
    """
    Iterate over switch ports in the topology

    Args:
      include_attr: If true not only ports are returned but the attributes
                    as well
    """
    return self._g.vertices_iter_with_check(check=self._port_check,
                                            include_attrs=include_attrs)

  def switches_iter(self, include_attrs=False):
    """
    Iterate over switches in the topology

    Args:
      include_attr: If true not only switches are returned but the attributes
                    as well
    """
    return self._g.vertices_iter_with_check(check=self._switch_check,
                                            include_attrs=include_attrs)

  def links_iter(self, include_attrs=False):
    """
    Iterate over links in the topology

    Args:
      include_attr: If true not only links are returned but the attributes
                    as well
    """
    for src_port, dst_port, value in self.edges_iter(include_attrs=True):
      if not self._link_check(src_port, dst_port, value):
        continue
      src_node = value.get('src_node', None)
      dst_node = value.get('dst_node', None)
      if include_attrs:
        yield src_node, src_port, dst_node, dst_port, value
      else:
        yield src_node, src_port, dst_node, dst_port

  def edges_iter(self, include_attrs=False):
    """
    Iterate over all edges in the topology (including the artificial
    host->interface and switch-port)

    Args:
      include_attr: If true not only edges are returned but the attributes
                    as well
    """
    return self._g.edges_iter(include_attrs=include_attrs)

  def add_host(self, interfaces=None, name=None, hid=None,
               num_used_interfaces=None, **kwargs):
    """
    Add Host to the topology

    kwargs:
      interfaces: list of interfaces connected to the host (default [])
      name: human readable name for the host (default h{hid})
      hid: unique identifier for host (default autogen integer)
      num_used_interfaces: interfaces to be assumed used and never use them
                           when new links are added (the first n-ifaces in the
                           interfaces list) (default 0)
      kwargs: additional arguments to passed to the host factory
    """
    attrs = kwargs.copy()
    vtype = attrs.get('vtype', VertexType.HOST)
    hid = hid if hid else self._host_hids.next()
    vertex_id = name or "h%s" % hid
    assert vertex_id not in self._g.vertices, "Host '%s' is already added" % hid
    interfaces = interfaces if interfaces else []
    interfaces = interfaces if isinstance(interfaces, list) else [interfaces]
    assert len(interfaces) >= num_used_interfaces

    # set unique port no for each interface
    next_port_no = 0
    for interface in interfaces:
      port_no = interface.get('port_no', next_port_no)
      port_no = port_no or next_port_no
      interface['port_no'] = port_no
      next_port_no = max(next_port_no, port_no) + 1
      if not interface.get('name', None):
        interface['name'] = "%s-eth%s" % (vertex_id, port_no)

      interface['vtype'] = interface.get('vtype', VertexType.INTERFACE)
      ips = interface.get('ips', [])
      ips = ips if isinstance(ips, list) else [ips]
      interface['ips'] = ips
      self._g.add_vertex(interface['name'], **interface)
    attrs['interfaces'] = interfaces
    attrs['name'] = vertex_id
    attrs['hid'] = hid
    attrs['num_used_interfaces'] = num_used_interfaces
    attrs['vtype'] = vtype
    self._g.add_vertex(vertex_id, **attrs)
    return vertex_id

  def add_switch(self, dpid, name=None, ports=None, num_used_ports=0, **kwargs):
    """
    Add a switch to the topology

    kwargs:
      dpid: switch unique ID (default auto-generated integer)
      name: switch unqiue human readable name (default s{dpid})
      ports: list of switch ports
      num_used_ports: number of reserved ports
      kwargs: additional arguments passed to the switch factory
    """
    attrs = kwargs.copy()
    vtype = attrs.get('vtype', VertexType.SWITCH)
    vertex_id = name or "s%s" % dpid
    assert vertex_id not in self._g.vertices,\
      "Switch '%s' is already added" % dpid
    ports = ports if ports else []
    ports = ports if isinstance(ports, list) else [ports]
    assert len(ports) >= num_used_ports

     # set unique port no for each interface
    next_port_no = 0
    for port in ports:
      port_no = port.get('port_no', next_port_no)
      port_no = port_no or next_port_no
      port['port_no'] = port_no
      next_port_no = max(next_port_no, port_no) + 1
      if not port.get('name', None):
        port['name'] = "%s-%s" % (vertex_id, port_no)
      port['vtype'] = VertexType.PORT
      self._g.add_vertex(port['name'], **port)

    attrs['dpid'] = dpid
    attrs['name'] = vertex_id
    attrs['ports'] = ports
    attrs['num_used_ports'] = num_used_ports
    attrs['vtype'] = vtype
    self._g.add_vertex(vertex_id, **attrs)
    return vertex_id

  def add_interface_to_host(self, host_id, hw_addr, ips=None, port_no=None,
                            name=None, **kwargs):
    """
    Helper method to add a Host interface to existing host

    Args:
      host_id: the vertex id of the host (e.g. h1, h2)
      hw_addr: Hardware address (MAC Address) of this interface
      ips: List of IP addresses assigned to this interface
      port_no: numerical unique number (per host) for the interface
      name: Human Readable name for this interface (e.g. h1-eth0)
    """
    assert self._g.has_vertex(host_id)
    host_attrs = self.get_host_info(host_id)
    assert host_attrs.get('vtype', None) == VertexType.HOST
    attrs = kwargs.copy()

    ips = ips or []
    ips = attrs.get('ips', ips)
    ips = ips if isinstance(ips, list) else [ips]
    port_no = attrs.get('port_no', port_no)
    if port_no is None:
      port_no = 1 + max(
        0, 0, *[iface.get('port_no', 0) for iface in host_attrs['interfaces']])
    name = attrs.get('name', name)
    name = name or "%s-eth%s" % (host_id, port_no)
    assert not self._g.has_vertex(name)
    vtype = attrs.get('vtype', VertexType.INTERFACE)
    attrs['hw_addr'] = hw_addr
    attrs['ips'] = ips
    attrs['port_no'] = port_no
    attrs['name'] = name
    attrs['vtype'] = vtype
    host_attrs['interfaces'].append(attrs)
    self._g.add_vertex(name, **attrs)
    return name

  def add_port_to_switch(self, switch_id, hw_addr, port_no=None, name=None,
                         **kwargs):
    assert switch_id in self._g.vertices
    switch_dict = self._g.vertices[switch_id]
    assert switch_dict.get('vtype', None) == VertexType.SWITCH
    if port_no is None:
      port_no = 1 + max(
        0, 0, *[p.get('port_no', 0) for p in switch_dict['ports']])
    name = name or "%s-%s" % (switch_id, port_no)
    assert not self._g.has_vertex(name)
    port_dict = dict(hw_addr=hw_addr, port_no=port_no, name=name,
                     vtype=VertexType.PORT, **kwargs)
    switch_dict['ports'].append(port_dict)
    self._g.add_vertex(name, **port_dict)
    return name

  def add_link(self, src_node, src_port, dst_node, dst_port, **kwargs):
    assert src_node in self._g.vertices
    assert src_port in self._g.vertices
    assert dst_node in self._g.vertices
    assert dst_port in self._g.vertices

    assert self._g.vertices[src_node].get('vtype', None) in\
           [VertexType.HOST, VertexType.SWITCH]
    assert self._g.vertices[src_port].get('vtype', None) in\
           [VertexType.INTERFACE, VertexType.PORT]
    assert self._g.vertices[dst_node].get('vtype', None) in\
           [VertexType.HOST, VertexType.SWITCH]
    assert self._g.vertices[dst_port].get('vtype', None) in\
           [VertexType.INTERFACE, VertexType.PORT]

    if not self._g.has_edge(src_node, src_port):
      self._g.add_edge(src_node, src_port)
    if not self._g.has_edge(dst_node, dst_port):
      self._g.add_edge(dst_node, dst_port)
    kwargs['src_node'] = src_node
    kwargs['dst_node'] = dst_node
    self._g.add_edge(src_port, dst_port, **kwargs)

  def has_link(self, src_node, src_port, dst_node, dst_port):
    return self.get_link(src_node, src_port, dst_node, dst_port) is not None

  def get_link(self, src_node, src_port, dst_node, dst_port):
    src_node_attrs = self._g.vertices.get(src_node, None)
    dst_node_attrs = self._g.vertices.get(dst_node, None)
    # Check if src_node and dst_node exist
    if src_node_attrs is None or dst_node_attrs is None:
      return None
    # Check if src_port is connected to src_node (and same for dst)
    if not self._g.has_edge(src_node, src_port) or \
        not self._g.has_edge(dst_node, dst_port):
      return None
    return self._g.get_edge(src_port, dst_port)

  def get_host_info(self, host_id):
    info = self._g.vertices[host_id]
    assert info.get('vtype', None) == VertexType.HOST
    return info

  def get_switch_info(self, switch_id):
    info = self._g.vertices[switch_id]
    assert info.get('vtype', None) == VertexType.SWITCH
    return info

  def to_json(self):
    json_dict = dict(hosts=[], switches=[], links=[])
    json_dict['__type__'] = object_fullname(self)
    json_dict['hosts'] = list(self.hosts_iter(True))
    json_dict['switches'] = list(self.switches_iter(True))
    json_dict['links'] = list(self.links_iter(True))
    return json_dict

  @classmethod
  def from_json(cls, json_dict):
    assert json_dict.get('__type__') == class_fullname(cls)
    topo = cls()
    for name, value in json_dict['hosts']:
      topo.add_host(**value)
    for name, value in json_dict['switches']:
      topo.add_switch(**value)
    for src_node, src_port, dst_node, dst_port, value in json_dict['links']:
      attrs = value.copy()
      attrs.pop('src_node', None)
      attrs.pop('dst_node', None)
      topo.add_link(src_node, src_port, dst_node, dst_port, **attrs)
    return topo


class PatchPanel(object):
  """
  Patch panel connects the different elements in the network together.

  In this basic model, the patch panel has any-to-any connectivity, but it
  can be extended to support different models. Simply all ports for each
  network element are connected to the patch panel. The patch panel can connect
  any two ports (aka create a link) or disconnect them (bring the link down),
  or migrate hosts (change the switch side of the link).

  Since this is a simple model, this class is merely  a data structure to track
  link status and migrate virtual links, but it can be extended to support
  a real patch panel (OVS or hardware)
  """

  __metaclass__ = abc.ABCMeta

  def __init__(self, link_cls=Link, access_link_cls=AccessLink,
               port_cls=ofp_phy_port, host_interface_cls=HostInterface,
               sts_console=msg):
    super(PatchPanel, self).__init__()
    self.link_cls = link_cls
    self.access_link_cls = access_link_cls
    self.port_cls = port_cls
    self.host_interface_cls = host_interface_cls
    self.msg = sts_console

    self.cut_links = set()
    self.cut_access_links = set()
    self.dpid2switch = {}
    self.port2access_link = {}
    self.interface2access_link = {}
    self.src_port2internal_link = {}
    self.dst_port2internal_link = {}

  @property
  def network_links(self):
    """Return list of internal network links"""
    return list(set(self.src_port2internal_link.values()))

  @property
  def access_links(self):
    """Return list of access links (host->switch)"""
    return self.interface2access_link.values()

  @property
  def live_links(self):
    """Return list of live internal network links"""
    return set(self.network_links) - self.cut_links

  @property
  def live_access_links(self):
    """Return list of live access links"""
    return set(self.access_links) - self.cut_access_links

  @property
  def can_create_host_interfaces(self):
    """
    Return True if the patch panel has the ability to add new interfaces to
    hosts.
    """
    return True

  @property
  def can_create_switch_ports(self):
    """
    Return True if the patch panel has the ability to add new ports to switches.
    """
    return True

  def is_port_connected(self, port):
    """
    Return True if the port is currently connected to anything
    """
    return (port in self.port2access_link or
            port in self.interface2access_link or
            port in self.src_port2internal_link or
            port in self.dst_port2internal_link)

  def is_interface_connected(self, interface):
    """
    Return True if the interface is currently connected to anything
    """
    return interface in self.interface2access_link

  def find_unused_port(self, switch, create_new=True):
    """
    Find a switch's unused port;
    if no such port exists and create_new=True, create a new one
    """
    for _, port in switch.ports.items():
      if not self.is_port_connected(port):
        return port
    if create_new is False:
      return None
    else:
      assert self.can_create_switch_ports
    if len(switch.ports) == 0:
      new_port_number = 1
    else:
      new_port_number = max(
        [port_number for port_number in switch.ports.keys()]) + 1
    new_port = self.port_cls(hw_addr=random_eth_addr(), port_no=new_port_number)
    switch.ports[new_port_number] = new_port
    return new_port

  def find_unused_interface(self, host, create_new=True):
    """
    Find a host's unused interface;
    if no such interface exists and create_new=True, create a new one
    """
    for interface in host.interfaces:
      if not self.is_interface_connected(interface):
        return interface
    if create_new is False:
      return None
    else:
      assert self.can_create_host_interfaces
    if len(host.interfaces) == 0:
      new_port_no = 1
    else:
      new_port_no = max(
        [interface.hw_addr.toInt() for interface in host.interfaces]) + 1
    host_addr = host.hid
    host_addr = host_addr << 32
    new_interface_addr = host_addr | new_port_no
    new_interface_addr = hex(new_interface_addr)[2:].zfill(12)
    new_interface_addr = ":".join(
      new_interface_addr[i:i+2] for i in range(0,len(new_interface_addr), 2))
    new_interface = self.host_interface_cls(new_interface_addr,
                                            name="%s-eth%s" % (host.name,
                                                               new_port_no))
    host.interfaces.append(new_interface)
    return new_interface

  def create_network_link(self, src_switch, src_port, dst_switch, dst_port,
                          create_new_ports=True):
    """
    Create a unidirectional network (internal) link between two switches
    If a port is not provided and create_new_ports=True,
    an unused port in the corresponding switch is used.
    """
    if src_port is None:
      src_port = self.find_unused_port(src_switch, create_new_ports)
    if dst_port is None:
      dst_port = self.find_unused_port(dst_switch, create_new_ports)
    if src_port is None or dst_port is None:
      return None
    link = self.link_cls(src_switch, src_port, dst_switch, dst_port)
    self.add_link(link)
    return link

  def add_link(self, link):
    """Connect whatever necessary to make the link connected."""
    assert isinstance(link, (DirectedLinkAbstractClass, BiDirectionalLinkAbstractClass))
    if isinstance(link, BiDirectionalLinkAbstractClass):
      self.src_port2internal_link[link.port1] = link
      self.src_port2internal_link[link.port2] = link
      self.dst_port2internal_link[link.port1] = link
      self.dst_port2internal_link[link.port2] = link
    elif isinstance(link, DirectedLinkAbstractClass):
      self.src_port2internal_link[link.start_port] = link
      self.dst_port2internal_link[link.end_port] = link
    return link

  def remove_network_link(self, src_switch, src_port, dst_switch, dst_port,
                          remove_all=False):
    """
    Remove a unidirectional network (internal) link(s) between two switches.

    If ports are None and remove all set to True, all links will be removed
    If ports are None and  remove all set to False and there are multiple
    links an exception will be raised.
    """
    links = []
    for port in src_switch.ports.values():
      if port in self.src_port2internal_link.keys():
        link = self.src_port2internal_link[port]
        if isinstance(link, DirectedLinkAbstractClass):
          if link.start_node is src_switch and link.end_node is dst_switch:
            if src_port is not None:
              if link.start_port != src_port and link.start_port.port_no != src_port:
                continue
            if dst_port is not None:
              if link.end_port != dst_port and link.end_port.port_no != dst_port:
                continue
        elif isinstance(link, BiDirectionalLinkAbstractClass):
          if (link.node1 == src_switch and link.node2 == dst_switch) or\
            (link.node2 == src_switch and link.node1 == dst_switch):
            if src_port is not None:
              if link.port1 != src_port and link.port1.port_no != dst_port and\
                  link.port2 != src_port and link.port2.port_no != dst_port :
                continue
        if link not in links:
            links.append(link)
    if len(links) > 1 and remove_all == False:
      raise ValueError("Multiple links connecting '%s'->'%s'" % (src_switch,
                                                                 dst_switch))
    for link in links:
      if isinstance(link, DirectedLinkAbstractClass):
        del self.src_port2internal_link[link.start_port]
        del self.dst_port2internal_link[link.end_port]
      elif isinstance(link, BiDirectionalLinkAbstractClass):
        del self.src_port2internal_link[link.port1]
        del self.src_port2internal_link[link.port2]
        del self.dst_port2internal_link[link.port1]
        del self.dst_port2internal_link[link.port2]

  def remove_access_link(self, host, interface, switch, port, remove_all=False):
    """
    Remove access link(s) between a host and a switch.

    If ports are None and remove all set to True, all links will be removed
    If ports are None and  remove all set to False and there are multiple
    links an exception will be raised.
    """
    links = []
    for iface in host.interfaces:
      if not self.is_interface_connected(iface):
        continue
      link = self.interface2access_link[iface]
      if interface is not None and iface != interface:
        continue
      if port is not None and link.switch_port != port:
        continue
      links.append(link)
    if len(links) > 1 and remove_all == False:
      raise ValueError("Multiple links connecting '%s'->'%s'" % (host,
                                                                 switch))
    for link in links:
      del self.interface2access_link[link.interface]
      del self.port2access_link[link.switch_port]

  def add_access_link(self, link):
    """Connect whatever necessary to make the link connected."""
    self.port2access_link[link.switch_port] = link
    self.interface2access_link[link.interface] = link
    return link

  def create_access_link(self, host, interface, switch, port,
                         create_new_ports=True):
    """
    Create an access link between a host and a switch
    If no interface is provided and create_new_port is False,
      an unused interface is used
    If no interface is provided and create_new_port is True and no free
      interfaces is available, a new one is created
      interfaces is available, a new one is created
    The same goes for switch ports
    """
    if interface is None:
      interface = self.find_unused_interface(host, create_new_ports)
    if port is None:
      port = self.find_unused_port(switch, create_new_ports)
    if interface is None:
      raise ValueError("Cannot find free interface at host '%s'" % host)
    if port is None:
      raise ValueError("Cannot find free port at switch '%s'" % switch)
    link = self.access_link_cls(host, interface, switch, port)
    self.add_access_link(link)
    return link

  @abc.abstractmethod
  def sever_link(self, link):
    """
    Disconnect link
    """
    raise NotImplementedError()

  @abc.abstractmethod
  def repair_link(self, link):
    """Bring a link back online"""
    raise NotImplementedError()

  @abc.abstractmethod
  def sever_access_link(self, link):
    """
    Disconnect host-switch link
    """
    raise NotImplementedError()


  @abc.abstractmethod
  def repair_access_link(self, link):
    """Bring a link back online"""
    raise NotImplementedError()

  def remove_host(self, host):
    """
    Clean up links connected to the host when it's removed
    """
    for interface in host.interfaces:
      if interface in self.interface2access_link:
        link = self.interface2access_link[interface]
        self.remove_access_link(host, interface, link.switch, link.switch_port)

  def get_other_side(self, node, port):
    """
    Given a node and a port, return a tuple (node, port) that is directly
    connected to the port.

    This can be used in 2 ways
    - node is a Host type and port is a HostInterface type
    - node is a Switch type and port is a ofp_phy_port type.
    """
    if port in self.port2access_link:
      access_link = self.port2access_link[port]
      return access_link.host, access_link.interface
    if port in self.interface2access_link:
      access_link = self.interface2access_link[port]
      return access_link.switch, access_link.switch_port
    elif port in self.src_port2internal_link:
      network_link = self.src_port2internal_link[port]
      return network_link.end_software_switch, network_link.end_port
    else:
      raise ValueError("Unknown port %s on node %s" % (str(port),str(node)))


class Topology(object):
  """
  Keeps track of the network elements
  """
  def __init__(self, patch_panel, topo_graph=None, hosts=None, switches=None, controllers=None,
               links=None, host_cls=Host, switch_cls=FuzzSoftwareSwitch,
               link_cls=Link, access_link_cls=AccessLink,
               interface_cls=HostInterface, sts_console=msg):
    super(Topology, self).__init__()
    self.host_cls = host_cls
    self.switch_cls = switch_cls
    self.link_cls = link_cls
    self.access_link_cls = access_link_cls
    self.interface_cls = interface_cls
    self.patch_panel = patch_panel
    self._g = Graph()
    self._topo_graph = topo_graph or TopologyGraph()
    self._dpid2vertex = {}
    self.failed_switches = set()
    self.msg = sts_console
    self.log = logging.getLogger("sts.topology.base.Topology")

    # Some basic checks to deal the topology graph
    self._host_check = lambda v, attrs: isinstance(attrs.get('obj', None), self.host_cls)

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
    True if the switches in the topology can shutdown and reboot switches
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
    edge_switches = set(filter(lambda sw: sw.can_connect_to_endhosts, self.switches))
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
