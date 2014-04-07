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

from sts.topology.base import TopologyGraph
from sts.topology.base import Topology
from sts.topology.base import PatchPanel

from sts.entities.base import BiDirectionalLinkAbstractClass
from sts.entities.hosts import Host
from sts.entities.hosts import HostInterface
from sts.entities.sts_entities import AccessLink
from sts.entities.sts_entities import Link
from sts.entities.sts_entities import FuzzSoftwareSwitch


class MockPatchPanel(PatchPanel):
  """
  Provide simple implementation for the abstract methods in PatchPanel.
  Basically treats it as a data structure.
  """
  def __init__(self, link_cls=Link):
    super(MockPatchPanel, self).__init__(link_cls=Link)

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

  def repair_link(self, link):
    """Bring a link back online"""
    self.msg.event("Restoring link %s" % str(link))
    if link not in self.network_links:
      raise ValueError("Unknown link %s" % str(link))
    self.cut_links.remove(link)

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

  def repair_access_link(self, link):
    """Bring a link back online"""
    self.msg.event("Restoring access link %s" % str(link))
    if link not in self.access_links:
      raise ValueError("Unknown access link %s" % str(link))
    self.cut_access_links.remove(link)



class TopologyTest(unittest.TestCase):
  @unittest.skip
  def test_build(self):
    # Arrange
    if1 = dict(hw_addr='00:00:00:00:00:01', ips='192.168.56.21')
    if2 = dict(hw_addr='00:00:00:00:00:02', ips='192.168.56.22')
    topo = TopologyGraph()
    h1 = topo.add_host(interfaces=[if1, if2], name='h1')
    # Act
    net = Topology(topo_graph=topo, patch_panel=MockPatchPanel())
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
    topo = Topology(patch_panel=MockPatchPanel())
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
    topo = Topology(patch_panel=MockPatchPanel())
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
    topo = Topology(patch_panel=MockPatchPanel())
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
    topo = Topology(patch_panel=MockPatchPanel())
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
    topo = Topology(patch_panel=MockPatchPanel())
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
    topo = Topology(patch_panel=MockPatchPanel(),
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
    topo = Topology(patch_panel=MockPatchPanel())
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
    topo = Topology(patch_panel=MockPatchPanel())
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
      patch_panel=MockPatchPanel(link_cls=BiDirectionalLinkAbstractClass),
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
    topo = Topology(patch_panel=MockPatchPanel())
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
    topo = Topology(patch_panel=MockPatchPanel())
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
    topo = Topology(patch_panel=MockPatchPanel())
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



class PatchPanelTest(unittest.TestCase):
  def test_find_unused_port(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=2)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=0)
    panel = MockPatchPanel()
    # Act
    s1p1 = panel.find_unused_port(s1)
    none_port = panel.find_unused_port(s2, create_new=False)
    s2p1 = panel.find_unused_port(s2, create_new=True)
    # Assert
    self.assertEquals(s1p1.port_no, 1)
    self.assertIsNone(none_port)
    self.assertEquals(s2p1.port_no, 1)

  def test_find_unused_interface(self):
    # Arrange
    h1_eth0 = HostInterface(hw_addr='00:00:00:00:00:01', name='h1-eth0')
    h1 = Host(interfaces=h1_eth0, name='h1')
    h2 = Host(interfaces=None, name='h2', hid=2)
    panel = MockPatchPanel()
    # Act
    h1if0 = panel.find_unused_interface(h1)
    none_iface = panel.find_unused_interface(h2, create_new=False)
    h2if1 = panel.find_unused_interface(h2, create_new=True)
    # Assert
    self.assertEquals(h1if0, h1_eth0)
    self.assertIsNone(none_iface)
    self.assertEquals(h2if1.port_no, '00:02:00:00:00:01')

  def test_add_link(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=1)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=1)
    l1 = Link(s1, s1.ports[1], s2, s2.ports[1])
    panel = MockPatchPanel()
    # Act
    link = panel.add_link(l1)
    # Assert
    self.assertEquals(link, l1)
    self.assertEquals(len(panel.src_port2internal_link), 1)
    self.assertEquals(len(panel.dst_port2internal_link), 1)

  def test_create_network_link(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=1)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=1)
    panel = MockPatchPanel()
    # Act
    l1 = panel.create_network_link(s1, None, s2, None, create_new_ports=False)
    l2 = panel.create_network_link(s1, None, s2, None, create_new_ports=False)
    l3 = panel.create_network_link(s1, None, s2, None, create_new_ports=True)
    # Assert
    self.assertEquals(l1.start_software_switch, s1)
    self.assertEquals(l1.end_software_switch, s2)
    self.assertEquals(l1.start_port, s1.ports.values()[0])
    self.assertEquals(l1.end_port, s2.ports.values()[0])
    self.assertIsNone(l2)
    self.assertEquals(l3.start_software_switch, s1)
    self.assertEquals(l3.end_software_switch, s2)
    self.assertEquals(l3.start_port, s1.ports.values()[1])
    self.assertEquals(l3.end_port, s2.ports.values()[1])

  def test_remove_network_link(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=1)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=1)
    panel = MockPatchPanel()
    l1 = panel.create_network_link(s1, None, s2, None, create_new_ports=False)
    l2 = panel.create_network_link(s1, None, s2, None, create_new_ports=True)
    l3 = panel.create_network_link(s1, None, s2, None, create_new_ports=True)
    l4 = panel.create_network_link(s1, None, s2, None, create_new_ports=True)
    # Act
    self.assertRaises(ValueError, panel.remove_network_link, s1, None, s2,
                      None, remove_all=False)
    panel.remove_network_link(s1, s1.ports[1], s2, s2.ports[1],
                              remove_all=False)
    panel.remove_network_link(s1, 2, s2, 2, remove_all=False)
    panel.remove_network_link(s1, None, s2, None, remove_all=True)
    # Assert
    self.assertEquals(len(panel.src_port2internal_link), 0)

  def test_add_access_link(self):
    # Arrange
    if1 = HostInterface(hw_addr='00:00:00:00:00:01', name='h1-eth0')
    h1 = Host(if1, name='h1', hid=1)
    s1 = FuzzSoftwareSwitch(1, 's1', ports=1)
    l1 = AccessLink(h1, if1, s1, s1.ports.values()[0])
    panel = MockPatchPanel()
    # Act
    link = panel.add_access_link(l1)
    # Assert
    self.assertEquals(link, l1)
    self.assertIn(l1.interface, panel.interface2access_link)
    self.assertIn(l1.switch_port, panel.port2access_link)

  def test_create_access_link(self):
    # Arrange
    if1 = HostInterface(hw_addr='00:00:00:00:00:01', name='h1-eth0')
    h1 = Host(if1, name='h1', hid=1)
    s1 = FuzzSoftwareSwitch(1, 's1', ports=1)
    panel = MockPatchPanel()
    # Act
    l1 = panel.create_access_link(h1, None, s1, None, create_new_ports=False)
    self.assertRaises(ValueError, panel.create_access_link, h1, None, s1, None,
                                  create_new_ports=False)
    l2 = panel.create_access_link(h1, None, s1, None, create_new_ports=True)
    # Assert
    self.assertIn(l1.interface, panel.interface2access_link)
    self.assertIn(l1.switch_port, panel.port2access_link)
    self.assertIn(l2.interface, panel.interface2access_link)
    self.assertIn(l2.switch_port, panel.port2access_link)

  def test_sever_link(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=2)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=2)
    panel = MockPatchPanel()
    l1 = panel.create_network_link(s1, None, s2, None, create_new_ports=False)
    l2 = panel.create_network_link(s1, None, s2, None, create_new_ports=False)
    # Act
    cut_links1 = panel.cut_links.copy()
    panel.sever_link(l1)
    cut_links2 = panel.cut_links.copy()
    panel.sever_link(l2)
    cut_links3 = panel.cut_links.copy()
    # Assert
    self.assertEquals(len(cut_links1), 0)
    self.assertEquals(len(cut_links2), 1)
    self.assertEquals(len(cut_links3), 2)
    self.assertIn(l1, cut_links2)
    self.assertIn(l1, cut_links3)
    self.assertIn(l2, cut_links3)

  def test_repair_link(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=2)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=2)
    panel = MockPatchPanel()
    l1 = panel.create_network_link(s1, None, s2, None, create_new_ports=False)
    l2 = panel.create_network_link(s1, None, s2, None, create_new_ports=False)
    panel.sever_link(l1)
    panel.sever_link(l2)
    # Act
    cut_links1 = panel.cut_links.copy()
    panel.repair_link(l1)
    cut_links2 = panel.cut_links.copy()
    panel.repair_link(l2)
    cut_links3 = panel.cut_links.copy()
    # Assert
    self.assertEquals(len(cut_links1), 2)
    self.assertEquals(len(cut_links2), 1)
    self.assertEquals(len(cut_links3), 0)
    self.assertIn(l2, cut_links2)

  def test_sever_access_link(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=2)
    if1 = HostInterface(hw_addr='00:00:00:00:00:01', name='h1-eth0')
    if2 = HostInterface(hw_addr='00:00:00:00:00:02', name='h1-eth1')
    h1 = Host([if1, if2], name='h1', hid=1)
    panel = MockPatchPanel()
    l1 = panel.create_access_link(h1, if1, s1, None, create_new_ports=False)
    l2 = panel.create_access_link(h1, if2, s1, None, create_new_ports=False)
    # Act
    cut_links1 = panel.cut_access_links.copy()
    panel.sever_access_link(l1)
    cut_links2 = panel.cut_access_links.copy()
    panel.sever_access_link(l2)
    cut_links3 = panel.cut_access_links.copy()
    # Assert
    self.assertEquals(len(cut_links1), 0)
    self.assertEquals(len(cut_links2), 1)
    self.assertEquals(len(cut_links3), 2)
    self.assertIn(l1, cut_links2)
    self.assertIn(l1, cut_links3)
    self.assertIn(l2, cut_links3)

  def test_repair_access_link(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=2)
    if1 = HostInterface(hw_addr='00:00:00:00:00:01', name='h1-eth0')
    if2 = HostInterface(hw_addr='00:00:00:00:00:02', name='h1-eth1')
    h1 = Host([if1, if2], name='h1', hid=1)
    panel = MockPatchPanel()
    l1 = panel.create_access_link(h1, if1, s1, None, create_new_ports=False)
    l2 = panel.create_access_link(h1, if2, s1, None, create_new_ports=False)
    panel.sever_access_link(l1)
    panel.sever_access_link(l2)
    # Act
    cut_links1 = panel.cut_access_links.copy()
    panel.repair_access_link(l1)
    cut_links2 = panel.cut_access_links.copy()
    panel.repair_access_link(l2)
    cut_links3 = panel.cut_access_links.copy()
    # Assert
    self.assertEquals(len(cut_links1), 2)
    self.assertEquals(len(cut_links2), 1)
    self.assertEquals(len(cut_links3), 0)
    self.assertIn(l2, cut_links2)

  def test_remove_access_link(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=2)
    if1 = HostInterface(hw_addr='00:00:00:00:00:01', name='h1-eth0')
    if2 = HostInterface(hw_addr='00:00:00:00:00:02', name='h1-eth1')
    h1 = Host([if1, if2], name='h1', hid=1)
    panel = MockPatchPanel()
    l1 = panel.create_access_link(h1, if1, s1, None, create_new_ports=False)
    l2 = panel.create_access_link(h1, if2, s1, None, create_new_ports=False)
    # Act
    self.assertRaises(ValueError, panel.remove_access_link, l1.host, None,
                      l1.switch, None, remove_all=False)
    panel.remove_access_link(h1, if1, s1, s1.ports.values()[0])
    panel.remove_access_link(h1, if2, s1, s1.ports.values()[1])
    # Assert
    self.assertEquals(len(panel.access_links), 0)

  def test_remove_host(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=2)
    if1 = HostInterface(hw_addr='00:00:00:00:00:01', name='h1-eth0')
    if2 = HostInterface(hw_addr='00:00:00:00:00:02', name='h1-eth1')
    h1 = Host([if1, if2], name='h1', hid=1)
    panel = MockPatchPanel()
    l1 = panel.create_access_link(h1, if1, s1, None, create_new_ports=False)
    l2 = panel.create_access_link(h1, if2, s1, None, create_new_ports=False)
    # Act
    panel.remove_host(h1)
    # Assert
    self.assertEquals(len(panel.access_links), 0)
