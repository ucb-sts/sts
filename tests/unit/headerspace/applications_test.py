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
import os.path
import itertools
from copy import copy
import types

sys.path.append(os.path.dirname(__file__) + "/../../..")

from sts.topology import *
from pox.openflow.software_switch import SoftwareSwitch
from pox.openflow.libopenflow_01 import *
from sts.invariant_checker import InvariantChecker

submodule_loaded = True
try:
  import topology_loader.topology_loader as hsa_topo
  import headerspace.applications as hsa
except ImportError:
  import traceback
  traceback.print_exc()
  submodule_loaded = False

class MockAccessLink(object):
  def __init__(self, switch, switch_port):
    self.switch = switch
    self.switch_port = switch_port

class applications_test(unittest.TestCase):
  def _create_loopy_network(self, cut_loop=False):
    # by default OpenFlow ignores rules that outputs packets over the same
    # port they came in on, so we need to create a 3-switch topology.
    switch1 = create_switch(1, 2)
    if not cut_loop:
      flow_mod1 = ofp_flow_mod(match=ofp_match(in_port=2, nw_src="1.2.3.4"), action=ofp_action_output(port=1))
      switch1.table.process_flow_mod(flow_mod1)
    flow_mod1_in = ofp_flow_mod(match=ofp_match(in_port=3, nw_src="1.2.3.4"), action=ofp_action_output(port=1))
    switch1.table.process_flow_mod(flow_mod1_in)
    switch2 = create_switch(2, 2)
    flow_mod2 = ofp_flow_mod(match=ofp_match(in_port=1, nw_src="1.2.3.4"), action=ofp_action_output(port=2))
    flow_mod2_in = ofp_flow_mod(match=ofp_match(in_port=3, nw_src="1.2.3.4"), action=ofp_action_output(port=2))
    switch2.table.process_flow_mod(flow_mod2)
    switch2.table.process_flow_mod(flow_mod2_in)
    switch3 = create_switch(3, 2)
    flow_mod3 = ofp_flow_mod(match=ofp_match(in_port=2, nw_src="1.2.3.4"), action=ofp_action_output(port=1))
    flow_mod3_in = ofp_flow_mod(match=ofp_match(in_port=3, nw_src="1.2.3.4"), action=ofp_action_output(port=1))
    switch3.table.process_flow_mod(flow_mod3)
    switch3.table.process_flow_mod(flow_mod3_in)
    switches = [switch1, switch2, switch3]
    network_links = [Link(switch1, switch1.ports[1], switch2, switch2.ports[1]),
                     Link(switch2, switch2.ports[2], switch3, switch3.ports[2]),
                     Link(switch3, switch3.ports[1], switch1, switch1.ports[2])]
    return (switches, network_links)

  def test_python_loop(self):
    (switches, network_links) = self._create_loopy_network()
    NTF = hsa_topo.generate_NTF(switches)
    TTF = hsa_topo.generate_TTF(network_links)
    loops = hsa.detect_loop(NTF, TTF, switches)
    self.assertTrue(loops != [])

  def test_hassel_c_loop(self):
    (switches, network_links) = self._create_loopy_network()
    (name_tf_pairs, TTF) = InvariantChecker._get_transfer_functions(switches, network_links)
    access_links =  [ MockAccessLink(sw, sw.ports[2]) for sw in switches ]
    loops = hsa.check_loops_hassel_c(name_tf_pairs, TTF, access_links)
    self.assertTrue(loops != [])

  def test_hassel_c_no_loop(self):
    (switches, network_links) = self._create_loopy_network(cut_loop=True)
    (name_tf_pairs, TTF) = InvariantChecker._get_transfer_functions(switches, network_links)
    access_links = [ MockAccessLink(sw, sw.ports[2]) for sw in switches ]
    loops = hsa.check_loops_hassel_c(name_tf_pairs, TTF, access_links)
    self.assertTrue(loops == [])

  def test_blackhole(self):
    switch1 = create_switch(1, 2)
    flow_mod = ofp_flow_mod(xid=124, priority=1, match=ofp_match(in_port=1, nw_src="1.2.3.4"), action=ofp_action_output(port=2))
    switch1.table.process_flow_mod(flow_mod)
    switch2 = create_switch(2, 2)
    network_links = [Link(switch1, switch1.ports[2], switch2, switch2.ports[2]),
                     Link(switch2, switch2.ports[2], switch1, switch1.ports[2])]
    switches = [switch1, switch2]
    NTF = hsa_topo.generate_NTF(switches)
    TTF = hsa_topo.generate_TTF(network_links)
    access_links = [ MockAccessLink(sw, sw.ports[1]) for sw in switches ]
    blackholes = hsa.find_blackholes(NTF, TTF, access_links)
    self.assertEqual([(100002, [100001, 100002])], blackholes)

  def test_no_blackhole(self):
    switch1 = create_switch(1, 2)
    flow_mod = ofp_flow_mod(xid=124, priority=1, match=ofp_match(in_port=1, nw_src="1.2.3.4"), action=ofp_action_output(port=2))
    switch1.table.process_flow_mod(flow_mod)
    switch2 = create_switch(2, 2)
    flow_mod = ofp_flow_mod(xid=124, priority=1, match=ofp_match(in_port=2, nw_src="1.2.3.4"), action=ofp_action_output(port=1))
    switch2.table.process_flow_mod(flow_mod)
    network_links = [Link(switch1, switch1.ports[2], switch2, switch2.ports[2]),
                     Link(switch2, switch2.ports[2], switch1, switch1.ports[2])]
    NTF = hsa_topo.generate_NTF([switch1, switch2])
    TTF = hsa_topo.generate_TTF(network_links)
    access_links = [MockAccessLink(switch1, switch1.ports[1]),
                    MockAccessLink(switch2, switch2.ports[1])]
    blackholes = hsa.find_blackholes(NTF, TTF, access_links)
    self.assertEqual([], blackholes)

if __name__ == '__main__':
  if submodule_loaded:
    unittest.main()
