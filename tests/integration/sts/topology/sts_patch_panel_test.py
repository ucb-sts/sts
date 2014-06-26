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

from sts.entities.hosts import Host
from sts.entities.hosts import HostInterface
from sts.entities.sts_entities import AccessLink
from sts.entities.sts_entities import Link


from sts.topology.sts_patch_panel import STSPatchPanel
from sts.entities.sts_entities import FuzzSoftwareSwitch


class PatchPanelTest(unittest.TestCase):
  def test_create_network_link(self):
    # Arrange
    patch_panel = STSPatchPanel()
    src_switch = FuzzSoftwareSwitch(1, 's1', ports=2)
    dst_switch = FuzzSoftwareSwitch(2, 's2', ports=2)
    # Act
    link = patch_panel.create_network_link(src_switch, src_switch.ports[1],
                                           dst_switch, dst_switch.ports[1])
    # Assert
    self.assertIsInstance(link, Link)
    self.assertEquals(link.start_node, src_switch)
    self.assertEquals(link.start_port, src_switch.ports[1])
    self.assertEquals(link.end_node, dst_switch)
    self.assertEquals(link.end_port, dst_switch.ports[1])

  def test_add_link(self):
    # Arrange
    patch_panel1 = STSPatchPanel()
    src_switch = FuzzSoftwareSwitch(1, 's1', ports=2)
    dst_switch = FuzzSoftwareSwitch(2, 's2', ports=2)
    link = Link(src_switch, src_switch.ports[1], dst_switch,
                dst_switch.ports[1])
    # Act
    patch_panel1.add_network_link(link)
    # Assert
    self.assertItemsEqual(patch_panel1.live_network_links, [link])
    self.assertItemsEqual(patch_panel1.network_links, [link])

  def test_remove_link(self):
    # Arrange
    patch_panel = STSPatchPanel()
    src_switch = FuzzSoftwareSwitch(1, 's1', ports=2)
    dst_switch = FuzzSoftwareSwitch(2, 's2', ports=2)
    link = patch_panel.create_network_link(src_switch, src_switch.ports[1],
                                           dst_switch, dst_switch.ports[1])
    patch_panel.add_network_link(link)
    # Act
    patch_panel.remove_network_link(link)
    # Assert
    self.assertItemsEqual(patch_panel.live_network_links, [])
    self.assertItemsEqual(patch_panel.network_links, [])

  def test_query_network_links(self):
    # Arrange
    patch_panel = STSPatchPanel()

    src_switch1 = FuzzSoftwareSwitch(1, 'src_s1', ports=2)
    src_switch2 = FuzzSoftwareSwitch(2, 'src_s2', ports=2)
    dst_switch1 = FuzzSoftwareSwitch(3, 'dst_s1', ports=2)
    dst_switch2 = FuzzSoftwareSwitch(4, 'dst_s2', ports=2)

    link1 = patch_panel.create_network_link(src_switch1, src_switch1.ports[1],
                                            dst_switch1, dst_switch1.ports[1])
    link2 = patch_panel.create_network_link(src_switch1, src_switch1.ports[2],
                                            dst_switch1, dst_switch1.ports[2])
    link3 = patch_panel.create_network_link(src_switch2, src_switch2.ports[1],
                                            dst_switch2, dst_switch2.ports[1])
    link4 = patch_panel.create_network_link(src_switch2, src_switch2.ports[2],
                                            dst_switch2, dst_switch2.ports[2])
    patch_panel.add_network_link(link1)
    patch_panel.add_network_link(link2)
    patch_panel.add_network_link(link3)
    patch_panel.add_network_link(link4)
    # Act
    # Get exact link
    set1 = patch_panel.query_network_links(src_switch1, src_switch1.ports[1],
                                           dst_switch1, dst_switch1.ports[1])
    set2 = patch_panel.query_network_links(src_switch1, src_switch1.ports[2], dst_switch1,
                                           dst_switch1.ports[2])
    set3 = patch_panel.query_network_links(src_switch2, src_switch2.ports[1], dst_switch2,
                                           dst_switch2.ports[1])
    set4 = patch_panel.query_network_links(src_switch2, src_switch2.ports[2], dst_switch2,
                                           dst_switch2.ports[2])
    # Wildcard one port
    set5 = patch_panel.query_network_links(src_switch1, None, dst_switch1,
                                           dst_switch1.ports[1])
    set6 = patch_panel.query_network_links(src_switch1, src_switch1.ports[1],
                                           dst_switch1, None)
    set7 = patch_panel.query_network_links(src_switch2, None, dst_switch2,
                                           dst_switch2.ports[1])
    set8 = patch_panel.query_network_links(src_switch2, src_switch2.ports[1], dst_switch2,
                                           None)
    # Wildcard two ports
    set9 = patch_panel.query_network_links(src_switch1, None, dst_switch1, None)
    set10 = patch_panel.query_network_links(src_switch2, None, dst_switch2,
                                            None)

    # Assert
    self.assertItemsEqual([link1], set1)
    self.assertItemsEqual([link2], set2)
    self.assertItemsEqual([link3], set3)
    self.assertItemsEqual([link4], set4)
    self.assertItemsEqual([link1], set5)
    self.assertItemsEqual([link1], set6)
    self.assertItemsEqual([link3], set7)
    self.assertItemsEqual([link3], set8)
    self.assertItemsEqual([link1, link2], set9)
    self.assertItemsEqual([link3, link4], set10)

  def test_is_port_connected(self):
    # Arrange
    # Arrange
    patch_panel = STSPatchPanel()

    src_switch1 = FuzzSoftwareSwitch(1, 'src_s1', ports=2)
    src_switch2 = FuzzSoftwareSwitch(2, 'src_s2', ports=2)
    dst_switch1 = FuzzSoftwareSwitch(3, 'dst_s1', ports=2)
    dst_switch2 = FuzzSoftwareSwitch(4, 'dst_s2', ports=2)

    link1 = patch_panel.create_network_link(src_switch1, src_switch1.ports[1],
                                            dst_switch1, dst_switch1.ports[1])
    link2 = patch_panel.create_network_link(src_switch1, src_switch1.ports[2],
                                            dst_switch1, dst_switch1.ports[2])
    link3 = patch_panel.create_network_link(src_switch2, src_switch2.ports[1],
                                            dst_switch2, dst_switch2.ports[1])

    patch_panel.add_network_link(link1)
    patch_panel.add_network_link(link2)
    # Act
    is_connected_src_port1 = patch_panel.is_port_connected(src_switch1.ports[1])
    is_connected_dst_port1 = patch_panel.is_port_connected(dst_switch1.ports[1])
    is_connected_src_port2 = patch_panel.is_port_connected(src_switch1.ports[2])
    is_connected_dst_port2 = patch_panel.is_port_connected(dst_switch1.ports[2])
    is_connected_src_port3 = patch_panel.is_port_connected(src_switch2.ports[1])
    is_connected_dst_port3 = patch_panel.is_port_connected(dst_switch2.ports[1])
    is_connected_src_port4 = patch_panel.is_port_connected(src_switch2.ports[2])
    is_connected_dst_port4 = patch_panel.is_port_connected(dst_switch2.ports[2])
    # Assert
    self.assertTrue(is_connected_src_port1)
    self.assertTrue(is_connected_dst_port1)
    self.assertTrue(is_connected_src_port2)
    self.assertTrue(is_connected_dst_port2)
    self.assertFalse(is_connected_src_port3)
    self.assertFalse(is_connected_dst_port3)
    self.assertFalse(is_connected_src_port4)
    self.assertFalse(is_connected_dst_port4)

  def test_create_access_link(self):
    # Arrange
    patch_panel = STSPatchPanel()
    switch = FuzzSoftwareSwitch(1, 's1', 2)
    eth0 = HostInterface(hw_addr='00:00:00:00:00:01', ip_or_ips='10.0.0.1',
                         name='eth0')
    eth1 = HostInterface(hw_addr='00:00:00:00:00:02', ip_or_ips='10.0.0.2',
                         name='eth1')
    host = Host(interfaces=[eth0, eth1], name='h1', hid=1)
    # Act
    access_link = patch_panel.create_access_link(host, eth0, switch,
                                                 switch.ports[1])
    # Assert
    self.assertIsInstance(access_link, AccessLink)
    self.assertEquals(access_link.host, host)
    self.assertEquals(access_link.interface, eth0)
    self.assertEquals(access_link.switch, switch)
    self.assertEquals(access_link.switch_port, switch.ports[1])

  def test_add_access_link(self):
    # Arrange
    patch_panel = STSPatchPanel()
    switch = FuzzSoftwareSwitch(1, 's1', 2)
    eth0 = HostInterface(hw_addr='00:00:00:00:00:01', ip_or_ips='10.0.0.1',
                         name='eth0')
    eth1 = HostInterface(hw_addr='00:00:00:00:00:02', ip_or_ips='10.0.0.2',
                         name='eth1')
    host = Host(interfaces=[eth0, eth1], name='h1', hid=1)
    access_link = patch_panel.create_access_link(host, eth0, switch,
                                                 switch.ports[1])
    # Act
    patch_panel.add_access_link(access_link)
    # Assert
    self.assertIn(access_link, patch_panel.access_links)
    self.assertIn(access_link, patch_panel.live_access_links)

  def test_is_interface_connected(self):
    # Arrange
    patch_panel = STSPatchPanel()

    switch = FuzzSoftwareSwitch(1, 's1', 2)
    eth0 = HostInterface(hw_addr='00:00:00:00:00:01', ip_or_ips='10.0.0.1',
                         name='eth0')
    eth1 = HostInterface(hw_addr='00:00:00:00:00:02', ip_or_ips='10.0.0.2',
                         name='eth1')
    host = Host(interfaces=[eth0, eth1], name='h1', hid=1)
    access_link = patch_panel.create_access_link(host, eth0, switch,
                                                 switch.ports[1])

    patch_panel.add_access_link(access_link)
    # Act
    is_eth0_connected = patch_panel.is_interface_connected(eth0)
    is_eth1_connected = patch_panel.is_interface_connected(eth1)
    # Assert
    self.assertTrue(is_eth0_connected)
    self.assertFalse(is_eth1_connected)

  def test_remove_access_link(self):
    # Arrange
    patch_panel = STSPatchPanel()
    switch = FuzzSoftwareSwitch(1, 's1', 2)
    eth0 = HostInterface(hw_addr='00:00:00:00:00:01', ip_or_ips='10.0.0.1',
                         name='eth0')
    eth1 = HostInterface(hw_addr='00:00:00:00:00:02', ip_or_ips='10.0.0.2',
                         name='eth1')
    host = Host(interfaces=[eth0, eth1], name='h1', hid=1)
    access_link = patch_panel.create_access_link(host, eth0, switch,
                                                 switch.ports[1])

    patch_panel.add_access_link(access_link)
    # Act
    patch_panel.remove_access_link(access_link)
    # Assert
    self.assertItemsEqual(patch_panel.live_access_links, [])
    self.assertItemsEqual(patch_panel.access_links, [])

  def test_query_access_links(self):
    # Arrange
    patch_panel = STSPatchPanel()

    switch1 = FuzzSoftwareSwitch(1, 's1', 2)
    port1, port2 = switch1.ports[1], switch1.ports[2]

    switch2 = FuzzSoftwareSwitch(2, 's2', 2)
    port3, port4 = switch2.ports[1], switch2.ports[2]

    eth0 = HostInterface(hw_addr='00:00:00:00:00:01', ip_or_ips='10.0.0.1',
                         name='eth0')
    eth1 = HostInterface(hw_addr='00:00:00:00:00:02', ip_or_ips='10.0.0.2',
                         name='eth1')
    host1 = Host(interfaces=[eth0, eth1], name='h1', hid=1)

    eth2 = HostInterface(hw_addr='00:00:00:00:00:03', ip_or_ips='10.0.0.3',
                         name='eth2')
    eth3 = HostInterface(hw_addr='00:00:00:00:00:04', ip_or_ips='10.0.0.4',
                         name='eth3')
    host2 = Host(interfaces=[eth2, eth3], name='h2', hid=2)

    link1 = patch_panel.create_access_link(host1, eth0, switch1, port1)
    link2 = patch_panel.create_access_link(host1, eth1, switch1, port2)
    link3 = patch_panel.create_access_link(host2, eth2, switch2, port3)
    link4 = patch_panel.create_access_link(host2, eth3, switch2, port4)

    patch_panel.add_access_link(link1)
    patch_panel.add_access_link(link2)
    patch_panel.add_access_link(link3)
    patch_panel.add_access_link(link4)
    # Act
    # Get exact link
    set1 = patch_panel.query_access_links(host1, eth0, switch1, port1)
    set2 = patch_panel.query_access_links(host1, eth1, switch1, port2)
    set3 = patch_panel.query_access_links(host2, eth2, switch2, port3)
    set4 = patch_panel.query_access_links(host2, eth3, switch2, port4)
    # Wildcard one port
    set5 = patch_panel.query_access_links(host1, eth0, switch1, None)
    set6 = patch_panel.query_access_links(host1, None, switch1, port1)
    set7 = patch_panel.query_access_links(host2, eth2, switch2, None)
    set8 = patch_panel.query_access_links(host2, None, switch2, port3)
    # Wildcard two ports
    set9 = patch_panel.query_access_links(host1, None, switch1, None)
    set10 = patch_panel.query_access_links(host2, None, switch2, None)
    # Assert
    self.assertItemsEqual([link1], set1)
    self.assertItemsEqual([link2], set2)
    self.assertItemsEqual([link3], set3)
    self.assertItemsEqual([link4], set4)
    self.assertItemsEqual([link1], set5)
    self.assertItemsEqual([link1], set6)
    self.assertItemsEqual([link3], set7)
    self.assertItemsEqual([link3], set8)
    self.assertItemsEqual([link1, link2], set9)
    self.assertItemsEqual([link3, link4], set10)

  def test_get_other_side(self):
    # Arrange
    patch_panel = STSPatchPanel()

    switch1 = FuzzSoftwareSwitch(1, 's1', 2)
    port1, port2 = switch1.ports[1], switch1.ports[2]

    switch2 = FuzzSoftwareSwitch(2, 's2', 2)
    port3, port4 = switch2.ports[1], switch2.ports[2]

    eth0 = HostInterface(hw_addr='00:00:00:00:00:01', ip_or_ips='10.0.0.1',
                         name='eth0')
    eth1 = HostInterface(hw_addr='00:00:00:00:00:02', ip_or_ips='10.0.0.2',
                         name='eth1')
    host1 = Host(interfaces=[eth0, eth1], name='h1', hid=1)

    link1 = patch_panel.create_access_link(host1, eth0, switch1, port1)
    link2 = patch_panel.create_network_link(switch1, port2, switch2, port3)
    patch_panel.add_access_link(link1)
    patch_panel.add_network_link(link2)
    # Act
    n1, p1 = patch_panel.get_other_side(host1, eth0)
    n2, p2 = patch_panel.get_other_side(switch1, port1)
    n3, p3 = patch_panel.get_other_side(switch1, port2)
    n4, p4 = patch_panel.get_other_side(switch2, port3)

    fail_get1 = lambda: patch_panel.get_other_side(host1, eth1)
    fail_get2 = lambda: patch_panel.get_other_side(switch2, port4)

    # Assert
    self.assertEquals((n1, p1), (switch1, port1))
    self.assertEquals((n2, p2), (host1, eth0))
    self.assertEquals((n3, p3), (switch2, port3))
    self.assertEquals((n4, p4), (switch1, port2))
    self.assertRaises(ValueError, fail_get1)
    self.assertRaises(ValueError, fail_get2)

  def test_sever_network_link(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=4)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=4)
    panel = STSPatchPanel()
    l1 = panel.create_network_link(s1, s1.ports[1], s2, s2.ports[1])
    l2 = panel.create_network_link(s1, s1.ports[2], s2, s2.ports[2])
    l3 = panel.create_network_link(s1, s1.ports[3], s2, s2.ports[3])
    l4 = panel.create_network_link(s1, s1.ports[4], s2, s2.ports[4])
    panel.add_network_link(l1)
    panel.add_network_link(l2)
    panel.add_network_link(l3)
    # Act
    cut_links1 = panel.cut_network_links.copy()
    panel.sever_network_link(l1)
    cut_links2 = panel.cut_network_links.copy()
    panel.sever_network_link(l2)
    cut_links3 = panel.cut_network_links.copy()
    fail1 = lambda: panel.sever_network_link(l4)
    panel.sever_network_link(l3)
    fail2 = lambda: panel.sever_network_link(l3)
    # Assert
    self.assertEquals(len(cut_links1), 0)
    self.assertEquals(len(cut_links2), 1)
    self.assertEquals(len(cut_links3), 2)
    self.assertIn(l1, cut_links2)
    self.assertIn(l1, cut_links3)
    self.assertIn(l2, cut_links3)
    self.assertRaises(ValueError, fail1)
    self.assertRaises(RuntimeError, fail2)


  def test_repair_network_link(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=4)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=4)
    panel = STSPatchPanel()
    l1 = panel.create_network_link(s1, s1.ports[1], s2, s2.ports[1])
    l2 = panel.create_network_link(s1, s1.ports[2], s2, s2.ports[2])
    l3 = panel.create_network_link(s1, s1.ports[3], s2, s2.ports[3])
    l4 = panel.create_network_link(s1, s1.ports[4], s2, s2.ports[4])
    panel.add_network_link(l1)
    panel.add_network_link(l2)
    panel.add_network_link(l3)
    panel.sever_network_link(l1)
    panel.sever_network_link(l2)
    # Act
    cut_links1 = panel.cut_network_links.copy()
    panel.repair_network_link(l1)
    cut_links2 = panel.cut_network_links.copy()
    panel.repair_network_link(l2)
    cut_links3 = panel.cut_network_links.copy()
    fail1 = lambda: panel.repair_network_link(l4)
    fail2 = lambda: panel.repair_network_link(l3)
    # Assert
    self.assertEquals(len(cut_links1), 2)
    self.assertEquals(len(cut_links2), 1)
    self.assertEquals(len(cut_links3), 0)
    self.assertIn(l2, cut_links2)
    self.assertRaises(ValueError, fail1)
    self.assertRaises(RuntimeError, fail2)

  def test_sever_access_link(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=4)
    if1 = HostInterface(hw_addr='00:00:00:00:00:01', name='h1-eth0')
    if2 = HostInterface(hw_addr='00:00:00:00:00:02', name='h1-eth1')
    if3 = HostInterface(hw_addr='00:00:00:00:00:03', name='h1-eth2')
    if4 = HostInterface(hw_addr='00:00:00:00:00:04', name='h1-eth3')
    h1 = Host([if1, if2, if3, if4], name='h1', hid=1)
    panel = STSPatchPanel()
    l1 = panel.create_access_link(h1, if1, s1, s1.ports[1])
    l2 = panel.create_access_link(h1, if2, s1, s1.ports[2])
    l3 = panel.create_access_link(h1, if3, s1, s1.ports[3])
    l4 = panel.create_access_link(h1, if4, s1, s1.ports[4])
    panel.add_access_link(l1)
    panel.add_access_link(l2)
    panel.add_access_link(l3)
    # Act
    cut_links1 = panel.cut_access_links.copy()
    panel.sever_access_link(l1)
    cut_links2 = panel.cut_access_links.copy()
    panel.sever_access_link(l2)
    cut_links3 = panel.cut_access_links.copy()
    fail1 = lambda: panel.sever_access_link(l4)
    panel.sever_access_link(l3)
    fail2 = lambda: panel.sever_access_link(l3)
    # Assert
    self.assertEquals(len(cut_links1), 0)
    self.assertEquals(len(cut_links2), 1)
    self.assertEquals(len(cut_links3), 2)
    self.assertIn(l1, cut_links2)
    self.assertIn(l1, cut_links3)
    self.assertIn(l2, cut_links3)
    self.assertRaises(ValueError, fail1)
    self.assertRaises(RuntimeError, fail2)

  def test_repair_access_link(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=4)
    if1 = HostInterface(hw_addr='00:00:00:00:00:01', name='h1-eth0')
    if2 = HostInterface(hw_addr='00:00:00:00:00:02', name='h1-eth1')
    if3 = HostInterface(hw_addr='00:00:00:00:00:03', name='h1-eth2')
    if4 = HostInterface(hw_addr='00:00:00:00:00:04', name='h1-eth3')
    h1 = Host([if1, if2, if3, if4], name='h1', hid=1)
    panel = STSPatchPanel()
    l1 = panel.create_access_link(h1, if1, s1, s1.ports[1])
    l2 = panel.create_access_link(h1, if2, s1, s1.ports[2])
    l3 = panel.create_access_link(h1, if3, s1, s1.ports[3])
    l4 = panel.create_access_link(h1, if4, s1, s1.ports[4])
    panel.add_access_link(l1)
    panel.add_access_link(l2)
    panel.add_access_link(l3)
    panel.sever_access_link(l1)
    panel.sever_access_link(l2)
    # Act
    cut_links1 = panel.cut_access_links.copy()
    panel.repair_access_link(l1)
    cut_links2 = panel.cut_access_links.copy()
    panel.repair_access_link(l2)
    cut_links3 = panel.cut_access_links.copy()
    fail1 = lambda: panel.repair_access_link(l4)
    fail2 = lambda: panel.repair_access_link(l3)
    # Assert
    self.assertEquals(len(cut_links1), 2)
    self.assertEquals(len(cut_links2), 1)
    self.assertEquals(len(cut_links3), 0)
    self.assertIn(l2, cut_links2)
    self.assertRaises(ValueError, fail1)
    self.assertRaises(RuntimeError, fail2)
