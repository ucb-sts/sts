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

from sts.entities.sts_entities import FuzzSoftwareSwitch

from sts.topology.sts_switches_manager import STSSwitchesManager


class STSSwitchesManagerTest(unittest.TestCase):
  def test_add_switch(self):
    # Arrange
    sw1 = FuzzSoftwareSwitch(1, 's1', ports=1)
    sw2 = FuzzSoftwareSwitch(2, 's2', ports=1)
    manager = STSSwitchesManager()
    # Act
    manager.add_switch(sw1)
    manager.add_switch(sw2)
    # Assert
    self.assertIn(sw1, manager.live_switches)
    self.assertIn(sw2, manager.live_switches)

  def test_create_switch(self):
    # Arrange
    manager = STSSwitchesManager()
    # Act
    switch = manager.create_switch(1, 2, True)
    # Assert
    self.assertIsInstance(switch, FuzzSoftwareSwitch)

  def test_crash_switch(self):
    # Arrange
    sw1 = FuzzSoftwareSwitch(1, 's1', ports=1)
    sw2 = FuzzSoftwareSwitch(2, 's2', ports=1)
    manager = STSSwitchesManager()
    manager.add_switch(sw1)
    manager.add_switch(sw2)
    # Act
    manager.crash_switch(sw1)
    # Assert
    self.assertNotIn(sw1, manager.live_switches)
    self.assertIn(sw1, manager.failed_switches)
    self.assertIn(sw2, manager.live_switches)

  @unittest.skip
  def test_recover_switch(self):
    # Arrange
    sw1 = FuzzSoftwareSwitch(1, 's1', ports=1)
    sw2 = FuzzSoftwareSwitch(2, 's2', ports=1)
    manager = STSSwitchesManager()
    manager.add_switch(sw1)
    manager.add_switch(sw2)
    manager.crash_switch(sw1)
    manager.crash_switch(sw2)
    # Act
    manager.recover_switch(sw1)
    # Assert
    self.assertNotIn(sw1, manager.failed_switches)
    self.assertIn(sw1, manager.live_switches)
    self.assertIn(sw2, manager.failed_switches)
