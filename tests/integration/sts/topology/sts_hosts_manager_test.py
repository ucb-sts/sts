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

import unittest

from sts.entities.hosts import Host

from sts.topology.hosts_manager import mac_addresses_generator
from sts.topology.hosts_manager import ip_addresses_generator
from sts.topology.hosts_manager import interface_names_generator


from sts.topology.sts_hosts_manager import STSHostsManager




class STSHostsManagerTest(unittest.TestCase):
  def test_create_host(self):
    # Arrange
    manager = STSHostsManager()
    interfaces = ["dummy_iface"]
    # Act
    host1 = manager.create_host(1, "h1", interfaces)
    host2 = manager.create_host(2, "h2", None)
    # Assert
    self.assertIsNotNone(host1)
    self.assertIsNotNone(host2)
    self.assertItemsEqual(interfaces, host1.interfaces)
    self.assertItemsEqual([], host2.interfaces)

  def test_create_interface(self):
    # Arrange
    manager = STSHostsManager()
    # Act
    iface1 = manager.create_interface(hw_addr="00:00:00:00:00:11",
                                      ip_or_ips="1.2.3.4", name="ethost1")
    iface2 = manager.create_interface(hw_addr="00:00:00:00:00:12",
                                      ip_or_ips="1.2.3.5", name="ethost2")
    # Assert
    self.assertIsNotNone(iface1)
    self.assertIsNotNone(iface2)

  def test_create_host_with_interfaces(self):
    # Arrange
    manager = STSHostsManager()
    mac_gen = mac_addresses_generator()
    ip_gen = ip_addresses_generator()
    name_gen = interface_names_generator()
    # Act
    host1 = manager.create_host_with_interfaces(1, "h1", 2, mac_gen, ip_gen,
                                             name_gen)
    host2 = manager.create_host_with_interfaces(2, "h2", 3, mac_gen, ip_gen,
                                             name_gen)
    # Assert
    self.assertIsNotNone(host1)
    self.assertIsNotNone(host2)
    self.assertEquals(len(host1.interfaces), 2)
    self.assertEquals(len(host2.interfaces), 3)

  def test_add_host(self):
    # Arrange
    host1 = Host(None, "h1", 1)
    host2 = Host(None, "h2", 2)
    manager = STSHostsManager()
    # Act
    manager.add_host(host1)
    manager.add_host(host2)
    # Assert
    self.assertIn(host1, manager.live_hosts)
    self.assertIn(host2, manager.live_hosts)

  def test_remove_host(self):
    # Arrange
    host1 = Host(None, "h1", 1)
    host2 = Host(None, "h2", 2)
    host3 = Host(None, "h3", 3)
    host4 = Host(None, "h4", 4)
    manager = STSHostsManager()
    manager.add_host(host1)
    manager.add_host(host2)
    manager._failed_hosts.add(host4)
    # Act
    manager.remove_host(host1)
    manager.remove_host(host4)
    fail_remove = lambda: manager.remove_host(host3)
    # Assert
    self.assertNotIn(host1, manager.live_hosts)
    self.assertNotIn(host1, manager.failed_hosts)
    self.assertNotIn(host4, manager.live_hosts)
    self.assertNotIn(host4, manager.failed_hosts)
    self.assertIn(host2, manager.live_hosts)
    self.assertRaises(ValueError, fail_remove)

  def test_crash_host(self):
     # Arrange
    host1 = Host(None, "h1", 1)
    manager = STSHostsManager()
    manager.add_host(host1)
    # Act
    fail_crash = lambda: manager.crash_host(host1)
    # Assert
    self.assertRaises(AssertionError, fail_crash)

  def test_recover_host(self):
     # Arrange
    host1 = Host(None, "h1", 1)
    manager = STSHostsManager()
    manager.add_host(host1)
    # Act
    fail_recover = lambda: manager.recover_host(host1)
    # Assert
    self.assertRaises(AssertionError, fail_recover)

  def test_up_hosts(self):
    # Arrange
    host1 = Host(None, "h1", 1)
    host2 = Host(None, "h2", 2)
    manager = STSHostsManager()
    # Act
    manager.add_host(host1)
    manager.add_host(host2)
    # Assert
    self.assertIn(host1, manager.up_hosts)
    self.assertIn(host2, manager.up_hosts)

  def test_down_hosts(self):
    # Arrange
    host1 = Host(None, "h1", 1)
    host2 = Host(None, "h2", 2)
    manager = STSHostsManager()
    # Act
    manager.add_host(host1)
    manager.add_host(host2)
    # Assert
    self.assertNotIn(host1, manager.down_hosts)
    self.assertNotIn(host2, manager.down_hosts)

  def test_hosts(self):
    # Arrange
    host1 = Host(None, "h1", 1)
    host2 = Host(None, "h2", 2)
    host3 = Host(None, "h3", 3)
    host4 = Host(None, "h4", 4)
    manager = STSHostsManager()
    manager.add_host(host1)
    manager.add_host(host2)
    manager.add_host(host3)
    manager._failed_hosts.add(host4)
    # Act
    hosts = manager.hosts
    # Assert
    self.assertIn(host1, hosts)
    self.assertIn(host2, hosts)
    self.assertIn(host3, hosts)
    self.assertIn(host4, hosts)