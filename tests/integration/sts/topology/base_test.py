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

from sts.topology.graph import TopologyGraph
from sts.topology.base import Topology

from sts.entities.hosts import Host
from sts.entities.hosts import HostInterface
from sts.entities.sts_entities import AccessLink
from sts.entities.sts_entities import Link
from sts.entities.base import BiDirectionalLinkAbstractClass
from sts.entities.sts_entities import FuzzSoftwareSwitch

from tests.integration.sts.topology.patch_panel_test import TestPatchPanel

class TopologyTest(unittest.TestCase):
  @unittest.skip
  def test_build(self):
    # Arrange
    if1 = dict(hw_addr='00:00:00:00:00:01', ips='192.168.56.21')
    if2 = dict(hw_addr='00:00:00:00:00:02', ips='192.168.56.22')
    topo = TopologyGraph()
    h1 = topo.add_host(interfaces=[if1, if2], name='h1')
    # Act
    net = Topology(topo_graph=topo, patch_panel=TestPatchPanel())
    net.build()
    # Assert
    self.assertEquals(h1, 'h1')
    self.assertEquals(len(topo._g.vertices), 3)
    self.assertEquals(list(topo.hosts_iter()), [h1])
    self.assertEquals(list(topo.interfaces_iter()), ['h1-eth0', 'h1-eth1'])
    self.assertEquals(len(topo.get_host_info(h1)['interfaces']), 2)
    self.assertEquals(topo.get_host_info(h1)['name'], h1)

  def test_add_host(self):
    # Arrange
    h1_eth1 = HostInterface(hw_addr='11:22:33:44:55:66', ip_or_ips='10.0.0.1')
    h2_eth1 = HostInterface(hw_addr='11:22:33:44:55:77', ip_or_ips='10.0.0.2')
    h1 = Host(h1_eth1, hid=1)
    h2 = Host(h2_eth1, hid=2)
    # Act
    topo = Topology(patch_panel=TestPatchPanel())
    topo.add_host(h1)
    topo.add_host(h2)
    duplicate_add = lambda: topo.add_host(h1)
    wrong_type = lambda: topo.add_host("Dummy")
    topo._can_add_hosts = False
    immutable_add = lambda: topo.add_host(h1)
    # Assert
    self.assertEquals(len(list(topo.hosts_iter())), 2)
    self.assertRaises(AssertionError, duplicate_add)
    self.assertRaises(AssertionError, wrong_type)
    self.assertRaises(AssertionError, immutable_add)
    self.assertEquals(len(list(topo.hosts_iter())), 2)
    self.assertTrue(topo.has_host(h1))
    self.assertTrue(topo.has_host(h2))
    self.assertTrue(topo.has_host(h1.name))

  def test_remove_host(self):
    # Arrange
    h1_eth1 = HostInterface(hw_addr='11:22:33:44:55:66', ip_or_ips='10.0.0.1')
    h2_eth1 = HostInterface(hw_addr='11:22:33:44:55:77', ip_or_ips='10.0.0.2')
    h1 = Host(h1_eth1, hid=1)
    h2 = Host(h2_eth1, hid=2)
    topo = Topology(patch_panel=TestPatchPanel())
    topo.add_host(h1)
    topo.add_host(h2)
    # Act
    topo.remove_host(h1)
    # Assert
    self.assertFalse(topo.has_host(h1))
    self.assertTrue(topo.has_host(h2))

  @unittest.skip
  def test_add_switch(self):
    # Arrange
    s1 = mock.Mock() # Making a switch is kinda hard now
    s1.dpid = 1
    s2 = mock.Mock() # Making a switch is kinda hard now
    s2.dpid = 2
    # Act
    topo = Topology(patch_panel=TestPatchPanel())
    topo.add_switch(s1)
    topo.add_switch(s2)
    duplicate_add = lambda: topo.add_switch(s1)
    wrong_type = lambda: topo.add_switch("Dummy")
    topo._can_add_hosts = False
    immutable_add = lambda: topo.add_switch(s1)
    # Assert
    self.assertEquals(len(list(topo.switches_iter())), 2)
    self.assertRaises(AssertionError, duplicate_add)
    self.assertRaises(AssertionError, wrong_type)
    self.assertRaises(AssertionError, immutable_add)
    self.assertEquals(len(list(topo.switches_iter())), 2)
    self.assertTrue(topo.has_switch(s1))
    self.assertTrue(topo.has_switch(s2))
    self.assertFalse(topo.has_switch('s3'))

  def test_remove_switch(self):
    # Arrange
    s1 = mock.Mock() # Making a switch is kinda hard now
    s1.dpid = 1
    s1.name = 's1'
    s1.ports.values.return_value = []
    s2 = mock.Mock() # Making a switch is kinda hard now
    s2.dpid = 2
    s2.name = 's2'
    s2.ports.values.return_value = []
    topo = Topology(patch_panel=TestPatchPanel())
    topo.add_switch(s1)
    topo.add_switch(s2)
    # Act
    topo.remove_switch(s1)
    # Assert
    self.assertFalse(topo.has_switch(s1))
    self.assertTrue(topo.has_switch(s2))

  def test_add_link(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=1)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=1)
    l1 = Link(s1, s1.ports[1], s2, s2.ports[1])
    topo = Topology(patch_panel=TestPatchPanel())
    topo.add_switch(s1)
    topo.add_switch(s2)
    # Act
    link = topo.add_link(l1)
    # Assert
    self.assertEquals(link, l1)
    self.assertTrue(topo.has_link(link))

  def test_add_bidir_link(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=1)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=1)
    l1 = BiDirectionalLinkAbstractClass(s1, s1.ports[1], s2, s2.ports[1])
    topo = Topology(patch_panel=TestPatchPanel(),
                    link_cls=BiDirectionalLinkAbstractClass)
    topo.add_switch(s1)
    topo.add_switch(s2)
    # Act
    link = topo.add_link(l1)
    # Assert
    self.assertEquals(link, l1)
    self.assertTrue(topo.has_link(link))

  def test_remove_access_link(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=3)
    h1_eth1 = HostInterface(hw_addr='11:22:33:44:55:66', ip_or_ips='10.0.0.1')
    h1_eth2 = HostInterface(hw_addr='11:22:33:44:55:77', ip_or_ips='10.0.0.2')
    h1_eth3 = HostInterface(hw_addr='11:22:33:44:55:88', ip_or_ips='10.0.0.3')
    h1 = Host([h1_eth1, h1_eth2, h1_eth3], name='h1', hid=1)
    topo = Topology(patch_panel=TestPatchPanel())
    topo.add_switch(s1)
    topo.add_host(h1)
    l1 = AccessLink(h1, h1_eth1, s1, s1.ports[1])
    l2 = AccessLink(h1, h1_eth2, s1, s1.ports[2])
    l3 = AccessLink(h1, h1_eth3, s1, s1.ports[3])
    topo.add_link(l1)
    topo.add_link(l2)
    topo.add_link(l3)
    # Act
    self.assertRaises(ValueError, topo.remove_access_link, h1, None, s1, None,
                      remove_all=False)
    topo.remove_access_link(h1, h1_eth1, s1, None, remove_all=False)
    topo.remove_access_link(h1, h1_eth2, s1, s1.ports[2], remove_all=False)
    self.assertRaises(AssertionError, topo.remove_access_link, h1, h1_eth1, s1,
                      None, remove_all=False)
    # Assert
    self.assertFalse(topo.has_link(l1))
    self.assertFalse(topo.has_link(l2))
    self.assertTrue(topo.has_link(l3))

  def test_remove_network_link(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=3)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=3)
    l1 = Link(s1, s1.ports[1], s2, s2.ports[1])
    l2 = Link(s1, s1.ports[2], s2, s2.ports[2])
    l3 = Link(s1, s1.ports[3], s2, s2.ports[3])
    topo = Topology(patch_panel=TestPatchPanel())
    topo.add_switch(s1)
    topo.add_switch(s2)
    topo.add_link(l1)
    topo.add_link(l2)
    topo.add_link(l3)
    # Act
    self.assertRaises(ValueError, topo.remove_network_link, s1, None, s2, None,
                      remove_all=False)
    topo.remove_network_link(s1, s1.ports[1], s2, s2.ports[1], remove_all=False)
    topo.remove_network_link(s1, s1.ports[2], s2, None, remove_all=False)
    self.assertRaises(AssertionError, topo.remove_network_link, s1, s1.ports[2],
                      s2, None, remove_all=False)
    # Assert
    self.assertFalse(topo.has_link(l1))
    self.assertFalse(topo.has_link(l2))
    self.assertTrue(topo.has_link(l3))

  def test_remove_bidir_network_link(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=3)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=3)
    l1 = BiDirectionalLinkAbstractClass(s1, s1.ports[1], s2, s2.ports[1])
    l2 = BiDirectionalLinkAbstractClass(s1, s1.ports[2], s2, s2.ports[2])
    l3 = BiDirectionalLinkAbstractClass(s1, s1.ports[3], s2, s2.ports[3])
    topo = Topology(
      patch_panel=TestPatchPanel(link_cls=BiDirectionalLinkAbstractClass),
      link_cls=BiDirectionalLinkAbstractClass)
    topo.add_switch(s1)
    topo.add_switch(s2)
    topo.add_link(l1)
    topo.add_link(l2)
    topo.add_link(l3)
    # Act
    self.assertRaises(ValueError, topo.remove_network_link, s1, None, s2, None,
                      remove_all=False)
    topo.remove_network_link(s1, s1.ports[1], s2, s2.ports[1], remove_all=False)
    topo.remove_network_link(s1, s1.ports[2], s2, None, remove_all=False)
    self.assertRaises(AssertionError, topo.remove_network_link, s1, s1.ports[2],
                      s2, None, remove_all=False)
    # Assert
    self.assertFalse(topo.has_link(l1))
    self.assertFalse(topo.has_link(l2))
    self.assertTrue(topo.has_link(l3))

  def test_crash_switch(self):
    # Arrange
    topo = Topology(patch_panel=TestPatchPanel())
    s1 = FuzzSoftwareSwitch(1, 's1', ports=0)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=0)
    topo.add_switch(s1)
    topo.add_switch(s2)
    # Act
    topo.crash_switch(s1)
    # Assert
    self.assertEquals(len(topo.failed_switches), 1)
    self.assertIn(s1, topo.failed_switches)
    self.assertEquals(topo.live_switches, set([s2]))

  def test_recover_switch(self):
    # Arrange
    topo = Topology(patch_panel=TestPatchPanel())
    s1 = FuzzSoftwareSwitch(1, 's1', ports=0)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=0)
    topo.add_switch(s1)
    topo.add_switch(s2)
    topo.crash_switch(s1)
    topo.crash_switch(s2)
    s1.recover = lambda down_controller_ids: True
    # Act
    topo.recover_switch(s1)
    # Assert
    self.assertEquals(len(topo.failed_switches), 1)
    self.assertIn(s2, topo.failed_switches)
    self.assertEquals(topo.live_switches, set([s1]))

  def test_live_edge_switches(self):
    topo = Topology(patch_panel=TestPatchPanel())
    s1 = FuzzSoftwareSwitch(1, 's1', ports=0)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=0)
    topo.add_switch(s1)
    topo.add_switch(s2)
    topo.crash_switch(s1)
    # Act
    live_edge = topo.live_edge_switches
    # Assert
    self.assertEquals(len(topo.failed_switches), 1)
    self.assertIn(s1, topo.failed_switches)
    self.assertEquals(topo.live_switches, set([s2]))
    self.assertItemsEqual(live_edge, [s2])
