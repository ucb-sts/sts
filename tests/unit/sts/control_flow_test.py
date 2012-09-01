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
    superlog.close()

  def setup_simulation(self):
    controllers = []
    topology = FatTree()
    patch_panel_class = BufferedPatchPanel
    return Simulation(controllers, topology, patch_panel_class)

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
