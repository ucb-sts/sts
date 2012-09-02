#!/usr/bin/env python

import unittest
import sys
import os
import itertools
from copy import copy
import types
import tempfile

sys.path.append(os.path.dirname(__file__) + "/../../..")

import log_processing.superlog_parser as superlog_parser
from sts.event import LinkFailure, LinkRecovery

class superlog_parser_test(unittest.TestCase):
  tmpfile = '/tmp/superlog.tmp'

  def open_simple_superlog(self):
    ''' Returns the file. Make sure to close afterwards! '''
    superlog = open(self.tmpfile, 'w')
    e1 = str('''{"dependent_labels": ["e2"], "start_dpid": 1, "class": "LinkFailure",'''
             ''' "start_port_no": 1, "end_dpid": 2, "end_port_no": 1, "label": "e1"}''')
    superlog.write(e1 + '\n')
    e2 = str('''{"dependent_labels": [], "start_dpid": 1, "class": "LinkRecovery",'''
             ''' "start_port_no": 1, "end_dpid": 2, "end_port_no": 1, "label": "e2"}''')
    superlog.write(e2 + '\n')
    superlog.close()

  def test_basic(self):
    name = None
    try:
      self.open_simple_superlog()
      events = superlog_parser.parse_path(self.tmpfile)
      self.assertEqual(2, len(events))
      self.assertEqual(LinkFailure,type(events[0]))
      self.assertEqual(LinkRecovery,type(events[1]))
    finally:
      if name is not None:
        os.unlink(name)

if __name__ == '__main__':
  unittest.main()
