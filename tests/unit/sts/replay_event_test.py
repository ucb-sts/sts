#!/usr/bin/env python

import unittest
import sys
import os.path
import itertools
from copy import copy
import types

sys.path.append(os.path.dirname(__file__) + "/../../..")

from sts.replay_event import *

class MockEvent(Event):
  def proceed(self, simulation):
    pass

class event_dag_test(unittest.TestCase):
  def test_split_basic(self):
    events = [MockEvent(), MockEvent(), MockEvent(), MockEvent()]
    dag = EventDag(events)
    splits = dag.split_inputs(2)
    self.assertEqual(2, len(splits))
    self.assertEqual(2, len(splits[0]))
    self.assertEqual(2, len(splits[1]))
    splits = dag.split_inputs(4)
    self.assertEqual(4, len(splits))
    self.assertEqual(1, len(splits[0]))
    self.assertEqual(1, len(splits[1]))
    self.assertEqual(1, len(splits[2]))
    self.assertEqual(1, len(splits[3]))
    splits = dag.split_inputs(3)
    self.assertEqual(3, len(splits))
    self.assertEqual(4, len(splits[0]) + len(splits[1]) + len(splits[2]))

  def test_split_single(self):
    events = [MockEvent()]
    dag = EventDag(events)
    splits = dag.split_inputs(1)
    self.assertEqual(1, len(splits))
    self.assertEqual(1, len(splits[0]))

  def test_split_zero(self):
    events = []
    dag = EventDag(events)
    splits = dag.split_inputs(1)
    self.assertEqual(1, len(splits))
    self.assertEqual(0, len(splits[0]))

  def test_split_odd(self):
    events = [MockEvent(), MockEvent(), MockEvent()]
    dag = EventDag(events)
    splits = dag.split_inputs(2)
    self.assertEqual(2, len(splits))
    self.assertEqual(3, len(splits[0]) + len(splits[1]))
    splits = dag.split_inputs(3)
    self.assertEqual(3, len(splits))
    self.assertEqual(3, len(splits[0]) + len(splits[1]) + len(splits[2]))

if __name__ == '__main__':
  unittest.main()
