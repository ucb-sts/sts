#!/usr/bin/env python
#
# Copyright 2011-2013 Colin Scott
# Copyright 2011-2013 Andreas Wundsam
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

sys.path.append(os.path.dirname(__file__) + "/../../..")

from sts.topology import *
from pox.openflow.libopenflow_01 import *

submodule_loaded = True
try:
  from config_parser.openflow_parser import generate_transfer_function, HS_FORMAT
  from headerspace.tf import *
except ImportError:
  import traceback
  traceback.print_exc()
  submodule_loaded = False

class config_parser_test(unittest.TestCase):
  def test_basic(self):
    tf = TF(HS_FORMAT())
    switch = create_switch(1, 2)
    flow_mod = ofp_flow_mod(xid=124, priority=1, match=ofp_match(in_port=1, nw_src="1.2.3.4"), action=ofp_action_output(port=2))
    switch.table.process_flow_mod(flow_mod)
    generate_transfer_function(tf, switch)
    print "tf: %s" % str(tf)
    # TODO: do something smarter than printing to console...

  def test_drop(self):
    tf = TF(HS_FORMAT())
    switch = create_switch(1, 2)
    # Don't give it an action
    flow_mod = ofp_flow_mod(xid=124, priority=1, match=ofp_match(in_port=1, nw_src="1.2.3.4"))
    switch.table.process_flow_mod(flow_mod)
    generate_transfer_function(tf, switch)
    print "tf: %s" % str(tf)
    # TODO: do something smarter than printing to console...

  def test_ip_display(self):
    tf = TF(HS_FORMAT())
    flow_mod = ofp_flow_mod(xid=124, priority=1, match=ofp_match(in_port=1, nw_dst="254.0.0.0/8"), action=ofp_action_output(port=2))
    switch = create_switch(1, 2)
    switch.table.process_flow_mod(flow_mod)
    generate_transfer_function(tf, switch)
    print "tf: %s" % str(tf)

  def test_field_display(self):
    tf = TF(HS_FORMAT())
    flow_mod = ofp_flow_mod(xid=124, priority=1, match=ofp_match(nw_tos=6), action=ofp_action_output(port=2))
    switch = create_switch(1, 2)
    switch.table.process_flow_mod(flow_mod)
    generate_transfer_function(tf, switch)
    print "tf: %s" % str(tf)

  def test_eth_display(self):
    tf = TF(HS_FORMAT())
    print "int value is: ", EthAddr("00:00:11:22:33:00").toInt()
    print "string is:", str(EthAddr("00:00:11:22:33:00"))
    flow_mod = ofp_flow_mod(xid=124, priority=1, match=ofp_match(dl_src="00:00:11:22:33:00"), action=ofp_action_output(port=2))
    switch = create_switch(1, 2)
    switch.table.process_flow_mod(flow_mod)
    generate_transfer_function(tf, switch)
    print "tf: %s" % str(tf)

if __name__ == '__main__':
  if submodule_loaded:
    unittest.main()
