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

from tests.unit.sts.util.capability_test import CapabilitiesGenericTest
from sts.topology.base import TopologyCapabilities


class TopologyCapabilitiesTest(CapabilitiesGenericTest):
  def test_set_add_policy(self):
    # Arrange
    policy1 = TopologyCapabilities()
    policy2 = TopologyCapabilities()
    # Act
    policy1.set_add_policy(False)
    policy2.set_add_policy(True)
    # Assert
    self.assertFalse(policy1.can_add_network_link)
    self.assertFalse(policy1.can_add_access_link)
    self.assertFalse(policy1.can_add_switch)
    self.assertFalse(policy1.can_add_host)
    self.assertTrue(policy2.can_add_network_link)
    self.assertTrue(policy2.can_add_access_link)
    self.assertTrue(policy2.can_add_switch)
    self.assertTrue(policy2.can_add_host)

  def test_set_remove_policy(self):
    # Arrange
    policy1 = TopologyCapabilities()
    policy2 = TopologyCapabilities()
    # Act
    policy1.set_remove_policy(False)
    policy2.set_remove_policy(True)
    # Assert
    self.assertFalse(policy1.can_remove_network_link)
    self.assertFalse(policy1.can_remove_switch)
    self.assertFalse(policy1.can_remove_access_link)
    self.assertFalse(policy1.can_remove_host)
    self.assertTrue(policy2.can_remove_network_link)
    self.assertTrue(policy2.can_remove_switch)
    self.assertTrue(policy2.can_remove_access_link)
    self.assertTrue(policy2.can_remove_host)
