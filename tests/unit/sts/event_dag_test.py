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

class MockEvent(InputEvent):
  def proceed(self, simulation):
    pass

class MockInternalEvent(InternalEvent):
  def __init__(self, fingerprint, label=None):
    InternalEvent.__init__(self, label)
    self.fingerprint = fingerprint

  def proceed(self, simulation):
    pass

class MockInputEvent(InputEvent):
  def proceed(self, simulation):
    pass

class event_dag_test(unittest.TestCase):
  def test_split_basic(self):
    events = [MockEvent(), MockEvent(), MockEvent(), MockEvent()]
    dag = EventDag(events)
    splits = split_list(dag.input_events, 2)
    self.assertEqual(2, len(splits))
    self.assertEqual(2, len(splits[0]))
    self.assertEqual(2, len(splits[1]))
    splits = split_list(dag.input_events, 4)
    self.assertEqual(4, len(splits))
    self.assertEqual(1, len(splits[0]))
    self.assertEqual(1, len(splits[1]))
    self.assertEqual(1, len(splits[2]))
    self.assertEqual(1, len(splits[3]))
    splits = split_list(dag.input_events, 3)
    self.assertEqual(3, len(splits))
    self.assertEqual(4, len(splits[0]) + len(splits[1]) + len(splits[2]))

  def test_split_single(self):
    events = [MockEvent()]
    dag = EventDag(events)
    splits = split_list(dag.input_events, 1)
    self.assertEqual(1, len(splits))
    self.assertEqual(1, len(splits[0]))

  def test_split_zero(self):
    events = []
    dag = EventDag(events)
    splits = split_list(dag.input_events, 1)
    self.assertEqual(1, len(splits))
    self.assertEqual(0, len(splits[0]))

  def test_split_odd(self):
    events = [MockEvent(), MockEvent(), MockEvent()]
    dag = EventDag(events)
    splits = split_list(dag.input_events, 2)
    self.assertEqual(2, len(splits))
    self.assertEqual(3, len(splits[0]) + len(splits[1]))
    splits = split_list(dag.input_events, 3)
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

  def test_event_dag(self):
    event_dag = EventDag( [ MockInternalEvent("a"), MockInputEvent() ])
    self.assertEqual(2, len(event_dag))
    self.assertEqual(2, len(event_dag.filter_unsupported_input_types()))
    event_dag.mark_invalid_input_sequences()
    self.assertEqual(2, len(event_dag))

  def test_event_dag_subset(self):
    mockInputEvent = MockInputEvent()
    mockInputEvent2 = MockInputEvent()
    events = [ MockInternalEvent('a'), mockInputEvent, mockInputEvent2 ]
    event_dag = EventDag(events)
    # subset of (full set) is a noop
    self.assertEqual( event_dag.events, event_dag.input_subset(events).events)
    # subset of () empty retains the internal event
    self.assertEqual( event_dag.events[0:1], event_dag.input_subset([]).events)

    sub_graph = event_dag.input_subset([mockInputEvent])
    self.assertEqual( event_dag.events[0:2], sub_graph.events)

  def test_event_dag_complement(self):
    mockInputEvent = MockInputEvent()
    mockInputEvent2 = MockInputEvent()
    events = [ MockInternalEvent('a'), mockInputEvent, mockInputEvent2 ]
    event_dag = EventDag(events)
    # complement of (nothing) is full set
    self.assertEqual( event_dag.events, event_dag.input_complement([]).events)
    # complement of (all elements) retains only the internal event
    self.assertEqual( event_dag.events[0:1], event_dag.input_complement(events).events)

    sub_graph = event_dag.input_complement([mockInputEvent])
    self.assertEqual( [ e for (i, e) in enumerate(event_dag.events) if i==0 or i==2 ], sub_graph.events)



if __name__ == '__main__':
  unittest.main()
