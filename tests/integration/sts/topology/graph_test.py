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


import unittest

from pox.openflow.libopenflow_01 import ofp_phy_port

from sts.entities.hosts import Host
from sts.entities.hosts import HostInterface
from sts.entities.sts_entities import AccessLink
from sts.entities.sts_entities import Link
from sts.entities.sts_entities import FuzzSoftwareSwitch

from sts.topology.graph import Graph
from sts.topology.graph import TopologyGraph


class GraphTest(unittest.TestCase):
  """
  Testing sts.topology.base.Graph
  """

  def test_init(self):
    # Arrange
    vertices = {1: None, 2: {'a': 'b'}, 3: None}
    edges = {1: {1: {}, 2: {'a': 'b'}}, 3: {1: None}}
    # Act
    graph1 = Graph()
    graph2 = Graph(vertices, edges)
    # Assert
    self.assertEquals(len(graph1.vertices), 0)
    self.assertEquals(len(graph1.edges), 0)
    self.assertEquals(len(graph2.vertices), len(vertices))
    self.assertEquals(len(graph2.edges), 3)
    self.assertEquals(graph2.vertices[1], {})
    self.assertEquals(graph2.vertices[2], vertices[2])
    self.assertEquals(graph2.vertices[3], {})
    self.assertEquals(graph2.edges[0], (1, 1, {}))
    self.assertEquals(graph2.edges[1], (1, 2, edges[1][2]))
    self.assertEquals(graph2.edges[2], (3, 1, {}))

  def test_add_vertex(self):
    # Arrange
    vertices = {1: None, 2: {'a': 'b'}, 3: None}
    edges = {1: {1: {}, 2: {'a': 'b'}}, 3: {1: None}}
    # Act
    graph = Graph(vertices, edges)
    graph.add_vertex(4, c='d')
    graph.add_vertex(5)
    # Assert
    self.assertEquals(len(graph.vertices), len(vertices) + 2)
    self.assertEquals(len(graph.edges), 3)
    self.assertEquals(graph.vertices[1], {})
    self.assertEquals(graph.vertices[2], vertices[2])
    self.assertEquals(graph.vertices[3], {})
    self.assertEquals(graph.vertices[4], {'c': 'd'})
    self.assertEquals(graph.vertices[5], {})
    self.assertTrue(graph.has_vertex(1))
    self.assertTrue(graph.has_vertex(2))
    self.assertTrue(graph.has_vertex(3))
    self.assertTrue(graph.has_vertex(4))
    self.assertTrue(graph.has_vertex(5))
    self.assertFalse(graph.has_vertex(6))

  def test_has_vertex(self):
    # Arrange
    vertices = {1: None, 2: {'a': 'b'}, 3: None}
    edges = {1: {1: {}, 2: {'a': 'b'}}, 3: {1: None}}
    # Act
    graph = Graph(vertices, edges)
    graph.add_vertex(4, c='d')
    graph.add_vertex(5)
    # Assert
    self.assertTrue(graph.has_vertex(1))
    self.assertTrue(graph.has_vertex(2))
    self.assertTrue(graph.has_vertex(3))
    self.assertTrue(graph.has_vertex(4))
    self.assertTrue(graph.has_vertex(5))
    self.assertFalse(graph.has_vertex(6))

  def test_edges_iter(self):
    # Arrange
    edges = {1: {1: {}, 2: {'a': 'b'}}, 3: {1: {}}}
    graph = Graph(vertices=None, edges=edges)
    # Act
    edges1 = list(graph.edges_iter(include_attrs=False))
    edges2 = list(graph.edges_iter(include_attrs=True))
    # Assert
    for edge in edges1:
      self.assertEquals(len(edge), 2)
      self.assertIn(edge[0], edges)
      self.assertIn(edge[1], edges[edge[0]])
    for edge in edges2:
      self.assertIn(edge[0], edges)
      self.assertIn(edge[1], edges[edge[0]])
      self.assertEquals(edges[edge[0]][edge[1]], edge[2])

  def test_edges_iter_with_check(self):
    # Arrange
    edges = {1: {1: {}, 2: {'a': 'b'}}, 3: {1: {}}}
    graph = Graph(vertices=None, edges=edges)
    check = lambda v1, v2, attrs: attrs.get('a', None) is not None
    # Act
    edges1 = list(graph.edges_iter_with_check(check, include_attrs=False))
    edges2 = list(graph.edges_iter_with_check(check, include_attrs=True))
    # Assert
    self.assertEquals(edges1, [(1, 2)])
    self.assertEquals(edges2, [(1, 2, {'a': 'b'})])

  def test_vertices_iter(self):
    # Arrange
    vertices = {1: None, 2: {'a': 'b'}, 3: None, 4: None, 5: None}
    graph = Graph(vertices)
    # Act
    vertices1 = list(graph.vertices_iter(include_attrs=False))
    vertices2 = list(graph.vertices_iter(include_attrs=True))
    # Assert
    for vertex in vertices1:
      self.assertTrue(vertex in vertices)
    for vertex, value in vertices2:
      value = value if value != {} else None
      self.assertEquals(vertices[vertex], value)

  def test_vertices_iter_with_check(self):
    # Arrange
    vertices = {1: None, 2: {'a': 'b'}, 3: None, 4: None, 5: None}
    graph = Graph(vertices)
    check = lambda v, attrs: attrs.get('a', None) is not None
    # Act
    vertices1 = list(graph.vertices_iter_with_check(check, include_attrs=False))
    vertices2 = list(graph.vertices_iter_with_check(check, include_attrs=True))
    # Assert
    self.assertEquals(vertices1, [2])
    self.assertEquals(vertices2, [(2, vertices[2])])

  def test_add_edge(self):
    # Arrange
    vertices = {1: None, 2: {'a': 'b'}, 3: None}
    edges = {1: {1: {}, 2: {'a': 'b'}}, 3: {1: None}}
    expected = [(1, 1, {}), (1, 1, {}), (1, 2, edges[1][2]), (3, 1, {}),
                (1, 3, {}), (1, 4, {'c': 'd'})]
    # Act
    graph = Graph(vertices, edges)
    graph.add_edge(1, 3)
    graph.add_edge(1, 4, c='d')
    # Assert
    self.assertEquals(len(graph.vertices), len(vertices) + 1)
    self.assertEquals(len(graph.edges), 3 + 2)
    self.assertEquals(graph.vertices[1], {})
    self.assertEquals(graph.vertices[2], vertices[2])
    self.assertEquals(graph.vertices[3], {})
    self.assertEquals(graph.vertices[4], {})
    self.assertTrue(graph.has_edge(1, 2))
    self.assertFalse(graph.has_edge(2, 4))
    self.assertFalse(graph.has_edge(9, 6))
    for edge in expected:
      self.assertTrue(edge in graph.edges)

  def test_remove_edge(self):
    # Arrange
    graph = Graph()
    edge1 = graph.add_edge(1, 2)
    edge2 = graph.add_edge(2, 3)
    edge3 = graph.add_edge(2, 4)
    # Act
    graph.remove_edge(*edge1)
    graph.remove_edge(*edge2)
    # Assert
    self.assertRaises(AssertionError, graph.remove_edge, 10, 20)
    self.assertFalse(graph.has_edge(*edge1))
    self.assertFalse(graph.has_edge(*edge2))
    self.assertTrue(graph.has_edge(*edge3))

  def test_remove_vertex(self):
    # Arrange
    graph = Graph()
    v1, v2, v3, v4, v5, v6, v7 = 1, 2, 3, 4, 5, 6, 7
    graph.add_vertex(v1)
    graph.add_vertex(v2)
    graph.add_vertex(v3)
    graph.add_vertex(v4)
    graph.add_vertex(v5)
    graph.add_vertex(v6)
    graph.add_vertex(v7)
    e1 = graph.add_edge(v1, v2)
    e2 = graph.add_edge(v3, v4)
    e3 = graph.add_edge(v3, v5)
    # Act
    graph.remove_vertex(v1, remove_edges=True)
    graph.remove_vertex(v6, remove_edges=False)
    self.assertRaises(AssertionError, graph.remove_vertex, v3, remove_edges=False)
    graph.remove_vertex(v3, remove_edges=True)
    # Assert
    self.assertFalse(graph.has_vertex(v1))
    self.assertTrue(graph.has_vertex(v2))
    self.assertFalse(graph.has_vertex(v3))
    self.assertTrue(graph.has_vertex(v4))
    self.assertTrue(graph.has_vertex(v5))
    self.assertFalse(graph.has_vertex(v6))
    self.assertTrue(graph.has_vertex(v7))
    self.assertFalse(graph.has_edge(*e1))
    self.assertFalse(graph.has_edge(*e2))
    self.assertFalse(graph.has_edge(*e3))

  def test_edges_src(self):
    # Arrange
    v1, v2, v3, v4 = 1, 2, 3, 4
    g = Graph()
    e1 = g.add_edge(v1, v2)
    e2 = g.add_edge(v2, v3)
    e3 = g.add_edge(v2, v4)
    # Act
    v1_src = g.edges_src(v1)
    v2_src = g.edges_src(v2)
    v3_src = g.edges_src(v3)
    # Assert
    self.assertItemsEqual([e1], v1_src)
    self.assertItemsEqual([e2, e3], v2_src)
    self.assertItemsEqual([], v3_src)

  def test_edges_dst(self):
    # Arrange
    v1, v2, v3, v4 = 1, 2, 3, 4
    g = Graph()
    e1 = g.add_edge(v1, v2)
    e2 = g.add_edge(v1, v3)
    e3 = g.add_edge(v2, v3)
    g.add_vertex(v4)
    # Act
    v1_dst = g.edges_dst(v1)
    v2_dst = g.edges_dst(v2)
    v3_dst = g.edges_dst(v3)
    v4_dst = g.edges_dst(v4)
    # Assert
    self.assertItemsEqual([], v1_dst)
    self.assertItemsEqual([e1], v2_dst)
    self.assertItemsEqual([e2, e3], v3_dst)
    self.assertEquals(v4_dst, [])


class TopologyGraphTest(unittest.TestCase):

  def test_init(self):
    # Arrange
    h1_eth1 = HostInterface(hw_addr='11:22:33:44:55:66', ip_or_ips='10.0.0.1')
    h2_eth1 = HostInterface(hw_addr='11:22:33:44:55:77', ip_or_ips='10.0.0.2')
    h1 = Host(h1_eth1, hid=1)
    h2 = Host(h2_eth1, hid=2)
    hosts = [h1, h2]
    interfaces = [h1_eth1, h2_eth1]
    s1 = FuzzSoftwareSwitch(1, 's1', ports=3)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=3)
    s3 = FuzzSoftwareSwitch(3, 's3', ports=3)
    switches = [s1, s2, s3]
    ports = s1.ports.values() + s2.ports.values() + s3.ports.values()
    l1 = Link(s1, s1.ports[1], s2, s2.ports[1])
    l2 = Link(s1, s1.ports[2], s2, s2.ports[2])
    l3 = AccessLink(h1, h1_eth1, s1, s1.ports[3])
    l4 = AccessLink(h2, h2_eth1, s1, s2.ports[3])
    links = [l1, l2, l3, l4]
    # Act
    graph = TopologyGraph(hosts, switches, links)
    # Assert
    self.assertItemsEqual(hosts, graph.hosts)
    self.assertItemsEqual(switches, graph.switches)
    self.assertItemsEqual(links, graph.links)
    self.assertItemsEqual(interfaces, graph.interfaces)
    self.assertItemsEqual(ports, graph.ports)

  def test_add_host(self):
    # Arrange
    h1_eth1 = HostInterface(hw_addr='11:22:33:44:55:66', ip_or_ips='10.0.0.1')
    h2_eth1 = HostInterface(hw_addr='11:22:33:44:55:77', ip_or_ips='10.0.0.2')
    h1 = Host(h1_eth1, hid=1)
    h2 = Host(h2_eth1, hid=2)
    h3 = Host(None, hid=3)
    graph = TopologyGraph()
    # Act
    graph.add_host(h1)
    graph.add_host(h2)
    # Assert
    self.assertItemsEqual([h1.name, h2.name], list(graph.hosts_iter(False)))
    self.assertTrue(graph.has_host(h1.name))
    self.assertTrue(graph.has_host(h2.name))
    self.assertFalse(graph.has_host(h3.name))

  def test_remove_host(self):
    # Arrange
    h1_eth1 = HostInterface(hw_addr='11:22:33:44:55:66', ip_or_ips='10.0.0.1')
    h2_eth1 = HostInterface(hw_addr='11:22:33:44:55:77', ip_or_ips='10.0.0.2')
    h1 = Host(h1_eth1, hid=1)
    h2 = Host(h2_eth1, hid=2)
    h3 = Host(None, hid=3)
    graph = TopologyGraph()
    graph.add_host(h1)
    graph.add_host(h2)
    # Act
    graph.remove_host(h1.name)
    graph.remove_host(h2.name)
    remove_h3 = lambda: graph.remove_host(h3.name)
    # Assert
    self.assertRaises(AssertionError, remove_h3)
    self.assertFalse(graph.hosts)
    self.assertFalse(graph.has_host(h1.name))
    self.assertFalse(graph.has_host(h2.name))
    self.assertFalse(graph.has_host(h3.name))

  def test_add_switch(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=1)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=1)
    s3 = FuzzSoftwareSwitch(3, 's3', ports=1)
    graph = TopologyGraph()
    # Act
    graph.add_switch(s1)
    graph.add_switch(s2)
    # Assert
    self.assertItemsEqual([s1.name, s2.name], list(graph.switches_iter(False)))
    self.assertTrue(graph.has_switch(s1.name))
    self.assertTrue(graph.has_switch(s2.name))
    self.assertFalse(graph.has_switch(s3.name))

  def test_remove_switch(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=1)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=1)
    s3 = FuzzSoftwareSwitch(3, 's3', ports=1)
    graph = TopologyGraph()
    graph.add_switch(s1)
    graph.add_switch(s2)
    # Act
    graph.remove_switch(s1.name)
    graph.remove_switch(s2)
    remove_s3 = lambda: graph.remove_switch(s3.dpid)
    # Assert
    self.assertRaises(AssertionError, remove_s3)
    self.assertFalse(graph.switches)
    self.assertFalse(graph.has_host(s1.dpid))
    self.assertFalse(graph.has_host(s2.dpid))
    self.assertFalse(graph.has_host(s3.dpid))

  def test_add_link(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=2)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=2)
    l1 = Link(s1, s1.ports[1], s2, s2.ports[1])
    l2 = Link(s1, ofp_phy_port(), s2, s2.ports[2])
    graph = TopologyGraph()
    graph.add_switch(s1)
    graph.add_switch( s2)
    # Act
    link = graph.add_link(l1)
    fail_add = lambda: graph.add_link(l2)
    # Assert
    self.assertEquals(link, l1)
    self.assertTrue(graph.has_link(l1))
    self.assertFalse(graph.has_link(l2))
    self.assertIsNotNone(graph.get_link('s1-1', 's2-1'))
    self.assertIsNone(graph.get_link('s1-2', 's2-2'))
    self.assertRaises(AssertionError, fail_add)

  def test_remove_link(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=4)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=4)
    l1 = Link(s1, s1.ports[1], s2, s2.ports[1])
    l2 = Link(s1, s1.ports[2], s2, s2.ports[2])
    l3 = Link(s1, s1.ports[3], s2, s2.ports[3])
    l4 = Link(s1, s1.ports[4], s2, s2.ports[4])
    graph = TopologyGraph()
    graph.add_switch(s1)
    graph.add_switch(s2)
    graph.add_link(l1)
    graph.add_link(l2, bidir=l2)
    graph.add_link(l3)
    # Act
    graph.remove_link(l1)
    graph.remove_link(l2)
    fail_remove = lambda: graph.remove_link(l4)
    # Assert
    self.assertFalse(graph.has_link(l1))
    self.assertFalse(graph.has_link(l2))
    self.assertTrue(graph.has_link(l3))
    self.assertIsNone(graph.get_link("s1-1", "s2-1"))
    self.assertIsNone(graph.get_link("s1-2", "s2-2"))
    self.assertIsNotNone(graph.get_link("s1-3", "s2-3"))
    self.assertRaises(AssertionError, fail_remove)

  def test_get_host_links(self):
    # Arrange
    h1_eth1 = HostInterface(hw_addr='11:22:33:44:55:66', ip_or_ips='10.0.0.1')
    h1_eth2 = HostInterface(hw_addr='11:22:33:44:55:67', ip_or_ips='10.0.0.2')
    h2_eth1 = HostInterface(hw_addr='11:22:33:44:55:77', ip_or_ips='10.0.0.3')
    h1 = Host([h1_eth1, h1_eth2], hid=1)
    h2 = Host(h2_eth1, hid=2)
    s1 = FuzzSoftwareSwitch(1, 's1', ports=3)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=3)
    l1 = AccessLink(h1, h1_eth1, s1, s1.ports[1])
    l2 = AccessLink(h1, h1_eth2, s2, s2.ports[1])
    l3 = AccessLink(h2, h2_eth1, s2, s2.ports[2])
    l4 = Link(s1, s1.ports[3], s2, s2.ports[2])
    graph = TopologyGraph()
    graph.add_switch(s1)
    graph.add_switch(s2)
    graph.add_host(h1)
    graph.add_host(h2)
    graph.add_link(l1)
    graph.add_link(l2)
    graph.add_link(l3)
    graph.add_link(l4)
    # Act
    h1_links = graph.get_host_links(h1)
    h2_links = graph.get_host_links(h2)
    # Assert
    self.assertItemsEqual([l1, l2], h1_links)
    self.assertItemsEqual([l3], h2_links)

  def test_get_switches_links(self):
    # Arrange
    h1_eth1 = HostInterface(hw_addr='11:22:33:44:55:66', ip_or_ips='10.0.0.1')
    h1_eth2 = HostInterface(hw_addr='11:22:33:44:55:67', ip_or_ips='10.0.0.2')
    h2_eth1 = HostInterface(hw_addr='11:22:33:44:55:77', ip_or_ips='10.0.0.3')
    h1 = Host([h1_eth1, h1_eth2], hid=1)
    h2 = Host(h2_eth1, hid=2)
    s1 = FuzzSoftwareSwitch(1, 's1', ports=3)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=3)
    l1 = AccessLink(h1, h1_eth1, s1, s1.ports[1])
    l2 = AccessLink(h1, h1_eth2, s2, s2.ports[1])
    l3 = AccessLink(h2, h2_eth1, s2, s2.ports[2])
    l4 = Link(s1, s1.ports[3], s2, s2.ports[2])
    graph = TopologyGraph()
    graph.add_switch(s1)
    graph.add_switch(s2)
    graph.add_host(h1)
    graph.add_host(h2)
    graph.add_link(l1)
    graph.add_link(l2)
    graph.add_link(l3)
    graph.add_link(l4)
    # Act
    s1_links = graph.get_switch_links(s1)
    s2_links = graph.get_switch_links(s2)
    # Assert
    self.assertItemsEqual([l1, l4], s1_links)
    self.assertItemsEqual([l2, l3, l4], s2_links)
