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

# TODO: Provide optional test for BigSwitch, ONOS, and other controllers


import time
import unittest

from sts.entities.controllers import ControllerConfig
from sts.entities.controllers import ControllerState
from sts.entities.controllers import POXController


class POXControllerTest(unittest.TestCase):
  # TODO: Test sync and namespaces

  def get_config(self):
    start_cmd = "./pox.py --verbose --no-cli sts.syncproto.pox_syncer " +\
                "--blocking=False openflow.of_01 --address=__address__ " +\
                "--port=__port__"
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
