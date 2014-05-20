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

import mock
import unittest

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

  def test_add_host(self):
    # Arrange
    if1 = dict(hw_addr='00:00:00:00:00:01', ips='192.168.56.21')
    if2 = dict(hw_addr='00:00:00:00:00:02', ips='192.168.56.22')
    topo = TopologyGraph()
    # Act
    h1 = topo.add_host(interfaces=[if1, if2], name='h1')
    # Assert
    self.assertEquals(h1, 'h1')
    self.assertEquals(len(topo._g.vertices), 3)
    self.assertEquals(list(topo.hosts_iter()), [h1])
    self.assertEquals(list(topo.interfaces_iter()), ['h1-eth0', 'h1-eth1'])
    self.assertEquals(len(topo.get_host_info(h1)['interfaces']), 2)
    self.assertEquals(topo.get_host_info(h1)['name'], h1)

  def test_add_interface_to_host(self):
    # Arrange
    if1_params = dict(hw_addr='00:00:00:00:00:01', ips='192.168.56.21',
                      port_no=10)
    if2_params = dict(hw_addr='00:00:00:00:00:02', ips='192.168.56.22',
                      port_no=11)
    topo = TopologyGraph()
    h1 = topo.add_host(interfaces=None, name='h1', hid='1')
    # Act
    if1 = topo.add_interface_to_host(h1, hw_addr=if1_params['hw_addr'],
                                     ips=if1_params['ips'],
                                     port_no=if1_params['port_no'])
    if2 = topo.add_interface_to_host(h1, hw_addr=if2_params['hw_addr'],
                                     ips=if2_params['ips'])
    # Assert
    self.assertEquals(h1, 'h1')
    self.assertEquals(if1, 'h1-eth10')
    self.assertEquals(if2, 'h1-eth11')
    self.assertEquals(len(topo._g.vertices), 3)
    self.assertEquals(list(topo.hosts_iter()), [h1])
    self.assertEquals(list(topo.interfaces_iter()), ['h1-eth10', 'h1-eth11'])
    self.assertEquals(len(topo.get_host_info(h1)['interfaces']), 2)
    self.assertEquals(topo.get_host_info(h1)['name'], h1)

  def test_add_switch(self):
    # Arrange
    p1 = dict(hw_addr='00:00:00:00:01:01', port_no=1)
    p2 = dict(hw_addr='00:00:00:00:01:02', port_no=2)
    dpid1 = 1
    dpid2 = 2
    sw1_ports = None
    sw2_ports = [p1, p2]
    topo = TopologyGraph()
    # Act
    sw1 = topo.add_switch(dpid=dpid1, ports=sw1_ports)
    sw2 = topo.add_switch(dpid=dpid2, ports=sw2_ports)
    # Assert
    self.assertEquals(len(list(topo.switches_iter())), 2)
    self.assertEquals(list(topo.switches_iter()), [sw1, sw2])
    self.assertEquals(len(list(topo.ports_iter())), 2)
    self.assertEquals(len(topo._g.vertices), 4)
    self.assertItemsEqual(list(topo.ports_iter()), ['s2-1', 's2-2'])
    self.assertEquals(len(topo.get_switch_info(sw1)['ports']), 0)
    self.assertEquals(len(topo.get_switch_info(sw2)['ports']), 2)
    self.assertEquals(topo.get_switch_info(sw1)['name'], sw1)
    self.assertEquals(topo.get_switch_info(sw2)['name'], sw2)

  def test_add_port_to_switch(self):
    # Arrange
    p1_params = dict(hw_addr='00:00:00:00:00:01', port_no=10)
    p2_params = dict(hw_addr='00:00:00:00:00:02')
    sw1_params = dict(dpid=1, ports=None)
    topo = TopologyGraph()
    sw1 = topo.add_switch(**sw1_params)
    # Act
    p1 = topo.add_port_to_switch(sw1, **p1_params)
    p2 = topo.add_port_to_switch(sw1, **p2_params)
    # Assert
    self.assertEquals(sw1, 's1')
    self.assertEquals(p1, 's1-10')
    self.assertEquals(p2, 's1-11')
    self.assertEquals(len(topo._g.vertices), 3)
    self.assertEquals(list(topo.switches_iter()), [sw1])
    self.assertItemsEqual(list(topo.ports_iter()), [p1, p2])
    self.assertEquals(len(topo.get_switch_info(sw1)['ports']), 2)


  def test_add_link(self):
    # Arrange
    if1_params = dict(hw_addr='00:00:00:00:00:01', ips='192.168.56.21')
    p1_params = dict(hw_addr='00:00:00:00:00:02')
    h1_params = dict(interfaces=None, name='h1')
    sw1_params = dict(dpid=1, ports=None)
    topo = TopologyGraph()
    h1 = topo.add_host(**h1_params)
    sw1 = topo.add_switch(**sw1_params)
    if1 = topo.add_interface_to_host(h1, **if1_params)
    p1 = topo.add_port_to_switch(sw1, **p1_params)
    link_parmas = dict(foo='bar')
    expected_link_params = link_parmas.copy()
    expected_link_params['src_node'] = sw1
    expected_link_params['dst_node'] = h1

    # Act
    topo.add_link(sw1, p1, h1, if1, **link_parmas)
    # Assert
    self.assertTrue(topo.has_link(sw1, p1, h1, if1))

    self.assertEquals(topo.get_link(sw1, p1, h1, if1), expected_link_params)

  def test_serialize(self):
    # Arrange
    if1_params = dict(hw_addr='00:00:00:00:00:01', ips='192.168.56.21')
    p1_params = dict(hw_addr='00:00:00:00:00:02')
    h1_params = dict(interfaces=None, name='h1')
    sw1_params = dict(dpid=1, ports=None)
    topo = TopologyGraph()
    h1 = topo.add_host(**h1_params)
    sw1 = topo.add_switch(**sw1_params)
    if1 = topo.add_interface_to_host(h1, **if1_params)
    p1 = topo.add_port_to_switch(sw1, **p1_params)
    link_parmas = dict(foo='bar')
    expected_link_params = link_parmas.copy()
    expected_link_params['src_node'] = sw1
    expected_link_params['dst_node'] = h1
    topo.add_link(sw1, p1, h1, if1, **link_parmas)
    # Act
    json_dict = topo.to_json()
    topo2 = TopologyGraph.from_json(json_dict)
    # Assert
    self.assertEquals(json_dict['__type__'], 'sts.topology.graph.TopologyGraph')
    self.assertItemsEqual(list(topo.switches_iter()),
                          list(topo2.switches_iter()))
    self.assertItemsEqual(list(topo.hosts_iter()), list(topo2.hosts_iter()))
    self.assertItemsEqual(list(topo.links_iter()), list(topo2.links_iter()))
