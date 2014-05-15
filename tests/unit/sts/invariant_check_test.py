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
import os.path
from sts.topology import *
from pox.openflow.software_switch import SoftwareSwitch

sys.path.append(os.path.dirname(__file__) + "/../../..")

from sts.topology import *
from pox.openflow.software_switch import SoftwareSwitch
from pox.openflow.libopenflow_01 import *
from config.invariant_checks import check_for_two_loop

class MockSimulation(object):
  def __init__(self, topology):
    self.topology = topology

class InvariantCheckTest(unittest.TestCase):
  def basic_test(self):
    topo = MeshTopology(num_switches=2)
    message = ofp_flow_mod(match=ofp_match(in_port=1, nw_src="1.1.1.1"),
                           action=ofp_action_output(port=1))
    topo.switches[1].table.process_flow_mod(message)
    simulation = MockSimulation(topo)
    violations = check_for_two_loop(simulation)
    self.assertNotEqual(violations, [])

  def test_no_loop(self):
    topo = MeshTopology(num_switches=2)
    simulation = MockSimulation(topo)
    violations = check_for_two_loop(simulation)
    self.assertEqual(violations, [])
