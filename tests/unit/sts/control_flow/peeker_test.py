#!/usr/bin/env python

import unittest
import sys
import os
import itertools
from copy import copy
import types
import signal
import tempfile

from sts.control_flow.peeker import *
# TODO: move Mock internal events to lib
from tests.unit.sts.event_dag_test import MockInternalEvent
from tests.unit.sts.control_flow_test import MockInputEvent
from config.experiment_config_lib import ControllerConfig
from sts.control_flow import Replayer, MCSFinder
from sts.topology import FatTree, PatchPanel, MeshTopology
from sts.simulation_state import Simulation, SimulationConfig
from sts.replay_event import Event, InternalEvent, InputEvent
from sts.event_dag import EventDag
from sts.entities import Host, Controller
import logging

sys.path.append(os.path.dirname(__file__) + "/../../..")

_running_simulation = None
def handle_int(sigspec, frame):
  print >> sys.stderr, "Caught signal %d, stopping sdndebug" % sigspec
  if _running_simulation is not None:
    _running_simulation.current_simulation.clean_up()
  raise RuntimeError("terminating on signal %d" % sigspec)


signal.signal(signal.SIGINT, handle_int)
signal.signal(signal.SIGTERM, handle_int)

class PeekerTest(unittest.TestCase):
  def setUp(self):
    self.input_trace = [ MockInputEvent(fingerprint=("class",f)) for f in range(1,7) ]
    self.dag = EventDag(self.input_trace)
    self.peeker = Peeker()

  def test_basic_noop(self):
    """ test_basic_noop: running on a dag with no input events returns the same dag """
    events = [ MockInputEvent(fingerprint=("class",f)) for f in range(1,7) ]
    new_dag = self.peeker.peek(None, EventDag(events))
    self.assertEquals(events, new_dag.events)

  def test_basic_no_prune(self):
    inp1 = MockInputEvent(fingerprint="a")
    inp2 = MockInputEvent(fingerprint="b")
    int1 = MockInternalEvent(fingerprint="c")
    inp3 =  MockInputEvent(fingerprint="d")
    events = [ inp1, inp2, int1, inp3 ]

    def fake_find_internal_events(simulation_config, replay_dag, wait_time):
      if replay_dag.events == [ inp1 ]:
        return []
      elif replay_dag.events == [ inp1, inp2 ]:
        return [ int1 ]
      elif replay_dag.events == [ inp1, inp2, int1, inp3 ]:
        return []
      else:
        raise AssertionError("Unexpected event sequence queried: %s" % replay_dag.events)

    self.peeker.find_internal_events = fake_find_internal_events
    new_dag = self.peeker.peek(None, EventDag(events))
    self.assertEquals(events, new_dag.events)

  def test_basic_prune(self):
    inp1 = MockInputEvent(fingerprint="a")
    inp2 = MockInputEvent(fingerprint="b")
    int1 = MockInternalEvent(fingerprint="c")
    inp3 =  MockInputEvent(fingerprint="d")
    int2 = MockInternalEvent(fingerprint="e")
    all_events = [ inp1, inp2, int1, inp3, int2 ]
    sub_events = [ inp2, int1, inp3, int2 ]

    def fake_find_internal_events(simulation_config, replay_dag, wait_time):
      if replay_dag.events == [ inp2 ]:
        return []
      elif replay_dag.events == [ inp2, inp3 ]:
        return [ int2 ]
      else:
        raise AssertionError("Unexpected event sequence queried: %s" % replay_dag.events)

    self.peeker.find_internal_events = fake_find_internal_events
    new_dag = self.peeker.peek(None, EventDag(sub_events))
    self.assertEquals( [inp2, inp3, int2 ], new_dag.events)


class MatchFingerPrintTest(unittest.TestCase):
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


