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

# TODO (AH): Provide optional test for BigSwitch, ONOS, and other controllers


import time
import unittest

from sts.entities.base import LocalEntity
from sts.entities.base import SSHEntity
from sts.entities.controllers import ControllerConfig
from sts.entities.controllers import ControllerState
from sts.entities.controllers import POXController
from sts.entities.controllers import ONOSController


class POXControllerTest(unittest.TestCase):
  # TODO (AH): Test sync and namespaces

  def get_config(self):
    start_cmd = ("./pox.py --verbose --no-cli sts.syncproto.pox_syncer "
                 "--blocking=False openflow.of_01 --address=__address__ "
                 "--port=__port__")
    kill_cmd = ""
    cwd = "pox"
    config = ControllerConfig(start_cmd=start_cmd, kill_cmd=kill_cmd, cwd=cwd)
    return config

  def test_start(self):
    # Arrange
    config = self.get_config()
    # Act
    ctrl = POXController(controller_config=config)
    ctrl.start(None)
    time.sleep(5)
    state1 = ctrl.state
    check_status1 = ctrl.check_status(None)
    ctrl.kill()
    time.sleep(5)
    state2 = ctrl.state
    check_status2 = ctrl.check_status(None)
    #Assert
    self.assertEquals(state1, ControllerState.ALIVE)
    self.assertEquals(state2, ControllerState.DEAD)
    self.assertEquals(check_status1[0], True)
    self.assertEquals(check_status2[0], True)

  def test_restart(self):
    # Arrange
    config = self.get_config()
    # Act
    ctrl = POXController(controller_config=config)
    ctrl.start(None)
    time.sleep(5)
    state1 = ctrl.state
    check_status1 = ctrl.check_status(None)
    ctrl.kill()

    ctrl.restart()
    time.sleep(5)
    state2 = ctrl.state
    check_status2 = ctrl.check_status(None)

    ctrl.kill()
    time.sleep(5)
    state3 = ctrl.state
    check_status3 = ctrl.check_status(None)
    #Assert
    self.assertEquals(state1, ControllerState.ALIVE)
    self.assertEquals(state2, ControllerState.ALIVE)
    self.assertEquals(state3, ControllerState.DEAD)
    self.assertEquals(check_status1[0], True)
    self.assertEquals(check_status2[0], True)
    self.assertEquals(check_status3[0], True)


  def test_start(self):
    # Arrange
    config = self.get_config()
    # Act
    ctrl = POXController(controller_config=config)
    ctrl.start(None)
    time.sleep(5)
    state1 = ctrl.state
    check_status1 = ctrl.check_status(None)
    ctrl.kill()
    time.sleep(5)
    state2 = ctrl.state
    check_status2 = ctrl.check_status(None)
    #Assert
    self.assertEquals(state1, ControllerState.ALIVE)
    self.assertEquals(state2, ControllerState.DEAD)
    self.assertEquals(check_status1[0], True)
    self.assertEquals(check_status2[0], True)


class ONOSControllerTest(unittest.TestCase):
  def get_config(self):
    start_cmd = "./start-onos.sh start"
    kill_cmd = "./start-onos.sh stop"
    restart_cmd = "./start-onos.sh stop"
    check = "./start-onos.sh status"
    address = '192.168.56.11'
    cwd = "ONOS"
    config = ControllerConfig(address=address, start_cmd=start_cmd,
                              kill_cmd=kill_cmd, restart_cmd=restart_cmd,
                              check_cmd=check, cwd=cwd)
    return config

  def get_executor(self):
    address = '192.168.56.11'
    ssh = SSHEntity(address, username='mininet', password='mininet', cwd='ONOS',
                    label='ONOSDEV', redirect_output=True)
    return ssh

  def setUp(self):
    cmd_exec = LocalEntity(redirect_output=True)
    cmd_exec.execute_command("onos stop")
    cmd_exec.execute_command("cassandra start")
    cmd_exec.execute_command("cassandra  start")

  def tearDown(self):
    cmd_exec = LocalEntity(redirect_output=True)
    cmd_exec.execute_command("onos stop")
    cmd_exec.execute_command("cassandra stop")
    cmd_exec.execute_command("zk status stop")

  @unittest.skip
  def test_start_kill(self):
    # Arrange
    config = self.get_config()
    cmd_exec = self.get_executor()

    # Act
    ctrl = ONOSController(controller_config=config, cmd_executor=cmd_exec)
    ctrl.start(None)
    time.sleep(20)
    state1 = ctrl.state
    check_status1 = ctrl.check_status(None)
    # clean up
    ctrl.kill()
    time.sleep(5)
    state2 = ctrl.state
    check_status2 = ctrl.check_status(None)
    #Assert
    self.assertEquals(state1, ControllerState.ALIVE)
    self.assertEquals(state2, ControllerState.DEAD)
    self.assertEquals(check_status1[0], True)
    self.assertEquals(check_status2[0], True)
