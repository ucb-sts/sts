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

import sts.input_traces.log_parser as log_parser
from sts.replay_event import LinkFailure, LinkRecovery

class superlog_parser_test(unittest.TestCase):
  tmpfile = '/tmp/superlog.tmp'

  def open_simple_superlog(self):
    ''' Returns the file. Make sure to close afterwards! '''
    superlog = open(self.tmpfile, 'w')
    e1 = str('''{"dependent_labels": ["e2"], "start_dpid": 1, "class": "LinkFailure",'''
             ''' "start_port_no": 1, "end_dpid": 2, "end_port_no": 1, "label": "e1", "time": [0,0], "round": 0}''')
    superlog.write(e1 + '\n')
    e2 = str('''{"dependent_labels": [], "start_dpid": 1, "class": "LinkRecovery",'''
             ''' "start_port_no": 1, "end_dpid": 2, "end_port_no": 1, "label": "e2", "time": [0,0], "round": 0}''')
    superlog.write(e2 + '\n')
    superlog.close()

  def test_basic(self):
    name = None
    try:
      self.open_simple_superlog()
      events = log_parser.parse_path(self.tmpfile)
      self.assertEqual(2, len(events))
      self.assertEqual(LinkFailure,type(events[0]))
      self.assertEqual(LinkRecovery,type(events[1]))
    finally:
      if name is not None:
        os.unlink(name)

if __name__ == '__main__':
  unittest.main()
