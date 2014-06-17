# Copyright 2014 Ahmed El-Hassany
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
A Simple Library for topology graphs.
"""


from itertools import count

from sts.util.convenience import class_fullname
from sts.util.convenience import object_fullname


class Graph(object):
  """
  A generic graph representation
  """

  def __init__(self, vertices=None, edges=None):
    """
    Args:
      vertices: dict of vertex_id->attrs
      edges: adjacency matrix
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

  This graph considers ports and host interfaces as vertices with bidirectional
  edges to the switch/host. To tell if the edge is a link or a switch-port
  or host-interface association see `is_link`.
  """

  _host_hids = count(1) # host id counter
  _dpids = count(1) # dpid counter


  def __init__(self, hosts=None, switches=None, links=None):
    super(TopologyGraph, self).__init__()
    self._g = Graph()
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

  def is_host(self, vertex, attrs):
    """Returns True if the vertex is a host."""
    return attrs.get('vtype', None) == VertexType.HOST

  def is_interface(self, vertex, attrs):
    """Returns True if the vertex is an interface."""
    return attrs.get('vtype', None) == VertexType.INTERFACE

  def is_switch(self, vertex, attrs):
    """Returns True if the vertex is a switch."""
    return attrs.get('vtype', None) == VertexType.SWITCH

  def is_port(self, vertex, attrs):
    """Returns True if the vertex is a port for a switch."""
    return attrs.get('vtype', None) == VertexType.PORT

  def is_link(self, vertex1, vertex2, attrs):
    """Check if it's an actual network (or access) link.

    This check is distinguish the network links from the virtual port-switch
    or host-interface edges.
    """
    src_node = attrs.get('src_node', None)
    dst_node = attrs.get('dst_node', None)
    return src_node is not None and dst_node is not None

  def hosts_iter(self, include_attrs=False):
    """
    Iterates over hosts in the topology.

    Args:
      include_attr: If true not only host is returned but the attributes as well
    """
    return self._g.vertices_iter_with_check(check=self.is_host,
                                            include_attrs=include_attrs)

  @property
  def hosts(self):
    """List of hosts (objects not just IDs) in the topology"""
    hosts = [host for _, host in self.hosts_iter(True)]
    return hosts

  def interfaces_iter(self, include_attrs=False):
    """
    Iterates over host interfaces in the topology.

    Args:
      include_attr: If true not only interfaces are returned but the attributes
                    as well
    """
    return self._g.vertices_iter_with_check(check=self.is_interface,
                                            include_attrs=include_attrs)

  def ports_iter(self, include_attrs=False):
    """
    Iterates over switch ports in the topology.

    Args:
      include_attr: If true not only ports are returned but the attributes
                    as well
    """
    return self._g.vertices_iter_with_check(check=self.is_port,
                                            include_attrs=include_attrs)

  def switches_iter(self, include_attrs=False):
    """
    Iterates over switches in the topology.

    Args:
      include_attr: If true not only switches are returned but the attributes
                    as well
    """
    return self._g.vertices_iter_with_check(check=self.is_switch,
                                            include_attrs=include_attrs)

  @property
  def switches(self):
    """List of Switches (objects not just IDs) in the topology"""
    switches = [switch for _, switch in self.switches_iter(True)]
    return switches

  def links_iter(self, include_attrs=False):
    """
    Iterates over links in the topology.

    Args:
      include_attr: If true not only links are returned but the attributes
                    as well
    """
    for src_port, dst_port, value in self.edges_iter(include_attrs=True):
      if not self.is_link(src_port, dst_port, value):
        continue
      src_node = value.get('src_node', None)
      dst_node = value.get('dst_node', None)
      if include_attrs:
        yield src_node, src_port, dst_node, dst_port, value
      else:
        yield src_node, src_port, dst_node, dst_port

  def edges_iter(self, include_attrs=False):
    """
    Iterates over all edges in the topology (including the artificial
    host->interface and switch-port).

    Args:
      include_attr: If true not only edges are returned but the attributes
                    as well
    """
    return self._g.edges_iter(include_attrs=include_attrs)

  def add_host(self, interfaces=None, name=None, hid=None,
               num_used_interfaces=None, **kwargs):
    """
    Adds Host to the topology.

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
