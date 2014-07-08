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

import socket
import unittest

from pox.lib.util import connect_socket_with_backoff

from sts.entities.controllers import ControllerConfig
from sts.entities.controllers import POXController
from sts.entities.sts_entities import FuzzSoftwareSwitch
from sts.entities.sts_entities import DeferredOFConnection
from sts.openflow_buffer import OpenFlowBuffer
from sts.util.io_master import IOMaster
from sts.util.deferred_io import DeferredIOWorker

from sts.topology.controllers_manager import ControllersManager
from sts.topology.sts_switches_manager import STSSwitchesManager


class STSSwitchesManagerTest(unittest.TestCase):

  def initialize_io_loop(self):
    io_master = IOMaster()
    return io_master

  def create_connection(self, controller_info, switch,
                        max_backoff_seconds=1024):
    """Connect switches to controllers. May raise a TimeoutError"""
    socket_ctor = socket.socket
    sock = connect_socket_with_backoff(controller_info.config.address,
                                       controller_info.config.port,
                                       max_backoff_seconds=max_backoff_seconds,
                                       socket_ctor=socket_ctor)
    # Set non-blocking
    sock.setblocking(0)
    io_worker = DeferredIOWorker(self.io_master.create_worker_for_socket(sock))
    connection = DeferredOFConnection(io_worker, controller_info.cid,
                                      switch.dpid, self.openflow_buffer)
    return connection

  def get_controller_config(self, cid, address='127.0.0.1', port=6633):
    start_cmd = ("./pox.py --verbose --no-cli sts.syncproto.pox_syncer "
                 "--blocking=False openflow.of_01 --address=__address__ "
                 "--port=__port__")
    kill_cmd = ""
    cwd = "pox"
    config = ControllerConfig(start_cmd=start_cmd, kill_cmd=kill_cmd, cwd=cwd,
                              address=address, port=port, cid=cid)
    return config

  def get_controller(self, cid, address='127.0.0.1', port=6633):
    config = self.get_controller_config(cid, address, port)
    ctrl = POXController(controller_config=config)
    return ctrl

  def setUp(self):
    self.io_master = self.initialize_io_loop()
    self.openflow_buffer = OpenFlowBuffer()

  def test_add_switch(self):
    # Arrange
    sw1 = FuzzSoftwareSwitch(1, 's1', ports=1)
    sw2 = FuzzSoftwareSwitch(2, 's2', ports=1)
    manager = STSSwitchesManager(self.create_connection)
    # Act
    manager.add_switch(sw1)
    manager.add_switch(sw2)
    # Assert
    self.assertIn(sw1, manager.live_switches)
    self.assertIn(sw2, manager.live_switches)

  def test_create_switch(self):
    # Arrange
    manager = STSSwitchesManager(self.create_connection)
    # Act
    switch = manager.create_switch(1, 2, True)
    # Assert
    self.assertIsInstance(switch, FuzzSoftwareSwitch)

  def test_crash_switch(self):
    # Arrange
    sw1 = FuzzSoftwareSwitch(1, 's1', ports=1)
    sw2 = FuzzSoftwareSwitch(2, 's2', ports=1)
    manager = STSSwitchesManager(self.create_connection)
    manager.add_switch(sw1)
    manager.add_switch(sw2)
    # Act
    manager.crash_switch(sw1)
    # Assert
    self.assertNotIn(sw1, manager.live_switches)
    self.assertIn(sw1, manager.failed_switches)
    self.assertIn(sw2, manager.live_switches)

  def test_recover_switch(self):
    # Arrange
    sw1 = FuzzSoftwareSwitch(1, 's1', ports=1)
    sw2 = FuzzSoftwareSwitch(2, 's2', ports=1)
    c1 = self.get_controller(1, port=6633)
    c1.start()
    manager = STSSwitchesManager(self.create_connection)
    manager.add_switch(sw1)
    manager.add_switch(sw2)
    manager.connect_to_controllers(sw1, c1)
    manager.crash_switch(sw1)
    manager.crash_switch(sw2)
    # Act
    manager.recover_switch(sw1)
    # Assert
    self.assertNotIn(sw1, manager.failed_switches)
    self.assertIn(sw1, manager.live_switches)
    self.assertIn(sw2, manager.failed_switches)

  def test_switches(self):
    # Arrange
    sw1 = FuzzSoftwareSwitch(1, 's1', ports=1)
    sw2 = FuzzSoftwareSwitch(2, 's2', ports=1)
    manager = STSSwitchesManager(self.create_connection)
    manager.add_switch(sw1)
    manager.add_switch(sw2)
    manager.crash_switch(sw1)
    # Act
    switches = manager.switches
    # Assert
    self.assertIn(sw1, switches)
    self.assertIn(sw2, switches)

  def test_connect(self):
    # Arrange
    manager = STSSwitchesManager(self.create_connection)
    s1 = manager.create_switch(1, 2, True)
    s2 = manager.create_switch(2, 2, True)
    manager.add_switch(s1)
    manager.add_switch(s2)
    c1 = self.get_controller(1, port=6633)
    c1.start()
    c2 = self.get_controller(2,port=6644)
    c2.start()
    c3 = self.get_controller(3, port=6655)
    c3.start()
    # Act
    manager.connect_to_controllers(s1, c1)
    manager.connect_to_controllers(s2, [c1, c2])
    # Assert
    self.assertTrue(s1.is_connected_to(c1.cid))
    self.assertTrue(s2.is_connected_to(c2.cid))
    self.assertFalse(s1.is_connected_to(c3.cid))
    self.assertFalse(s2.is_connected_to(c3.cid))

  def test_get_connected_controllers(self):
    # Arrange
    manager = STSSwitchesManager(self.create_connection)
    s1 = manager.create_switch(1, 2, True)
    s2 = manager.create_switch(2, 2, True)
    manager.add_switch(s1)
    manager.add_switch(s2)
    c1 = self.get_controller(1, port=6633)
    c1.start()
    c2 = self.get_controller(2,port=6644)
    c2.start()
    c3 = self.get_controller(3, port=6655)
    c3.start()
    c_mgm = ControllersManager()
    c_mgm.add_controller(c1)
    c_mgm.add_controller(c2)
    c_mgm.add_controller(c3)
    manager.connect_to_controllers(s1, c1)
    manager.connect_to_controllers(s2, [c1, c2])
    # Act
    s1_controllers = manager.get_connected_controllers(s1, c_mgm)
    s2_controllers = manager.get_connected_controllers(s2, c_mgm)
    # Assert
    self.assertTrue(s1.is_connected_to(c1.cid))
    self.assertTrue(s2.is_connected_to(c2.cid))
    self.assertFalse(s1.is_connected_to(c3.cid))
    self.assertFalse(s2.is_connected_to(c3.cid))
    self.assertItemsEqual([c1], s1_controllers)
    self.assertItemsEqual([c1, c2], s2_controllers)

  def test_disconnect_controllers(self):
    # Arrange
    manager = STSSwitchesManager(self.create_connection)
    s1 = manager.create_switch(1, 2, True)
    manager.add_switch(s1)
    c1 = self.get_controller(1, port=6633)
    c1.start()
    c2 = self.get_controller(2,port=6644)
    c2.start()
    c_mgm = ControllersManager()
    c_mgm.add_controller(c1)
    c_mgm.add_controller(c2)
    manager.connect_to_controllers(s1, [c1, c2])
    # Act
    manager.disconnect_controllers(s1)
    # Assert
    self.assertFalse(s1.is_connected_to(c1.cid))
    self.assertFalse(s1.is_connected_to(c2.cid))
    self.assertEquals(manager.get_connected_controllers(s1, c_mgm), [])
