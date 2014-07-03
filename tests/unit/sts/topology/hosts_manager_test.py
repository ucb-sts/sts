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


import re
import unittest

from tests.unit.sts.util.capability_test import CapabilitiesGenericTest

from sts.topology.hosts_manager import HostsManagerCapabilities
from sts.topology.hosts_manager import mac_addresses_generator
from sts.topology.hosts_manager import ip_addresses_generator
from sts.topology.hosts_manager import interface_names_generator


class GeneratorsTest(unittest.TestCase):
  def test_mac_addresses_generator(self):
    # Arrange
    macs = []
    max_num = 5
    gen = mac_addresses_generator(max_num)
    # Act
    for mac in gen:
      macs.append(mac)
    # Assert
    self.assertEquals(len(macs), max_num)
    for mac in macs:
      match = re.match("[0-9a-f]{2}([-:])[0-9a-f]{2}(\\1[0-9a-f]{2}){4}$",
                       mac.lower())
      self.assertTrue(match)

  def test_ip_addresses_generator(self):
    # Arrange
    addresses = []
    max_num = 5
    gen = ip_addresses_generator(max_num)
    # Act
    for address in gen:
      addresses.append(address)
    # Assert
    self.assertEquals(len(addresses), max_num)

  def test_interface_names_generator(self):
    # Arrange
    names = []
    max_num = 5
    gen = interface_names_generator(max_names=max_num)
    # Act
    for name in gen:
      names.append(name)
    # Assert
    self.assertEquals(len(names), max_num)


class HostsManagerCapabilitiesTest(CapabilitiesGenericTest):
  def setUp(self):
    self._capabilities_cls = HostsManagerCapabilities
