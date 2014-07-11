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

from sts.entities.controllers import ControllerConfig
from sts.entities.controllers import POXController

from sts.topology.controllers_manager import ControllersManager


class ControllersManagerTest(unittest.TestCase):
  def get_config(self, address='127.0.0.1', port=6633):
    start_cmd = ("./pox.py --verbose --no-cli sts.syncproto.pox_syncer "
                 "--blocking=False openflow.of_01 --address=__address__ "
                 "--port=__port__")
    kill_cmd = ""
    cwd = "pox"
    config = ControllerConfig(start_cmd=start_cmd, kill_cmd=kill_cmd, cwd=cwd,
                              address=address, port=port)
    return config

  def get_controller(self, address='127.0.0.1', port=6633):
    config = self.get_config(address, port)
    ctrl = POXController(controller_config=config)
    return ctrl

  def test_add_controller(self):
    # Arrange
    c1 = self.get_controller(port=6633)
    c1.start()
    c2 = self.get_controller(port=6644)
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
    c1 = self.get_controller(port=6633)
    c1.start()
    c2 = self.get_controller(port=6644)
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
    c1 = self.get_controller(port=6633)
    c1.start()
    c2 = self.get_controller(port=6644)
    manager = ControllersManager()
    manager.add_controller(c1)
    manager.add_controller(c2)
    # Act
    # Assert
    self.assertIn(c1, manager.up_controllers)
    self.assertNotIn(c1, manager.down_controllers)
    self.assertIn(c2, manager.down_controllers)
    self.assertNotIn(c2, manager.up_controllers)


  def test_crash_controller(self):
    # Arrange
    c1 = self.get_controller(port=6633)
    c1.start()
    c2 = self.get_controller(port=6644)
    c2.start()
    manager = ControllersManager()
    manager.add_controller(c1)
    manager.add_controller(c2)
    # Act
    manager.crash_controller(c1)
    # Assert
    self.assertIn(c1, manager.controllers)
    self.assertIn(c2, manager.controllers)
    self.assertIn(c1, manager.failed_controllers)
    self.assertIn(c2, manager.live_controllers)


  def test_recover_controller(self):
    # Arrange
    c1 = self.get_controller(port=6633)
    c2 = self.get_controller(port=6644)
    manager = ControllersManager()
    manager.add_controller(c1)
    manager.add_controller(c2)
    # Act
    manager.recover_controller(c1)
    # Assert
    self.assertIn(c1, manager.controllers)
    self.assertIn(c2, manager.controllers)
    self.assertIn(c1, manager.live_controllers)
    self.assertIn(c2, manager.failed_controllers)

  def test_create_controller(self):
    # Arrange
    manager = ControllersManager()
    # Act
    failed = lambda: manager.create_controller('127.0.0.1', 6633)
    # Assert
    self.assertRaises(AssertionError, failed)
