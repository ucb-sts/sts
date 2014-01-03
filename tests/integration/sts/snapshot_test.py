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
from sts.control_flow.snapshot_utils import snapshot_controller, snapshot_proceed
from sts.entities import SnapshotPopen

sys.path.append(os.path.dirname(__file__) + "/../../..")

psutil_installed = True
try:
  import psutil
except ImportError:
  psutil_installed = False

# TODO(cs): double check that psutil is loaded

class SnapshotTest(unittest.TestCase):
  def _check_controller_dead(self, pid):
    if not psutil_installed:
      return
    try:
      self.assertTrue(SnapshotPopen(pid).poll() is not None)
    except psutil.NoSuchProcess:
      return

  def basic_test(self):
    start_cmd = ('''./pox.py --verbose '''
                 '''openflow.discovery forwarding.l2_multi '''
                 '''sts.util.socket_mux.pox_monkeypatcher --snapshot_address=../snapshot_socket '''
                 '''openflow.of_01 --address=__address__ --port=__port__''')

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

    snapshot_controller(simulation, c1)
    time.sleep(1)
    snapshot_proceed(simulation, c1)

    self.assertEqual(1, len(simulation.controller_manager.controllers))
    c2 = simulation.controller_manager.controllers[0]
    c2_pid = c2.pid
    self.assertTrue(c1_pid != c2_pid)
    # Controller object itself should not have changed
    self.assertTrue(c1 == c2)

    # Old controller should be dead
    self._check_controller_dead(c1_pid)

    # snapshotting should work multiple times
    snapshot_controller(simulation, c2)
    time.sleep(1)
    snapshot_proceed(simulation, c2)

    self.assertEqual(1, len(simulation.controller_manager.controllers))
    c3 = simulation.controller_manager.controllers[0]
    self.assertTrue(c2_pid != c3.pid)
    self._check_controller_dead(c2_pid)


if __name__ == '__main__':
  unittest.main()
