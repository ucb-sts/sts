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

from sts.topology.patch_panel import PatchPanelBK
from sts.topology.patch_panel import PatchPanelCapabilities

from tests.unit.sts.util.capability_test import Capabilities


class PatchPanelCapabilitiesTest(Capabilities):
  def setUp(self):
    self._capabilities_cls = PatchPanelCapabilities


network_link_factory = mock.Mock(name='NetworkLinkFactory',
                                 side_effect=lambda x, y, z, w: (x, y, z, w))
access_link_factory = mock.Mock(name='AccessLinkFactory',
                                 side_effect=lambda x, y, z, w: (x, y, z, w))

class TestPatchPanel(PatchPanelBK):
  """
  Provide simple implementation for the abstract methods in PatchPanel.
  Basically treats it as a data structure.
  """

  def __init__(self, capabilities=PatchPanelCapabilities()):
    super(TestPatchPanel, self).__init__(
      network_link_factory=network_link_factory,
      access_link_factory=access_link_factory, capabilities=capabilities)

  def sever_network_link(self, link):
    """
    Disconnect link
    """
    if link not in self.network_links:
      raise ValueError("unknown link %s" % str(link))
    if link in self.cut_network_links:
      raise RuntimeError("link %s already cut!" % str(link))
    self._cut_network_links.add(link)

  def repair_network_link(self, link):
    """Bring a link back online"""
    if link not in self.network_links:
      raise ValueError("Unknown link %s" % str(link))
    self._cut_network_links.remove(link)

  def sever_access_link(self, link):
    """
    Disconnect host-switch link
    """
    if link not in self.access_links:
      raise ValueError("unknown access link %s" % str(link))
    if link in self.cut_access_links:
      raise RuntimeError("Access link %s already cut!" % str(link))
    self.cut_access_links.add(link)

  def repair_access_link(self, link):
    """Bring a link back online"""
    if link not in self.access_links:
      raise ValueError("Unknown access link %s" % str(link))
    self.cut_access_links.remove(link)


class PatchPanelTest(unittest.TestCase):
  def test_create_network_link(self):
    # Arrange
    patch_panel = TestPatchPanel()
    patch_panel2 = TestPatchPanel(
      capabilities=PatchPanelCapabilities(can_create_network_link=False))
    patch_panel.network_link_factory = mock.Mock(
      side_effect=lambda x, y, z, w: (x, y, z, w))
    src_switch, src_port = mock.Mock(), mock.Mock()
    dst_switch, dst_port = mock.Mock(), mock.Mock()
    # Act
    link = patch_panel.create_network_link(src_switch, src_port,
                                           dst_switch, dst_port)
    fail_create = lambda: patch_panel2.create_network_link(src_switch, src_port,
                                                           dst_switch, dst_port)
    # Assert
    self.assertEquals(link, (src_switch, src_port, dst_switch, dst_port))
    self.assertRaises(AssertionError, fail_create)

  def test_add_network_link(self):
    # Arrange
    patch_panel1 = TestPatchPanel()
    patch_panel2 = TestPatchPanel(
      capabilities=PatchPanelCapabilities(can_add_network_link=False))
    src_switch, src_port = mock.Mock(), mock.Mock()
    dst_switch, dst_port = mock.Mock(), mock.Mock()
    link = mock.Mock()
    link.start_node = src_switch
    link.start_port = src_port
    link.dst_switch = dst_switch
    link.end_port = dst_port
    patch_panel1.is_network_link = lambda x: x == link
    patch_panel1.is_bidir_network_link = lambda x: False
    # Act
    patch_panel1.add_network_link(link)
    fail_add = lambda: patch_panel2.add_network_link(link)
    # Assert
    self.assertItemsEqual(patch_panel1.live_network_links, [link])
    self.assertItemsEqual(patch_panel1.network_links, [link])
    self.assertRaises(AssertionError, fail_add)

  def test_remove_network_link(self):
    # Arrange
    patch_panel1 = TestPatchPanel()
    patch_panel2 = TestPatchPanel(
      capabilities=PatchPanelCapabilities(can_remove_network_link=False))
    src_switch = mock.Mock(name='s1')
    src_port1, src_port2 = mock.Mock(name='p1'), mock.Mock(name='p2')
    dst_switch = mock.Mock(name='s1')
    dst_port1, dst_port2 = mock.Mock(name='p2'), mock.Mock(name='p3')

    link1 = mock.Mock(name='link1')
    link1.start_node = src_switch
    link1.start_port = src_port1
    link1.end_node = dst_switch
    link1.end_port = dst_port1
    link2 = mock.Mock(name='link2')
    link1.node1 = src_switch
    link1.port1 = src_port2
    link1.node2 = dst_switch
    link1.port2 = dst_port2
    patch_panel1.is_network_link = lambda x: x in [link1, link2]
    patch_panel2.is_network_link = lambda x: x in [link1, link2]
    patch_panel1.is_bidir_network_link = lambda x: x in [link2]
    patch_panel2.is_bidir_network_link = lambda x: x in [link2]
    patch_panel1.add_network_link(link1)
    patch_panel1.add_network_link(link2)
    patch_panel2.add_network_link(link2)
    # Act

    patch_panel1.remove_network_link(link1)
    patch_panel1.remove_network_link(link2)
    fail_add = lambda: patch_panel2.remove_network_link(link1)
    # Assert
    self.assertItemsEqual(patch_panel1.live_network_links, [])
    self.assertItemsEqual(patch_panel1.network_links, [])
    self.assertRaises(AssertionError, fail_add)

  def test_query_network_links(self):
    # Arrange
    patch_panel = TestPatchPanel()

    src_switch1 = mock.Mock(name='src_s1')
    src_port1, src_port2 = mock.Mock(name='src_p1'), mock.Mock(name='src_p2')

    src_switch2 = mock.Mock(name='src_s2')
    src_port3, src_port4 = mock.Mock(name='src_p3'), mock.Mock(name='src_p4')

    dst_switch1 = mock.Mock(name='dst_s1')
    dst_port1, dst_port2 = mock.Mock(name='dst_p1'), mock.Mock(name='dst_p2')

    dst_switch2 = mock.Mock(name='dst_s2')
    dst_port3, dst_port4 = mock.Mock(name='dst_p3'), mock.Mock(name='dst_p4')

    src_switch1.ports = {1: src_port1, 2: src_port2}
    src_switch2.ports = {1: src_port3, 2: src_port4}
    dst_switch1.ports = {1: dst_port1, 2: dst_port2}
    dst_switch2.ports = {1: dst_port3, 2: dst_port4}

    link1 = mock.Mock(name='link1')
    link1.start_node = src_switch1
    link1.start_port = src_port1
    link1.end_node = dst_switch1
    link1.end_port = dst_port1

    link2 = mock.Mock(name='link2')
    link2.start_node = src_switch1
    link2.start_port = src_port2
    link2.end_node = dst_switch1
    link2.end_port = dst_port2

    link3 = mock.Mock(name='link3')
    link3.node1 = src_switch2
    link3.port1 = src_port3
    link3.node2 = dst_switch2
    link3.port2 = dst_port3

    link4 = mock.Mock(name='link4')
    link4.node1 = src_switch2
    link4.port1 = src_port4
    link4.node2 = dst_switch2
    link4.port2 = dst_port4

    patch_panel.is_network_link = lambda x: x in [link1, link2, link3, link4]
    patch_panel.is_bidir_network_link = lambda x: x in [link3, link4]
    patch_panel.add_network_link(link1)
    patch_panel.add_network_link(link2)
    patch_panel.add_network_link(link3)
    patch_panel.add_network_link(link4)
    # Act
    # Get exact link
    set1 = patch_panel.query_network_links(src_switch1, src_port1, dst_switch1,
                                           dst_port1)
    set2 = patch_panel.query_network_links(src_switch1, src_port2, dst_switch1,
                                           dst_port2)
    set3 = patch_panel.query_network_links(src_switch2, src_port3, dst_switch2,
                                           dst_port3)
    set4 = patch_panel.query_network_links(src_switch2, src_port4, dst_switch2,
                                           dst_port4)
    # Wildcard one port
    set5 = patch_panel.query_network_links(src_switch1, None, dst_switch1,
                                           dst_port1)
    set6 = patch_panel.query_network_links(src_switch1, src_port1, dst_switch1,
                                           None)
    set7 = patch_panel.query_network_links(src_switch2, None, dst_switch2,
                                           dst_port3)
    set8 = patch_panel.query_network_links(src_switch2, src_port3, dst_switch2,
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
    patch_panel = TestPatchPanel()
    src_switch1, src_port1 = mock.Mock(name='src_s1'), mock.Mock(name='src_p1')
    dst_switch1, dst_port1 = mock.Mock(name='dst_s1'), mock.Mock(name='dst_p1')
    src_switch1, src_port2 = mock.Mock(name='src_s2'), mock.Mock(name='src_p2')
    dst_switch1, dst_port2 = mock.Mock(name='dst_s2'), mock.Mock(name='dst_p2')

    src_switch1.ports = {1: src_port1, 2: dst_port1, 3: src_port2, 4: dst_port2}

    link1 = mock.Mock(name='link1')
    link1.start_node = src_switch1
    link1.start_port = src_port1
    link1.end_node = dst_switch1
    link1.end_port = dst_port1

    link2 = mock.Mock(name='link2')
    link2.start_node = src_switch1
    link2.start_port = src_port2
    link2.end_node = dst_switch1
    link2.end_port = dst_port2
    patch_panel.is_network_link = lambda x: True
    patch_panel.is_bidir_network_link = lambda x: False
    patch_panel.add_network_link(link1)
    # Act
    is_connected_src_port1 = patch_panel.is_port_connected(src_port1)
    is_connected_dst_port1 = patch_panel.is_port_connected(dst_port1)
    is_connected_src_port2 = patch_panel.is_port_connected(src_port2)
    is_connected_dst_port2 = patch_panel.is_port_connected(dst_port2)
    # Assert
    self.assertTrue(is_connected_src_port1)
    self.assertTrue(is_connected_dst_port1)
    self.assertFalse(is_connected_src_port2)
    self.assertFalse(is_connected_dst_port2)

  def test_find_unused_port(self):
    # Arrange
    patch_panel = TestPatchPanel()
    src_switch1, src_port1 = mock.Mock(name='src_s1'), mock.Mock(name='src_p1')
    dst_switch1, dst_port1 = mock.Mock(name='dst_s1'), mock.Mock(name='dst_p1')
    src_switch1, src_port2 = mock.Mock(name='src_s2'), mock.Mock(name='src_p2')
    dst_switch1, dst_port2 = mock.Mock(name='dst_s2'), mock.Mock(name='dst_p2')

    src_switch1.ports = {1: src_port1, 2: dst_port1, 3: src_port2, 4: dst_port2}

    link1 = mock.Mock(name='link1')
    link1.start_node = src_switch1
    link1.start_port = src_port1
    link1.end_node = dst_switch1
    link1.end_port = dst_port1

    link2 = mock.Mock(name='link2')
    link2.start_node = src_switch1
    link2.start_port = src_port2
    link2.end_node = dst_switch1
    link2.end_port = dst_port2
    patch_panel.is_network_link = lambda x: True
    patch_panel.is_bidir_network_link = lambda x: False
    # Act
    unused_port1 = patch_panel.find_unused_port(src_switch1)
    patch_panel.add_network_link(link1)
    unused_port2 = patch_panel.find_unused_port(src_switch1)
    # Assert
    self.assertEquals(src_port1, unused_port1)
    self.assertEquals(src_port2, unused_port2)

  def test_create_access_link(self):
    # Arrange
    patch_panel1 = TestPatchPanel()
    patch_panel2 = TestPatchPanel(
      capabilities=PatchPanelCapabilities(can_create_access_link=False))
    switch = mock.Mock(name='s1')
    port1, port2 = mock.Mock(name='p1'), mock.Mock(name='p2')
    host = mock.Mock(name='h1')
    eth0, eth1 =  mock.Mock(name='eth0'),  mock.Mock(name='eth1')
    switch.ports = {1: port1, 2: port2}
    host.interfaces = [eth0, eth1]
    patch_panel1.access_link_factory = mock.Mock(
      side_effect=lambda x, y, z, w: (x, y, z, w))
    # Act
    access_link = patch_panel1.create_access_link(host, eth0, switch, port1)
    fail_create = lambda: patch_panel2.create_access_link(host, eth1,
                                                          switch, port1)
    # Assert
    self.assertEquals(access_link, (host, eth0, switch, port1))
    self.assertRaises(AssertionError, fail_create)

  def test_add_access_link(self):
    # Arrange
    patch_panel1 = TestPatchPanel()
    patch_panel2 = TestPatchPanel(
      capabilities=PatchPanelCapabilities(can_add_access_link=False))
    switch = mock.Mock(name='s1')
    port1, port2 = mock.Mock(name='p1'), mock.Mock(name='p2')
    host = mock.Mock(name='h1')
    eth0, eth1 = mock.Mock(name='eth0'), mock.Mock(name='eth1')
    switch.ports = {1: port1, 2: port2}
    host.interfaces = [eth0, eth1]

    link = mock.Mock(name='AccessLinkMock')
    link.switch = switch
    link.switch_port = port1
    link.host = host
    link.interface = eth0

    patch_panel1.is_access_link = lambda x: x == link
    # Act
    patch_panel1.add_access_link(link)
    fail_add = lambda: patch_panel2.add_access_link(link)
    # Assert
    self.assertItemsEqual(patch_panel1.live_access_links, [link])
    self.assertItemsEqual(patch_panel1.access_links, [link])
    self.assertRaises(AssertionError, fail_add)

  def test_is_interface_connected(self):
    # Arrange
    patch_panel1 = TestPatchPanel()

    switch = mock.Mock(name='s1')
    port1, port2 = mock.Mock(name='p1'), mock.Mock(name='p2')
    host = mock.Mock(name='h1')
    eth0, eth1 = mock.Mock(name='eth0'), mock.Mock(name='eth1')

    switch.ports = {1: port1, 2: port2}
    host.interfaces = [eth0, eth1]

    link1 = mock.Mock(name='AccessLinkMock')
    link1.switch = switch
    link1.port = port1
    link1.host = host
    link1.interface = eth0

    patch_panel1.is_access_link = lambda x: x in [link1]
    patch_panel1.add_access_link(link1)
    # Act
    is_eth0_connected = patch_panel1.is_interface_connected(eth0)
    is_eth1_connected = patch_panel1.is_interface_connected(eth1)
    # Assert
    self.assertTrue(is_eth0_connected)
    self.assertFalse(is_eth1_connected)

  def test_find_unused_interface(self):
    # Arrange
    patch_panel1 = TestPatchPanel()

    switch = mock.Mock(name='s1')
    port1, port2 = mock.Mock(name='p1'), mock.Mock(name='p2')
    host = mock.Mock(name='h1')
    eth0, eth1 = mock.Mock(name='eth0'), mock.Mock(name='eth1')

    switch.ports = {1: port1, 2: port2}
    host.interfaces = [eth0, eth1]

    link1 = mock.Mock(name='AccessLinkMock')
    link1.switch = switch
    link1.port = port1
    link1.host = host
    link1.interface = eth0
    patch_panel1.is_access_link = lambda x: x in [link1]
    # Act
    unused_iface1 = patch_panel1.find_unused_interface(host)
    patch_panel1.add_access_link(link1)
    unused_iface2 = patch_panel1.find_unused_interface(host)
    # Assert
    self.assertEquals(unused_iface1, eth0)
    self.assertEquals(unused_iface2, eth1)

  def test_remove_access_link(self):
    # Arrange
    patch_panel1 = TestPatchPanel()
    patch_panel2 = TestPatchPanel(
      capabilities=PatchPanelCapabilities(can_add_access_link=False))
    switch = mock.Mock(name='s1')
    port1, port2 = mock.Mock(name='p1'), mock.Mock(name='p2')
    host = mock.Mock(name='h1')
    eth0, eth1 = mock.Mock(name='eth0'), mock.Mock(name='eth1')
    switch.ports = {1: port1, 2: port2}
    host.interfaces = [eth0, eth1]

    link = mock.Mock(name='AccessLinkMock')
    link.switch = switch
    link.switch_port = port1
    link.host = host
    link.interface = eth0

    patch_panel1.is_access_link = lambda x: x == link
    patch_panel1.add_access_link(link)
    # Act
    patch_panel1.remove_access_link(link)
    fail_remove = lambda: patch_panel2.remove_access_link(link)
    # Assert
    self.assertItemsEqual(patch_panel1.live_access_links, [])
    self.assertItemsEqual(patch_panel1.access_links, [])
    self.assertRaises(AssertionError, fail_remove)

  def test_query_access_links(self):
    # Arrange
    patch_panel = TestPatchPanel()

    switch1 = mock.Mock(name='s1')
    port1, port2 = mock.Mock(name='p1'), mock.Mock(name='p2')

    switch2 = mock.Mock(name='s2')
    port3, port4 = mock.Mock(name='p3'), mock.Mock(name='p4')

    host1 = mock.Mock(name='h1')
    eth0, eth1 = mock.Mock(name='eth0'), mock.Mock(name='eth1')

    host2 = mock.Mock(name='h2')
    eth2, eth3 = mock.Mock(name='eth2'), mock.Mock(name='eth3')

    switch1.ports = {1: port1, 2: port2}
    switch2.ports = {1: port3, 2: port4}
    host1.interfaces = [eth0, eth1]
    host2.interfaces = [eth2, eth3]

    link1 = mock.Mock(name='link1')
    link1.switch = switch1
    link1.switch_port = port1
    link1.host = host1
    link1.interface = eth0

    link2 = mock.Mock(name='link2')
    link2.switch = switch1
    link2.switch_port = port2
    link2.host = host1
    link2.interface = eth1

    link3 = mock.Mock(name='link3')
    link3.switch = switch2
    link3.switch_port = port3
    link3.host = host2
    link3.interface = eth2

    link4 = mock.Mock(name='link4')
    link4.switch = switch2
    link4.switch_port = port4
    link4.host = host2
    link4.interface = eth3

    patch_panel.is_access_link = lambda x: x in [link1, link2, link3, link4]
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
    patch_panel = TestPatchPanel()

    switch1 = mock.Mock(name='s1')
    port1, port2 = mock.Mock(name='p1'), mock.Mock(name='p2')

    switch2 = mock.Mock(name='s2')
    port3, port4 = mock.Mock(name='p3'), mock.Mock(name='p4')

    host1 = mock.Mock(name='h1')
    eth0, eth1 = mock.Mock(name='eth0'), mock.Mock(name='eth1')

    switch1.ports = {1: port1, 2: port2}
    switch2.ports = {1: port3, 2: port4}
    host1.interfaces = [eth0, eth1]

    link1 = mock.Mock(name='Accesslink1')
    link1.switch = switch1
    link1.switch_port = port1
    link1.host = host1
    link1.interface = eth0

    link2 = mock.Mock(name='link2')
    link2.start_node = switch1
    link2.start_port = port2
    link2.end_node = switch2
    link2.end_port = port3

    patch_panel.is_access_link = lambda x: x in [link1]
    patch_panel.is_network_link = lambda x: x in [link2]
    patch_panel.is_bidir_network_link = lambda x: False
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

  def test_up_network_links(self):
    # Arrange
    patch_panel1 = TestPatchPanel()
    patch_panel2 = TestPatchPanel(
      capabilities=PatchPanelCapabilities(can_get_up_network_links=False))

    src_switch1 = mock.Mock(name='src_s1')
    src_port1, src_port2 = mock.Mock(name='src_p1'), mock.Mock(name='src_p2')

    dst_switch1 = mock.Mock(name='dst_s1')
    dst_port1, dst_port2 = mock.Mock(name='dst_p1'), mock.Mock(name='dst_p2')


    src_switch1.ports = {1: src_port1, 2: src_port2}
    dst_switch1.ports = {1: dst_port1, 2: dst_port2}

    link1 = mock.Mock(name='link1')
    link1.start_node = src_switch1
    link1.start_port = src_port1
    link1.end_node = dst_switch1
    link1.end_port = dst_port1

    link2 = mock.Mock(name='link2')
    link2.start_node = src_switch1
    link2.start_port = src_port2
    link2.end_node = dst_switch1
    link2.end_port = dst_port2
    patch_panel1.is_network_link = lambda x: x in [link1, link2]
    patch_panel1.is_bidir_network_link = lambda x: False
    patch_panel2.is_network_link = lambda x: x in [link1, link2]
    patch_panel2.is_bidir_network_link = lambda x: False
    patch_panel1.add_network_link(link1)
    patch_panel1.add_network_link(link2)
    patch_panel2.add_network_link(link1)
    patch_panel2.add_network_link(link2)
    # Act
    up_links1 = patch_panel1.up_network_links
    patch_panel1.sever_network_link(link1)
    up_links2 = patch_panel1.up_network_links
    fail_get = lambda:patch_panel2.up_network_links
    # Assert
    self.assertItemsEqual([link1, link2], up_links1)
    self.assertItemsEqual([link2], up_links2)
    self.assertRaises(AssertionError, fail_get)

  def test_down_network_links(self):
    # Arrange
    patch_panel1 = TestPatchPanel()
    patch_panel2 = TestPatchPanel(
      capabilities=PatchPanelCapabilities(can_get_down_network_links=False))

    src_switch1 = mock.Mock(name='src_s1')
    src_port1, src_port2 = mock.Mock(name='src_p1'), mock.Mock(name='src_p2')

    dst_switch1 = mock.Mock(name='dst_s1')
    dst_port1, dst_port2 = mock.Mock(name='dst_p1'), mock.Mock(name='dst_p2')


    src_switch1.ports = {1: src_port1, 2: src_port2}
    dst_switch1.ports = {1: dst_port1, 2: dst_port2}

    link1 = mock.Mock(name='link1')
    link1.start_node = src_switch1
    link1.start_port = src_port1
    link1.end_node = dst_switch1
    link1.end_port = dst_port1

    link2 = mock.Mock(name='link2')
    link2.start_node = src_switch1
    link2.start_port = src_port2
    link2.end_node = dst_switch1
    link2.end_port = dst_port2
    patch_panel1.is_network_link = lambda x: x in [link1, link2]
    patch_panel1.is_bidir_network_link = lambda x: False
    patch_panel2.is_network_link = lambda x: x in [link1, link2]
    patch_panel2.is_bidir_network_link = lambda x: False
    patch_panel1.add_network_link(link1)
    patch_panel1.add_network_link(link2)
    patch_panel2.add_network_link(link1)
    patch_panel2.add_network_link(link2)
    # Act
    down_links1 = patch_panel1.down_network_links
    patch_panel1.sever_network_link(link1)
    down_links2 = patch_panel1.down_network_links
    fail_get = lambda:patch_panel2.down_network_links
    # Assert
    self.assertItemsEqual([link1, link2], down_links1)
    self.assertItemsEqual([link2], down_links2)
    self.assertRaises(AssertionError, fail_get)

  def test_up_access_links(self):
    # Arrange
    patch_panel1 = TestPatchPanel()
    patch_panel2 = TestPatchPanel(
      capabilities=PatchPanelCapabilities(can_get_up_access_links=False))

    switch1 = mock.Mock(name='s1')
    port1, port2 = mock.Mock(name='p1'), mock.Mock(name='p2')

    host1 = mock.Mock(name='h1')
    eth0, eth1 = mock.Mock(name='eth0'), mock.Mock(name='eth1')

    switch1.ports = {1: port1, 2: port2}
    host1.interfaces = [eth0, eth1]

    link1 = mock.Mock(name='link1')
    link1.switch = switch1
    link1.port = port1
    link1.host = host1
    link1.interface = eth0

    link2 = mock.Mock(name='link2')
    link2.switch = switch1
    link2.port = port2
    link2.host = host1
    link2.interface = eth1

    patch_panel1.is_access_link = lambda x: x in [link1, link2]
    patch_panel1.add_access_link(link1)
    patch_panel1.add_access_link(link2)

    # Act
    up_links1 = patch_panel1.up_access_links
    patch_panel1.sever_access_link(link1)
    up_links2 = patch_panel1.up_access_links
    fail_get = lambda:patch_panel2.up_access_links
    # Assert
    self.assertItemsEqual([link1, link2], up_links1)
    self.assertItemsEqual([link2], up_links2)
    self.assertRaises(AssertionError, fail_get)

  def test_down_access_links(self):
    # Arrange
    patch_panel1 = TestPatchPanel()
    patch_panel2 = TestPatchPanel(
      capabilities=PatchPanelCapabilities(can_get_down_access_links=False))

    switch1 = mock.Mock(name='s1')
    port1, port2 = mock.Mock(name='p1'), mock.Mock(name='p2')

    host1 = mock.Mock(name='h1')
    eth0, eth1 = mock.Mock(name='eth0'), mock.Mock(name='eth1')

    switch1.ports = {1: port1, 2: port2}
    host1.interfaces = [eth0, eth1]

    link1 = mock.Mock(name='link1')
    link1.switch = switch1
    link1.port = port1
    link1.host = host1
    link1.interface = eth0

    link2 = mock.Mock(name='link2')
    link2.switch = switch1
    link2.port = port2
    link2.host = host1
    link2.interface = eth1

    patch_panel1.is_access_link = lambda x: x in [link1, link2]
    patch_panel1.add_access_link(link1)
    patch_panel1.add_access_link(link2)

    # Act
    down_links1 = patch_panel1.down_access_links
    patch_panel1.sever_access_link(link1)
    down_links2 = patch_panel1.down_access_links
    fail_get = lambda:patch_panel2.down_access_links
    # Assert
    self.assertItemsEqual([link1, link2], down_links1)
    self.assertItemsEqual([link2], down_links2)
    self.assertRaises(AssertionError, fail_get)
