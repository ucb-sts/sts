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
from sts.openflow_buffer import *
from sts.util.ordered_default_dict import OrderedDefaultDict
from pox.openflow.libopenflow_01 import *


class MockConnection(object):
  def __init__(self, is_send=False):
    self.is_send = is_send
    self.passed_message = False

  def allow_message_send(self, message):
    if not self.is_send:
      raise Exception("Not in send")
    self.passed_message = True

  def allow_message_receipt(self, message):
    if self.is_send:
      raise Exception("Not in receive")
    self.passed_message = True

class PendingQueueTest(unittest.TestCase):
  def setUp(self):
    self.message = ofp_flow_mod(match=ofp_match(in_port=1, nw_src="1.1.1.1"),
                           action=ofp_action_output(port=1))
    self.message2 = ofp_flow_mod(match=ofp_match(in_port=2, nw_src="1.1.1.1"),
                           action=ofp_action_output(port=1))
    self.mock_conn = MockConnection()
    self.pending_receipt = PendingReceive(1,"c1",OFFingerprint.from_pkt(self.message))
    self.pending_receipt1a = PendingReceive(1,"c1",OFFingerprint.from_pkt(self.message2))
    self.pending_receipt2 = PendingReceive(1,"c2",OFFingerprint.from_pkt(self.message))
    self.conn_message = (self.mock_conn, self.message)
    self.conn_message2 = (self.mock_conn, self.message2)

  def test_insert_pop(self):
    q = PendingQueue()
    self.assertEquals(0, len(q))
    q.insert(self.pending_receipt, self.conn_message)
    self.assertEquals(1, len(q))
    q.insert(self.pending_receipt, self.conn_message2)
    self.assertEquals(2, len(q))
    self.assertEquals(self.conn_message, q.pop_by_message_id(self.pending_receipt))
    self.assertEquals(1, len(q))
    self.assertEquals(self.conn_message2, q.pop_by_message_id(self.pending_receipt))
    self.assertEquals(0, len(q))

  def test_insert_get(self):
    q = PendingQueue()
    q.insert(self.pending_receipt, self.conn_message)
    q.insert(self.pending_receipt, self.conn_message)
    q.insert(self.pending_receipt1a, self.conn_message2)
    q.insert(self.pending_receipt2, self.conn_message2)
    self.assertEquals([self.conn_message, self.conn_message], q.get_all_by_message_id(self.pending_receipt))
    self.assertEquals([self.conn_message2], q.get_all_by_message_id(self.pending_receipt1a))
    self.assertEquals([self.conn_message2], q.get_all_by_message_id(self.pending_receipt2))

    # should return pending_receipts in order
    self.assertEquals([self.pending_receipt, self.pending_receipt1a],
            q.get_message_ids(1, "c1"))

    self.assertEquals([self.pending_receipt2],
            q.get_message_ids(1, "c2"))

class OpenFlowBufferTest(unittest.TestCase):
  def test_receive(self):
    buf = OpenFlowBuffer()
    message = ofp_flow_mod(match=ofp_match(in_port=1, nw_src="1.1.1.1"),
                           action=ofp_action_output(port=1))
    mock_conn = MockConnection(is_send=False)
    buf.insert_pending_receipt(1,"c1",message,mock_conn)
    pending_receipt = PendingReceive(1,"c1",OFFingerprint.from_pkt(message))
    self.assertTrue(buf.message_receipt_waiting(pending_receipt))
    self.assertEquals([pending_receipt], buf.pending_receives.get_message_ids(1, "c1"))
    buf.schedule(pending_receipt)
    self.assertTrue(mock_conn.passed_message)
    self.assertFalse(buf.message_receipt_waiting(pending_receipt))

  def test_send(self):
    buf = OpenFlowBuffer()
    message = ofp_flow_mod(match=ofp_match(in_port=1, nw_src="1.1.1.1"),
                           action=ofp_action_output(port=1))
    mock_conn = MockConnection(is_send=True)
    buf.insert_pending_send(1,"c1",message,mock_conn)
    pending_send = PendingSend(1,"c1",OFFingerprint.from_pkt(message))
    self.assertTrue(buf.message_send_waiting(pending_send))
    self.assertEquals([pending_send], buf.pending_sends.get_message_ids(1, "c1"))
    buf.schedule(pending_send)
    self.assertTrue(mock_conn.passed_message)
    self.assertFalse(buf.message_receipt_waiting(pending_send))
