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

from sts.entities.controllers import Controller
from sts.entities.controllers import ControllerAbstractClass
from sts.entities.controllers import ControllerState


class ControllerAbstractClassTest(unittest.TestCase):
  def get_concrete_class(self):
    """Simple mock for the abstract methods and properties"""
    class ControllerImpl(ControllerAbstractClass):
      def is_remote(self):
        return True

      @property
      def blocked_peers(self):
        return True

      def start(self, multiplex_sockets=False):
        return True

      def block_peer(self, peer_controller):
        return True

      def unblock_peer(self, peer_controller):
        return True

      def check_status(self, simulation):
        return ControllerState.ALIVE, "ALIVE"

    return ControllerImpl

  def test_init(self):
    # Arrange
    config = mock.MagicMock()
    label = "dummy_controller"
    cid = 123
    config.label = label
    config.cid = cid
    controller_cls = self.get_concrete_class()
    # Act
    c = controller_cls(config)
    # Assert
    self.assertEquals(c.config, config)
    self.assertEquals(c.state, ControllerState.DEAD)
    self.assertEquals(c.cid, cid)
    self.assertEquals(c.label, label)


class ControllerTest(unittest.TestCase):
  """
  TODO: test restart, snapshot_proceed, and check_status methods
  """
  def get_config(self):
    config = mock.MagicMock()
    label = "dummy_controller"
    cid = 123
    config.label = label
    config.cid = cid
    config.address = "localhost"
    config.launch_in_network_namespace = False
    config.start_cmd = ":" # NOP
    config.expanded_start_cmd = ["ls"] # NOP
    config.kill_cmd = ":" # NOP
    config.expanded_kill_cmd = ["ls"] # NOP
    config.cwd = "."
    config.snapshot_address = False
    return config

  def test_init(self):
    # Arrange
    config = self.get_config()
    c = Controller(config)
    # Act
    con = c.config
    state = c.state
    cid = c.cid
    label = c.label
    # Assert
    self.assertEquals(con, config)
    self.assertEquals(state, ControllerState.DEAD)
    self.assertEquals(cid, config.cid)
    self.assertEquals(label, config.label)

  def test_remote(self):
    # Arrange
    config1 = self.get_config()
    config2 = self.get_config()
    config2.address = "192.168.56.1"
    c1 = Controller(config1)
    c2 = Controller(config2)
    # Act
    is_remote1 = c1.is_remote
    is_remote2 = c2.is_remote
    # Assert
    self.assertFalse(is_remote1)
    self.assertTrue(is_remote2)

  def test_start(self):
    # Arrange
    config = self.get_config()
    Controller._check_snapshot_connect = mock.Mock()
    Controller._register_proc = mock.Mock()
    Controller._check_snapshot_connect = mock.Mock()
    Controller.kill = mock.Mock()
    c = Controller(config)
    # Act
    c.start()
    state = c.state
    del c # To make sure the clean up was done properly
    # Assert
    self.assertEquals(state, ControllerState.ALIVE)
    self.assertEquals(Controller._register_proc.call_count, 1)
    self.assertEquals(Controller.kill.call_count, 1)

  def test_kill(self):
    # Arrange
    config = self.get_config()
    Controller._check_snapshot_connect = mock.Mock()
    Controller._unregister_proc = mock.Mock()
    Controller._check_snapshot_connect = mock.Mock()
    c = Controller(config)
    c.state = ControllerState.ALIVE
    # Act
    c.kill()
    state = c.state
    # Assert
    self.assertEquals(state, ControllerState.DEAD)
    self.assertEquals(Controller._unregister_proc.call_count, 1)
    self.assertIsNone(c.process)
