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

from sts.replay_event import ControllerFailure
from sts.replay_event import ControllerRecovery
from sts.replay_event import LinkFailure
from sts.replay_event import LinkRecovery
from sts.replay_event import SwitchFailure
from sts.replay_event import SwitchRecovery
from sts.replay_event import TrafficInjection

from sts.topology.sts_topology import MeshTopology

from sts.control_flow.fuzzer_new import FuzzerParams
from sts.control_flow.fuzzer_new import Fuzzer


class FuzzerTest(unittest.TestCase):
  def get_controller_config(self, address='127.0.0.1', port=6633):
    start_cmd = ("./pox.py --verbose --no-cli sts.syncproto.pox_syncer "
                 "--blocking=False openflow.of_01 --address=__address__ "
                 "--port=__port__")
    kill_cmd = ""
    cwd = "pox"
    config = ControllerConfig(start_cmd=start_cmd, kill_cmd=kill_cmd, cwd=cwd,
                              address=address, port=port, cid=port)
    return config

  def get_controller(self, address='127.0.0.1', port=6633):
    config = self.get_controller_config(address, port)
    ctrl = POXController(controller_config=config)
    return ctrl

  def test_sever_network_links(self):
    # Arrange
    topology = MeshTopology(None, 2)
    params = FuzzerParams()
    fuzzer = Fuzzer(topology, params)
    # Act
    params.link_failure_rate = 1
    events1 = fuzzer.sever_network_links()
    params.link_failure_rate = 0
    events2 = fuzzer.sever_network_links()
    # Assert
    self.assertEquals(len(events1), 1)
    self.assertIsInstance(events1[0], LinkFailure)
    self.assertEquals(len(events2), 0)

  def test_repair_network_links(self):
    # Arrange
    topology = MeshTopology(None, 2)
    params = FuzzerParams()
    fuzzer = Fuzzer(topology, params)
    for link in topology.patch_panel.live_network_links:
      topology.patch_panel.sever_network_link(link)
    # Act
    params.link_recovery_rate = 1
    events1 = fuzzer.repair_network_links()
    params.link_recovery_rate = 0
    events2 = fuzzer.repair_network_links()
    # Assert
    self.assertEquals(len(events1), 1)
    self.assertIsInstance(events1[0], LinkRecovery)
    self.assertEquals(len(events2), 0)

  def test_crash_switches(self):
    # Arrange
    topology = MeshTopology(None, 2)
    params = FuzzerParams()
    fuzzer = Fuzzer(topology, params)
    # Act
    params.switch_failure_rate = 1
    events1 = fuzzer.crash_switches()
    params.switch_failure_rate = 0
    events2 = fuzzer.crash_switches()
    # Assert
    self.assertEquals(len(events1), 2)
    self.assertIsInstance(events1[0], SwitchFailure)
    self.assertEquals(len(events2), 0)

  def test_recover_switches(self):
    # Arrange
    topology = MeshTopology(None, 2)
    params = FuzzerParams()
    fuzzer = Fuzzer(topology, params)
    for switch in list(topology.switches_manager.live_switches):
      topology.switches_manager.crash_switch(switch)
    # Act
    params.switch_recovery_rate = 1
    events1 = fuzzer.recover_switches()
    params.switch_recovery_rate = 0
    events2 = fuzzer.recover_switches()
    # Assert
    self.assertEquals(len(events1), 2)
    self.assertIsInstance(events1[0], SwitchRecovery)
    self.assertIsInstance(events1[1], SwitchRecovery)
    self.assertEquals(len(events2), 0)

  def test_crash_controllers(self):
    # Arrange
    topology = MeshTopology(None, 2)
    c1 = self.get_controller(port=6633)
    c1.start()
    c2 = self.get_controller(port=6644)
    topology.add_controller(c1)
    topology.add_controller(c2)
    params = FuzzerParams()
    fuzzer = Fuzzer(topology, params)
    # Act
    params.controller_crash_rate = 1
    events1 = fuzzer.crash_controllers()
    params.controller_crash_rate = 0
    events2 = fuzzer.crash_controllers()
    # Assert
    self.assertEquals(len(events1), 1)
    self.assertIsInstance(events1[0], ControllerFailure)
    self.assertEquals(events1[0].controller_id, c1.cid)
    self.assertEquals(len(events2), 0)

  def test_recover_controllers(self):
    # Arrange
    topology = MeshTopology(None, 2)
    c1 = self.get_controller(port=6633)
    c1.start()
    c2 = self.get_controller(port=6644)
    topology.add_controller(c1)
    topology.add_controller(c2)
    params = FuzzerParams()
    fuzzer = Fuzzer(topology, params)
    # Act
    params.controller_recovery_rate = 1
    events1 = fuzzer.recover_controllers()
    params.controller_recovery_rate = 0
    events2 = fuzzer.recover_controllers()
    # Assert
    self.assertEquals(len(events1), 1)
    self.assertIsInstance(events1[0], ControllerRecovery)
    self.assertEquals(events1[0].controller_id, c2.cid)
    self.assertEquals(len(events2), 0)

  def test_fuzz_traffic(self):
    # Arrange
    topology = MeshTopology(None, 2)
    params = FuzzerParams()
    fuzzer = Fuzzer(topology, params)
    # Act
    params.traffic_generation_rate = 1
    events1 = fuzzer.fuzz_traffic()
    params.traffic_generation_rate = 0
    events2 = fuzzer.fuzz_traffic()
    # Assert
    self.assertEquals(len(events1), 2)
    self.assertIsInstance(events1[0], TrafficInjection)
    self.assertEquals(len(events2), 0)
