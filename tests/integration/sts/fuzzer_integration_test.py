#!/usr/bin/env python

import unittest
import sys
import os
import itertools
from copy import copy
import types
import tempfile

sys.path.append(os.path.dirname(__file__) + "/../../..")

simple_cfg = '''
from experiment_config_lib import ControllerConfig
from sts.topology import *
from sts.control_flow import Fuzzer
from sts.simulation_state import SimulationConfig

# Use POX as our controller
command_line = "./pox/pox.py --no-cli openflow.of_01 --address=__address__ --port=__port__"
controllers = [ControllerConfig(command_line)]

topology_class = MeshTopology
topology_params = "num_switches=4"
simulation_config = SimulationConfig(controller_configs=controllers,
                                     topology_class=topology_class,
                                     topology_params=topology_params)

control_flow = Fuzzer(simulation_config, steps=10, fuzzer_params='config.fuzzer_simple_test_params')
'''

params = '''
switch_failure_rate = 0.5
switch_recovery_rate = 0.5
dataplane_drop_rate = 0.5
dataplane_delay_rate = 0.5
controlplane_block_rate = 0.5
controlplane_unblock_rate = 0.5
ofp_message_receipt_rate = 0.5
link_failure_rate = 0.5
link_recovery_rate = 0.5
controller_crash_rate = 0.1
controller_recovery_rate = 0.5
traffic_generation_rate = 0.5
host_migration_rate = 0.5
'''

class FuzzerTest(unittest.TestCase):
  tmpcfg = 'config/fuzzer_simple_test.py'
  tmpparamsfile = 'config/fuzzer_simple_test_params.py'
  tmpcfgpyc = 'config/fuzzer_simple_test.pyc'
  tmpcfgmodule = 'config.fuzzer_simple_test'

  def write_simple_cfg(self):
    cfg = open(self.tmpcfg, 'w')
    cfg.write(simple_cfg)
    cfg.close()

  def write_params(self):
    output = open(self.tmpparamsfile, 'w')
    output.write(params)
    output.close()

  def basic_test(self):
    try:
      self.write_simple_cfg()
      self.write_params()
      ret = os.system("./simulator.py -c %s" % self.tmpcfgmodule)
      self.assertEqual(0, ret)
    finally:
      os.unlink(self.tmpcfg)
      os.unlink(self.tmpparamsfile)
      if os.path.exists(self.tmpcfgpyc):
        os.unlink(self.tmpcfgpyc)

if __name__ == '__main__':
  unittest.main()
