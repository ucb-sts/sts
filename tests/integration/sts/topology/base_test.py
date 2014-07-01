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


import inspect
import functools
import unittest

from sts.topology.graph import TopologyGraph
from sts.topology.base import Topology, TopologyPolicy

from sts.entities.hosts import Host
from sts.entities.hosts import HostInterface
from sts.entities.sts_entities import AccessLink
from sts.entities.sts_entities import Link
from sts.entities.base import BiDirectionalLinkAbstractClass
from sts.entities.sts_entities import FuzzSoftwareSwitch


from pox.openflow.libopenflow_01 import ofp_phy_port
from sts.topology.sts_hosts_manager import STSHostsManager
from sts.topology.sts_switches_manager import STSSwitchesManager
from sts.topology.sts_patch_panel import STSPatchPanel

from sts.topology.hosts_manager import mac_addresses_generator
from sts.topology.hosts_manager import ip_addresses_generator
from sts.topology.hosts_manager import interface_names_generator



def sts_topology_type_factory(is_host=None, is_switch=None,
                              is_network_link=None, is_access_link=None,
                              is_host_interface=None, is_port=None):
  """
  Fills in the parameters needed for default behavior as STS topology.
  Returns Topology class init with some of the fields already filled in.
  """
  is_host_lambda = lambda x: isinstance(x, Host)
  is_switch_lambda = lambda x: hasattr(x, 'dpid')
  is_network_link_lambda =lambda x: isinstance(x, Link)
  is_access_link_lambda = lambda x: isinstance(x, AccessLink)
  is_host_interface_lambda = lambda x: isinstance(x, HostInterface)
  is_port_lambda = lambda x: isinstance(x, ofp_phy_port)
  is_host = is_host or is_host_lambda
  is_switch = is_switch or is_switch_lambda
  is_network_link = is_network_link or is_network_link_lambda
  is_access_link = is_access_link or is_access_link_lambda
  is_host_interface = is_host_interface or is_host_interface_lambda
  is_port = is_port or is_port_lambda
  return functools.partial(Topology, hosts_manager=STSHostsManager(),
                           switches_manager=STSSwitchesManager(),
                           is_host=is_host, is_switch=is_switch,
                           is_network_link=is_network_link,
                           is_access_link=is_access_link,
                           is_host_interface=is_host_interface, is_port=is_port)



class TopologyTest(unittest.TestCase):
  @unittest.skip
  def test_build(self):
    # Arrange
    if1 = dict(hw_addr='00:00:00:00:00:01', ips='192.168.56.21')
    if2 = dict(hw_addr='00:00:00:00:00:02', ips='192.168.56.22')
    topo_cls = sts_topology_type_factory()
    topo = TopologyGraph()
    h1 = topo.add_host(interfaces=[if1, if2], name='h1')
    # Act
    net = topo_cls(topo_graph=topo, patch_panel=TestPatchPanel(),
                   policy=TopologyPolicy())
    net.build()
    # Assert
    self.assertEquals(h1, 'h1')
    self.assertEquals(len(topo._g.vertices), 3)
    self.assertEquals(list(topo.hosts_iter()), [h1])
    self.assertEquals(list(topo.interfaces_iter()), ['h1-eth0', 'h1-eth1'])
    self.assertEquals(len(topo.get_host_info(h1)['interfaces']), 2)
    self.assertEquals(topo.get_host_info(h1)['name'], h1)

  def test_create_interface(self):
    # Arrange
    topo_cls = sts_topology_type_factory()
    topo = topo_cls(patch_panel=STSPatchPanel(), policy=TopologyPolicy())
    # Act
    iface1 = topo.create_interface(hw_addr="00:00:00:00:00:11",
                                   ip_or_ips="1.2.3.4", name="eth1")
    iface2 = topo.create_interface(hw_addr="00:00:00:00:00:12",
                                   ip_or_ips="1.2.3.5", name="eth2")
    # Assert
    self.assertIsNotNone(iface1)
    self.assertIsNotNone(iface2)

  def test_create_host(self):
    # Arrange
    h1_eth1 = HostInterface(hw_addr='11:22:33:44:55:66', ip_or_ips='10.0.0.1')
    h2_eth1 = HostInterface(hw_addr='11:22:33:44:55:77', ip_or_ips='10.0.0.2')
    topo_cls = sts_topology_type_factory()
    topo = topo_cls(patch_panel=STSPatchPanel(), policy=TopologyPolicy())
    # Act
    h1 = topo.create_host(1, "h1", h1_eth1)
    h2 = topo.create_host(2, "h2", h2_eth1)
    # Assert
    self.assertIsNotNone(h1)
    self.assertIsNotNone(h2)
    self.assertItemsEqual([h1_eth1], h1.interfaces)
    self.assertItemsEqual([h2_eth1], h2.interfaces)
    self.assertTrue(topo.graph.has_host(h1))
    self.assertTrue(topo.graph.has_host(h2))
    self.assertTrue(h1 in topo.hosts_manager.live_hosts)
    self.assertTrue(h2 in topo.hosts_manager.live_hosts)

  def test_create_host_with_interfaces(self):
    # Arrange
    mac_gen = mac_addresses_generator()
    ip_gen = ip_addresses_generator()
    name_gen = interface_names_generator()
    topo_cls = sts_topology_type_factory()
    topo = topo_cls(patch_panel=STSPatchPanel(), policy=TopologyPolicy())
    # Act
    h1 = topo.create_host_with_interfaces(1, "h1", 2, mac_gen, ip_gen, name_gen)
    h2 = topo.create_host_with_interfaces(2, "h2", 3, mac_gen, ip_gen, name_gen)
    # Assert
    self.assertIsNotNone(h1)
    self.assertIsNotNone(h2)
    self.assertEquals(len(h1.interfaces), 2)
    self.assertEquals(len(h2.interfaces), 3)
    self.assertTrue(topo.graph.has_host(h1))
    self.assertTrue(topo.graph.has_host(h2))
    self.assertTrue(h1 in topo.hosts_manager.live_hosts)
    self.assertTrue(h2 in topo.hosts_manager.live_hosts)

  def test_add_host(self):
    # Arrange
    h1_eth1 = HostInterface(hw_addr='11:22:33:44:55:66', ip_or_ips='10.0.0.1')
    h2_eth1 = HostInterface(hw_addr='11:22:33:44:55:77', ip_or_ips='10.0.0.2')
    h1 = Host(h1_eth1, hid=1)
    h2 = Host(h2_eth1, hid=2)
    topo_cls = sts_topology_type_factory()
    topo = topo_cls(patch_panel=STSPatchPanel(), policy=TopologyPolicy())
    # Act
    topo.add_host(h1)
    topo.add_host(h2)
    duplicate_add = lambda: topo.add_host(h1)
    wrong_type = lambda: topo.add_host("Dummy")
    topo._can_add_hosts = False
    immutable_add = lambda: topo.add_host(h1)
    # Assert
    self.assertEquals(len(list(topo.graph.hosts_iter())), 2)
    self.assertRaises(AssertionError, duplicate_add)
    self.assertRaises(AssertionError, wrong_type)
    self.assertRaises(AssertionError, immutable_add)
    self.assertEquals(len(list(topo.graph.hosts_iter())), 2)
    self.assertTrue(topo.graph.has_host(h1))
    self.assertTrue(topo.graph.has_host(h2))
    self.assertTrue(topo.graph.has_host(h1.name))

  def test_remove_host(self):
    # Arrange
    h1_eth1 = HostInterface(hw_addr='11:22:33:44:55:66', ip_or_ips='10.0.0.1')
    h2_eth1 = HostInterface(hw_addr='11:22:33:44:55:77', ip_or_ips='10.0.0.2')
    h1 = Host(h1_eth1, hid=1)
    h2 = Host(h2_eth1, hid=2)
    topo_cls = sts_topology_type_factory()
    topo = topo_cls(patch_panel=STSPatchPanel(), policy=TopologyPolicy())
    topo.add_host(h1)
    topo.add_host(h2)
    # Act
    topo.remove_host(h1)
    # Assert
    self.assertFalse(topo.graph.has_host(h1))
    self.assertTrue(topo.graph.has_host(h2))

  def test_create_switch(self):
     # Arrange
    topo_cls = sts_topology_type_factory()
    topo = topo_cls(patch_panel=STSPatchPanel(), policy=TopologyPolicy())
    # Act
    switch = topo.create_switch(1, 2, True)
    # Assert
    self.assertTrue(topo.graph.has_switch(switch))

  def test_add_switch(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=1)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=1)
    topo_cls = sts_topology_type_factory()
    topo = topo_cls(patch_panel=STSPatchPanel(), policy=TopologyPolicy())
    # Act
    topo.add_switch(s1)
    topo.add_switch(s2)
    duplicate_add = lambda: topo.add_switch(s1)
    wrong_type = lambda: topo.add_switch("Dummy")
    topo._can_add_hosts = False
    immutable_add = lambda: topo.add_switch(s1)
    # Assert
    self.assertEquals(len(list(topo.graph.switches_iter())), 2)
    self.assertRaises(AssertionError, duplicate_add)
    self.assertRaises(AssertionError, wrong_type)
    self.assertRaises(AssertionError, immutable_add)
    self.assertEquals(len(list(topo.graph.switches_iter())), 2)
    self.assertTrue(topo.graph.has_switch(s1))
    self.assertTrue(topo.graph.has_switch(s2))
    self.assertFalse(topo.graph.has_switch('s3'))

  def test_remove_switch(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=1)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=1)
    topo_cls = sts_topology_type_factory()
    topo = topo_cls(patch_panel=STSPatchPanel(), policy=TopologyPolicy())
    topo.add_switch(s1)
    topo.add_switch(s2)
    # Act
    topo.remove_switch(s1)
    # Assert
    self.assertFalse(topo.graph.has_switch(s1))
    self.assertTrue(topo.graph.has_switch(s2))

  def test_create_network_link(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=1)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=1)
    topo_cls = sts_topology_type_factory()
    topo = topo_cls(patch_panel=STSPatchPanel(), policy=TopologyPolicy())
    topo.add_switch(s1)
    topo.add_switch(s2)
    # Act
    l1 = topo.create_network_link(s1, s1.ports[1], s2, s2.ports[1])
    # Assert
    self.assertEquals(l1.start_node, s1)
    self.assertEquals(l1.start_port, s1.ports[1])
    self.assertEquals(l1.end_node, s2)
    self.assertEquals(l1.end_port, s2.ports[1])

  def test_add_network_link(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=1)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=1)
    l1 = Link(s1, s1.ports[1], s2, s2.ports[1])
    topo_cls = sts_topology_type_factory()
    topo = topo_cls(patch_panel=STSPatchPanel(), policy=TopologyPolicy())
    topo.add_switch(s1)
    topo.add_switch(s2)
    # Act
    link = topo.add_network_link(l1)
    # Assert
    self.assertEquals(link, l1)
    self.assertTrue(topo.graph.has_link(link))
    self.assertIn(l1, topo.patch_panel.network_links)

  def test_add_bidir_link(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=1)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=1)
    l1 = BiDirectionalLinkAbstractClass(s1, s1.ports[1], s2, s2.ports[1])
    topo_cls = sts_topology_type_factory(
      is_network_link=lambda x: isinstance(x, BiDirectionalLinkAbstractClass))
    topo = topo_cls(patch_panel=STSPatchPanel(), policy=TopologyPolicy())
    #topo = Topology(patch_panel=TestPatchPanel(),
    #                link_cls=BiDirectionalLinkAbstractClass)
    topo.add_switch(s1)
    topo.add_switch(s2)
    # Act
    link = topo.add_network_link(l1)
    # Assert
    self.assertEquals(link, l1)
    self.assertTrue(topo.graph.has_link(link))

  def test_create_access_link(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=3)
    h1_eth1 = HostInterface(hw_addr='11:22:33:44:55:66', ip_or_ips='10.0.0.1')
    h1 = Host([h1_eth1], name='h1', hid=1)
    topo_cls = sts_topology_type_factory()
    topo = topo_cls(patch_panel=STSPatchPanel(), policy=TopologyPolicy())
    topo.add_switch(s1)
    topo.add_host(h1)
    # Act
    l1 = topo.create_access_link(h1, h1_eth1, s1, s1.ports[1])
    # Assert
    self.assertEquals(l1.host, h1)
    self.assertEquals(l1.interface, h1_eth1)
    self.assertEquals(l1.switch, s1)
    self.assertEquals(l1.switch_port, s1.ports[1])

  def test_add_access_link(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=3)
    h1_eth1 = HostInterface(hw_addr='11:22:33:44:55:66', ip_or_ips='10.0.0.1')
    h1 = Host([h1_eth1], name='h1', hid=1)
    topo_cls = sts_topology_type_factory()
    topo = topo_cls(patch_panel=STSPatchPanel(), policy=TopologyPolicy())
    topo.add_switch(s1)
    topo.add_host(h1)
    l1 = AccessLink(h1, h1_eth1, s1, s1.ports[1])
    # Act
    l1 = topo.add_access_link(l1)
    # Assert
    self.assertIn(l1, topo.patch_panel.access_links)
    self.assertTrue(topo.graph.has_link(l1))

  def test_remove_access_link(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=2)
    h1_eth1 = HostInterface(hw_addr='11:22:33:44:55:66', ip_or_ips='10.0.0.1')
    h1_eth2 = HostInterface(hw_addr='11:22:33:44:55:77', ip_or_ips='10.0.0.2')
    h1 = Host([h1_eth1, h1_eth2], name='h1', hid=1)
    topo_cls = sts_topology_type_factory()
    topo = topo_cls(patch_panel=STSPatchPanel(), policy=TopologyPolicy())
    topo.add_switch(s1)
    topo.add_host(h1)
    l1 = AccessLink(h1, h1_eth1, s1, s1.ports[1])
    l2 = AccessLink(h1, h1_eth2, s1, s1.ports[2])
    topo.add_network_link(l1)
    topo.add_network_link(l2)
    # Act
    topo.remove_access_link(l1)
    # Assert
    self.assertFalse(topo.graph.has_link(l1))
    self.assertNotIn(l1, topo.patch_panel.access_links)
    self.assertTrue(topo.graph.has_link(l2))
    self.assertIn(l2, topo.patch_panel.access_links)

  def test_remove_network_link(self):
    # Arrange
    s1 = FuzzSoftwareSwitch(1, 's1', ports=3)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=3)
    l1 = Link(s1, s1.ports[1], s2, s2.ports[1])
    l2 = Link(s1, s1.ports[2], s2, s2.ports[2])
    l3 = Link(s1, s1.ports[3], s2, s2.ports[3])
    topo_cls = sts_topology_type_factory()
    topo = topo_cls(patch_panel=STSPatchPanel(), policy=TopologyPolicy())
    topo.add_switch(s1)
    topo.add_switch(s2)
    topo.add_network_link(l1)
    topo.add_network_link(l2)
    topo.add_network_link(l3)
    # Act
    topo.remove_network_link(l1)
    # Assert
    self.assertFalse(topo.graph.has_link(l1))
    self.assertNotIn(l1, topo.patch_panel.network_links)
    self.assertTrue(topo.graph.has_link(l2))
    self.assertIn(l2, topo.patch_panel.network_links)

  def test_crash_switch(self):
    # Arrange
    topo_cls = sts_topology_type_factory()
    topo = topo_cls(patch_panel=STSPatchPanel(), policy=TopologyPolicy())
    s1 = FuzzSoftwareSwitch(1, 's1', ports=0)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=0)
    topo.add_switch(s1)
    topo.add_switch(s2)
    # Act
    topo.switches_manager.crash_switch(s1)
    # Assert
    self.assertEquals(len(topo.switches_manager.failed_switches), 1)
    self.assertIn(s1, topo.switches_manager.failed_switches)
    self.assertEquals(topo.switches_manager.live_switches, set([s2]))

  def test_recover_switch(self):
    # Arrange
    topo_cls = sts_topology_type_factory()
    topo = topo_cls(patch_panel=STSPatchPanel(), policy=TopologyPolicy())
    s1 = FuzzSoftwareSwitch(1, 's1', ports=0)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=0)
    topo.add_switch(s1)
    topo.add_switch(s2)
    topo.switches_manager.crash_switch(s1)
    topo.switches_manager.crash_switch(s2)
    s1.recover = lambda down_controller_ids: True
    # Act
    topo.switches_manager.recover_switch(s1)
    # Assert
    self.assertEquals(len(topo.switches_manager.failed_switches), 1)
    self.assertIn(s2, topo.switches_manager.failed_switches)
    self.assertEquals(topo.switches_manager.live_switches, set([s1]))

  def test_live_edge_switches(self):
    # Arrange
    topo_cls = sts_topology_type_factory()
    topo = topo_cls(patch_panel=STSPatchPanel(), policy=TopologyPolicy())
    s1 = FuzzSoftwareSwitch(1, 's1', ports=0)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=0)
    topo.add_switch(s1)
    topo.add_switch(s2)
    topo.switches_manager.crash_switch(s1)
    # Act
    live_edge = topo.switches_manager.live_edge_switches
    # Assert
    self.assertEquals(len(topo.switches_manager.failed_switches), 1)
    self.assertIn(s1, topo.switches_manager.failed_switches)
    self.assertEquals(topo.switches_manager.live_switches, set([s2]))
    self.assertItemsEqual(live_edge, [s2])
