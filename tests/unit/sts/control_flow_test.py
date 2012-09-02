#!/usr/bin/env python

import unittest
import sys
import os
import itertools
from copy import copy
import types
import tempfile

from config.experiment_config_lib import ControllerConfig
from sts.control_flow import Replayer
from sts.topology import FatTree, PatchPanel
from sts.simulation import Simulation
from pox.lib.recoco.recoco import Scheduler

sys.path.append(os.path.dirname(__file__) + "/../../..")

class ReplayerTest(unittest.TestCase):
  tmp_basic_superlog = '/tmp/superlog_basic.tmp'
  tmp_controller_superlog = '/tmp/superlog_controller.tmp'

  # ------------------------------------------ #
  #        Basic Test                          #
  # ------------------------------------------ #

  def write_simple_superlog(self):
    ''' Make sure to delete afterwards! '''
    superlog = open(self.tmp_basic_superlog, 'w')
    e1 = str('''{"dependent_labels": ["e2"], "start_dpid": 8, "class": "LinkFailure",'''
             ''' "start_port_no": 3, "end_dpid": 15, "end_port_no": 2, "label": "e1"}''')
    superlog.write(e1 + '\n')
    e2 = str('''{"dependent_labels": [], "start_dpid": 8, "class": "LinkRecovery",'''
             ''' "start_port_no": 3, "end_dpid": 15, "end_port_no": 2, "label": "e2"}''')
    superlog.write(e2 + '\n')
    e3 = str('''{"dependent_labels": ["e4"], "dpid": 8, "class": "SwitchFailure",'''
             ''' "label": "e3"}''')
    superlog.write(e3 + '\n')
    e4 = str('''{"dependent_labels": [], "dpid": 8, "class": "SwitchRecovery",'''
             ''' "label": "e4"}''')
    superlog.write(e4 + '\n')
    superlog.close()

  def setup_simple_simulation(self):
    controllers = []
    topology_class = FatTree
    topology_params = ""
    patch_panel_class = PatchPanel
    scheduler = Scheduler(daemon=True, useEpoll=False)
    return Simulation(scheduler, controllers, topology_class, topology_params, patch_panel_class)

  def test_basic(self):
    try:
      self.write_simple_superlog()
      replayer = Replayer(self.tmp_basic_superlog)
      simulation = self.setup_simple_simulation()
      replayer.simulate(simulation)
    finally:
      os.unlink(self.tmp_basic_superlog)

  # ------------------------------------------ #
  #        Controller Crash Test               #
  # ------------------------------------------ #

  def write_controller_crash_superlog(self):
    superlog = open(self.tmp_controller_superlog, 'w')
    e1 = str('''{"dependent_labels": ["e2"], "uuid": ["127.0.0.1", 8899],'''
             ''' "class": "ControllerFailure", "label": "e1"}''')
    superlog.write(e1 + '\n')
    e2 = str('''{"dependent_labels": [], "uuid": ["127.0.0.1", 8899],'''
             ''' "class": "ControllerRecovery", "label": "e2"}''')
    superlog.write(e2 + '\n')
    superlog.close()

  def setup_controller_simulation(self):
    cmdline = "./pox/pox.py --no-cli openflow.of_01 --address=__address__ --port=__port__"
    controllers = [ControllerConfig(cmdline=cmdline, address="127.0.0.1", port=8899)]
    topology_class = FatTree
    topology_params = ""
    patch_panel_class = PatchPanel
    scheduler = Scheduler(daemon=True, useEpoll=False)
    return Simulation(scheduler, controllers, topology_class, topology_params, patch_panel_class)

  def test_controller_crash(self):
    try:
      self.write_controller_crash_superlog()
      replayer = Replayer(self.tmp_controller_superlog)
      simulation = self.setup_controller_simulation()
      replayer.simulate(simulation)
    finally:
      os.unlink(self.tmp_controller_superlog)

if __name__ == '__main__':
  unittest.main()
