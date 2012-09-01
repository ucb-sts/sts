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
from experiment_config_lib import *
from sts.topology import FatTree, BufferedPatchPanel
from sts.control_flow import Fuzzer

# Don't use a controller
controllers = []
topology = FatTree()
patch_panel = BufferedPatchPanel
control_flow = Replayer(%s)
dataplane_trace = None
'''

class ReplayerTest(unittest.TestCase):
  def open_simple_superlog(self):
    ''' Returns the file. Make sure to close afterwards! '''
    superlog = tempfile.NamedTemporaryFile()
    e1 = '{"dependent_labels": [], "dpid": 1, "class": "LinkFailure", "port_no": 1, "label": "e1"}'
    superlog.write(e1 + '\n')
    e2 = '{"dependent_labels": [], "dpid": 1, "class": "LinkRecovery", "port_no": 1, "label": "e2"}'
    superlog.write(e1 + '\n')
    return superlog

  def open_simple_cfg(self):
    ''' Returns the file. Make sure to close afterwards! '''
    cfg = tempfile.NamedTemporaryFile()
    cfg.write(simple_cfg)
    return cfg

  def test_basic(self):
    superlog = self.open_simple_superlog()
    cfg = self.open_simple_cfg()
    superlog.close()
    cfg.close()

if __name__ == '__main__':
  unittest.main()
