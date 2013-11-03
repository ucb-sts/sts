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

sys.path.append(os.path.dirname(__file__) + "/../../..")

# N.B. this import is needed to avoid a circular dependency.
from sts.replay_event import *
from sts.openflow_buffer import OpenFlowBuffer, PendingReceive
from pox.openflow.libopenflow_01 import *

class MockConnection(object):
  def __init__(self):
    self.passed_message = False

  def allow_message_receipt(self, message):
    self.passed_message = True

class GodSchedulerTest(unittest.TestCase):
  def test_basic(self):
    god = OpenFlowBuffer()
    message = ofp_flow_mod(match=ofp_match(in_port=1, nw_src="1.1.1.1"),
                           action=ofp_action_output(port=1))
    mock_conn = MockConnection()
    god.insert_pending_receipt(1,"c1",message,mock_conn)
    pending_receipt = PendingReceive(1,"c1",OFFingerprint.from_pkt(message))
    self.assertTrue(god.message_receipt_waiting(pending_receipt))
    god.schedule(pending_receipt)
    self.assertTrue(mock_conn.passed_message)
    self.assertFalse(god.message_receipt_waiting(pending_receipt))
