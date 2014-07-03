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


import mock
import unittest

from tests.unit.sts.util.capability_test import CapabilitiesGenericTest

from sts.entities.controllers import ControllerState
from sts.topology.controllers_manager import ControllersManager
from sts.topology.controllers_manager import ControllersManagerCapabilities


class ControllersManagerCapabilitiesTest(CapabilitiesGenericTest):
  def setUp(self):
    self._capabilities_cls = ControllersManagerCapabilities


class ControllersManagerTest(unittest.TestCase):
  def test_add_controller(self):
    # Arrange
    c1 = mock.Mock(name='c1')
    c1.state = ControllerState.ALIVE
    c2 = mock.Mock(name='c2')
    c2.state = ControllerState.DEAD
    manager = ControllersManager()
    # Act
    manager.add_controller(c1)
    manager.add_controller(c2)
    failed_add1 = lambda: manager.add_controller(c1)
    failed_add2 = lambda: manager.add_controller(c2)
    # Assert
    self.assertIn(c1, manager.controllers)
    self.assertIn(c2, manager.controllers)
    self.assertIn(c1, manager.live_controllers)
    self.assertIn(c2, manager.failed_controllers)
    self.assertRaises(AssertionError, failed_add1)
    self.assertRaises(AssertionError, failed_add2)

  def test_remove_controller(self):
    # Arrange
    c1 = mock.Mock(name='c1')
    c1.state = ControllerState.ALIVE
    c2 = mock.Mock(name='c2')
    c2.state = ControllerState.DEAD
    manager = ControllersManager()
    manager.add_controller(c1)
    manager.add_controller(c2)
    # Act
    manager.remove_controller(c1)
    manager.remove_controller(c2)
    failed_remove1 = lambda: manager.remove_controller(c1)
    failed_remove2 = lambda: manager.remove_controller(c2)
    # Assert
    self.assertNotIn(c1, manager.controllers)
    self.assertNotIn(c2, manager.controllers)
    self.assertNotIn(c1, manager.live_controllers)
    self.assertNotIn(c2, manager.failed_controllers)
    self.assertRaises(AssertionError, failed_remove1)
    self.assertRaises(AssertionError, failed_remove2)
