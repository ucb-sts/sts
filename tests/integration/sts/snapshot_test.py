#!/usr/bin/env python
#
# Copyright 2011-2013 Colin Scott
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
import sys
import os
import time

from config.experiment_config_lib import ControllerConfig
from sts.topology import MeshTopology
from sts.simulation_state import SimulationConfig
from sts.control_flow import RecordingSyncCallback
from sts.control_flow.snapshot_utils import Snapshotter
from sts.entities import SnapshotPopen
from sts.util.convenience import IPAddressSpace
from sts.util.procutils import kill_procs

sys.path.append(os.path.dirname(__file__) + "/../../..")

class SnapshotTest(unittest.TestCase):
  def basic_test(self):
    simulation = None
    try:
      start_cmd = ('''./pox.py --verbose '''
                   '''openflow.discovery forwarding.l2_multi '''
                   '''sts.util.socket_mux.pox_monkeypatcher --snapshot_address=../snapshot_socket '''
                   '''openflow.of_01 --address=__address__ --port=__port__''')

      IPAddressSpace._claimed_addresses.clear()
      ControllerConfig._controller_labels.clear()
      controllers = [ControllerConfig(start_cmd, cwd="pox", snapshot_address="./snapshot_socket")]
      topology_class = MeshTopology
      topology_params = "num_switches=2"

      simulation_config = SimulationConfig(controller_configs=controllers,
                                           topology_class=topology_class,
                                           topology_params=topology_params,
                                           multiplex_sockets=True)
      simulation = simulation_config.bootstrap(RecordingSyncCallback(None))
      simulation.connect_to_controllers()

      c1 = simulation.controller_manager.controllers[0]
      c1_pid = c1.pid

      snapshotter = Snapshotter(simulation, c1)
      snapshotter.snapshot_controller()
      time.sleep(1)
      kill_procs([c1.process])
      snapshotter.snapshot_proceed()

      self.assertEqual(1, len(simulation.controller_manager.controllers))
      c2 = simulation.controller_manager.controllers[0]
      c2_pid = c2.pid
      self.assertTrue(c1_pid != c2_pid)
      # Controller object itself should not have changed
      self.assertTrue(c1 == c2)

      # snapshotting should work multiple times
      snapshotter = Snapshotter(simulation, c2)
      snapshotter.snapshot_controller()
      time.sleep(1)
      kill_procs([c2.process])
      snapshotter.snapshot_proceed()

      self.assertEqual(1, len(simulation.controller_manager.controllers))
      c3 = simulation.controller_manager.controllers[0]
      self.assertTrue(c2_pid != c3.pid)
    finally:
      if simulation is not None:
        simulation.clean_up()

if __name__ == '__main__':
  unittest.main()
