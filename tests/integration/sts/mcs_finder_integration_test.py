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

sys.path.append(os.path.dirname(__file__) + "/../../..")

simple_cfg = '''
from config.experiment_config_lib import ControllerConfig
from sts.control_flow.mcs_finder import MCSFinder
from sts.simulation_state import SimulationConfig

controllers = [ControllerConfig(start_cmd='./pox.py --verbose --no-cli openflow.of_01 --address=__address__ --port=__port__',
                                address='127.0.0.1', port=8888, cwd='pox')]
simulation_config = SimulationConfig(controller_configs=controllers)

control_flow = MCSFinder(simulation_config, "%s",
                         invariant_check_name="InvariantChecker.check_liveness")
'''

class ReplayerTest(unittest.TestCase):
  tmpsuperlog = '/tmp/superlog.tmp'
  tmpcfg = 'config/mcs_simple_test.py'
  tmpcfgpyc = 'config/mcs_simple_test.pyc'
  tmpcfgmodule = 'config.mcs_simple_test'

  def write_simple_superlog(self):
    ''' Returns the file. Make sure to close afterwards! '''
    # MCS is {e2}, a single controller failure event
    superlog = open(self.tmpsuperlog, 'w')
    e1 = str('''{"dependent_labels": [], "start_dpid": 8, "class": "LinkFailure",'''
             ''' "start_port_no": 3, "end_dpid": 15, "end_port_no": 2, "label": "e1", "time": [0,0], "round": 0}''')
    superlog.write(e1 + '\n')
    e2 = str('''{"dependent_labels": [], "class": "ControllerFailure",'''
             '''  "controller_id": "c1",  "label": "e2", "time": [0,0], "round": 0}''')
    superlog.write(e2 + '\n')
    e3 = str('''{"dependent_labels": [], "class": "InvariantViolation",'''
            '''  "violations": ["c1"], "persistent": true, "time": [0,0], "label": "e3"}''')
    superlog.write(e3 + '\n')
    superlog.close()

  def write_simple_cfg(self):
    cfg = open(self.tmpcfg, 'w')
    cfg.write(simple_cfg % self.tmpsuperlog)
    cfg.close()

  def basic_test(self):
    try:
      self.write_simple_superlog()
      self.write_simple_cfg()
      ret = os.system("./simulator.py -c %s" % self.tmpcfgmodule)
      self.assertEqual(0, ret)
    finally:
      os.unlink(self.tmpsuperlog)
      os.unlink(self.tmpcfg)
      if os.path.exists(self.tmpcfgpyc):
        os.unlink(self.tmpcfgpyc)

if __name__ == '__main__':
  unittest.main()
