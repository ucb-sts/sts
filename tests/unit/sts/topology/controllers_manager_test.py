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

  def test_up_controllers(self):
    # Arrange
    c1 = mock.Mock(name='c1')
    c1.state = ControllerState.ALIVE
    c2 = mock.Mock(name='c2')
    c2.state = ControllerState.DEAD
    manager = ControllersManager()
    manager.add_controller(c1)
    manager.add_controller(c2)
    # Act
    c1.check_status.return_value = ControllerState.ALIVE
    c2.check_status.return_value = ControllerState.DEAD
    # Assert
    self.assertIn(c1, manager.up_controllers)
    self.assertNotIn(c1, manager.down_controllers)
    self.assertIn(c2, manager.down_controllers)
    self.assertNotIn(c2, manager.up_controllers)

  def test_block_peers(self):
    # Arrange
    c1 = mock.Mock(name='c1')
    c2 = mock.Mock(name='c2')
    manager = ControllersManager()
    manager.add_controller(c1)
    manager.add_controller(c2)
    # Act
    manager.block_peers(c1, c2)
    # Assert
    c1.block_peer.assert_called_once_with(c2)

  def test_unblock_peers(self):
    # Arrange
    c1 = mock.Mock(name='c1')
    c2 = mock.Mock(name='c2')
    manager = ControllersManager()
    manager.add_controller(c1)
    manager.add_controller(c2)
    # Act
    manager.unblock_peers(c1, c2)
    # Assert
    c1.unblock_peer.assert_called_once_with(c2)