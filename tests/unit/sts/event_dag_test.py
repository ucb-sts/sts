#!/usr/bin/env python

import unittest
import sys
import os.path
import itertools
from copy import copy
import types

sys.path.append(os.path.dirname(__file__) + "/../../..")

from sts.replay_event import *
from sts.event_dag import *

class MockEvent(Event):
  def proceed(self, simulation):
    pass

class MockInternalEvent(InternalEvent):
  def __init__(self, fingerprint, label="a"):
    self.fingerprint = fingerprint
    self.label = label

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

  def test_match_fingerprints_simple(self):
    expected = [ MockInternalEvent(fingerprint) for fingerprint in ["a","b","c"] ]
    actual = [ MockInternalEvent(fingerprint) for fingerprint
               in ["a","d","d","d","d","b","d","d","d"] ]

    result = match_fingerprints(actual, expected)
    result = [ r.fingerprint for r in result ]
    self.assertEqual(["a","d","d","d","d","b"], result)

  def test_match_fingerprints_duplicate_expected(self):
    expected = [ MockInternalEvent(fingerprint) for fingerprint
                 in ["a","b","c","b","c","f"] ]
    actual = [ MockInternalEvent(fingerprint) for fingerprint
               in ["a","d","d","d","d","c","b","d","d","d","c","d"] ]

    result = match_fingerprints(actual, expected)
    result = [ r.fingerprint for r in result ]
    self.assertEqual(["a","d","d","d","d","c","b","d","d","d","c"], result)

  def test_match_fingerprints_duplicate_inferred(self):
    expected = [ MockInternalEvent(fingerprint) for fingerprint
                 in ["a","b","c"] ]
    actual = [ MockInternalEvent(fingerprint) for fingerprint
               in ["a","d","d","d","d","c","b","d","d","d","c","d"] ]

    result = match_fingerprints(actual, expected)
    result = [ r.fingerprint for r in result ]
    # TODO(cs): perhaps we should include "b"? [i.e., make the inferrence
    # unordered or semi-ordered]
    self.assertEqual(["a","d","d","d","d","c"], result)

  def test_match_fingerprints_empty(self):
    expected = [ MockInternalEvent(fingerprint) for fingerprint
                 in ["a","b","c"] ]
    actual = [ MockInternalEvent(fingerprint) for fingerprint
               in ["d","e","f"] ]

    result = match_fingerprints(actual, expected)
    result = [ r.fingerprint for r in result ]
    # TODO(cs): perhaps we should include "b"? [i.e., make the inferrence
    # unordered or semi-ordered]
    self.assertEqual([], result)


if __name__ == '__main__':
  unittest.main()
