#!/usr/bin/env python

import unittest
import sys
import os
import itertools
from copy import copy
import types
import tempfile

from sts.control_flow import Replayer
from sts.topology import FatTree, BufferedPatchPanel
from sts.simulation import Simulation
from pox.lib.recoco.recoco import Scheduler

sys.path.append(os.path.dirname(__file__) + "/../../..")

class ReplayerTest(unittest.TestCase):
  tmpsuperlog = '/tmp/superlog.tmp'

  def write_simple_superlog(self):
    ''' Returns the file. Make sure to close afterwards! '''
    superlog = open(self.tmpsuperlog, 'w')
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

  def setup_simulation(self):
    controllers = []
    topology_class = FatTree
    topology_params = ""
    patch_panel_class = BufferedPatchPanel
    scheduler = Scheduler(daemon=True, useEpoll=False)
    return Simulation(scheduler, controllers, topology_class, topology_params, patch_panel_class)

  def test_basic(self):
    try:
      self.write_simple_superlog()
      replayer = Replayer(self.tmpsuperlog)
      simulation = self.setup_simulation()
      replayer.simulate(simulation)
    finally:
      os.unlink(self.tmpsuperlog)

if __name__ == '__main__':
  unittest.main()
