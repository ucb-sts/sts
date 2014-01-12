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

sys.path.append(os.path.dirname(__file__) + "/../../..")

from config.experiment_config_lib import ControllerConfig
from sts.topology import MeshTopology
from sts.simulation_state import SimulationConfig
from sts.control_flow import RecordingSyncCallback

class OpenflowBufferTest(unittest.TestCase):
  def basic_test(self):
    start_cmd = ('''./pox.py --verbose '''
                 '''openflow.discovery forwarding.l2_multi '''
                 '''sts.util.socket_mux.pox_monkeypatcher '''
                 '''openflow.of_01 --address=__address__ --port=__port__''')

    controllers = [ControllerConfig(start_cmd, cwd="pox")]
    topology_class = MeshTopology
    topology_params = "num_switches=2"

    simulation_config = SimulationConfig(controller_configs=controllers,
                                         topology_class=topology_class,
                                         topology_params=topology_params,
                                         multiplex_sockets=True)
    simulation = simulation_config.bootstrap(RecordingSyncCallback(None))
    simulation.set_pass_through()
    simulation.connect_to_controllers()
    time.sleep(1)
    observed_events = simulation.unset_pass_through()
    print "Observed events: %s" % str(observed_events)
    self.assertTrue(observed_events != [])

if __name__ == '__main__':
  unittest.main()
