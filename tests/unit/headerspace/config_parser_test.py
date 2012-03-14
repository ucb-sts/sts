#!/usr/bin/env python

import unittest
import sys
import os.path
import itertools
from copy import copy
import types

sys.path.append(os.path.dirname(__file__) + "/../../..")

from debugger.topology_generator import *
from pox.openflow.switch_impl import SwitchImpl
from pox.openflow.libopenflow_01 import *
from headerspace.config_parser.openflow_parser import generate_transfer_function, HS_FORMAT
from headerspace.headerspace.tf import *

class config_parser_test(unittest.TestCase):
  def test_basic(self):
    tf = TF(HS_FORMAT()["length"]*2)
    switch = create_switch(1, 2)
    flow_mod = ofp_flow_mod(xid=124, priority=1, match=ofp_match(in_port=1, nw_src="1.2.3.4"), action=ofp_action_output(port=2))
    switch.table.process_flow_mod(flow_mod)
    generate_transfer_function(tf, switch)
    print "tf: %s" % str(tf)
    # TODO: verify correct match
  
  def test_drop(self):
    tf = TF(HS_FORMAT()["length"]*2)
    switch = create_switch(1, 2)
    # Don't give it an action
    flow_mod = ofp_flow_mod(xid=124, priority=1, match=ofp_match(in_port=1, nw_src="1.2.3.4"))
    switch.table.process_flow_mod(flow_mod)
    generate_transfer_function(tf, switch)
    print "tf: %s" % str(tf)
    
if __name__ == '__main__':
  unittest.main()
