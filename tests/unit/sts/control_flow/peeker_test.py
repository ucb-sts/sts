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
import os
import signal

from sts.control_flow.peeker import *
# TODO: move Mock internal events to lib
from tests.unit.sts.event_dag_test import MockInternalEvent
from tests.unit.sts.mcs_finder_test import MockInputEvent
from sts.replay_event import InternalEvent, ConnectToControllers
from sts.event_dag import EventDag
from config.experiment_config_lib import ControllerConfig
from sts.simulation_state import SimulationConfig
from sts.util.convenience import IPAddressSpace
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

class MockConnectToControllers(ConnectToControllers):
  def __init__(self, fingerprint=None, **kwargs):
    super(MockConnectToControllers, self).__init__(**kwargs)
    self._fingerprint = fingerprint
    self.prunable = False

  @property
  def fingerprint(self):
    return self._fingerprint

  def proceed(self, simulation):
    return True

class MockSnapshotter(object):
  def snapshot_proceed(*args):
    pass

class PeekerTest(unittest.TestCase):
  def setUp(self):
    self.input_trace = [ MockInputEvent(fingerprint=("class",f)) for f in range(1,7) ]
    self.dag = EventDag(self.input_trace)
    self.prefix_peeker = PrefixPeeker(None)
    IPAddressSpace._claimed_addresses.clear()
    ControllerConfig._controller_labels.clear()
    controller_cfg = ControllerConfig(start_cmd="sleep")
    simulation_cfg = SimulationConfig(controller_configs=[controller_cfg])
    self.snapshot_peeker = SnapshotPeeker(simulation_cfg,
                                          default_dp_permit=True)
    self.snapshot_peeker.setup_simulation = lambda: (None, None)
    # N.B. this assumes that no internal events occur before the first input
    # event.
    self.snapshot_peeker.snapshot_and_play_forward = lambda *args: ([], None)
    self.snapshot_peeker.replay_interval = lambda *args: []
    self.mock_snapshotter = MockSnapshotter()

  def test_basic_noop(self):
    """ test_basic_noop: running on a dag with no internal events returns the same dag """
    events = [MockConnectToControllers(fingerprint=("class",0))] + [ MockInputEvent(fingerprint=("class",f)) for f in range(1,7) ]
    new_dag = self.prefix_peeker.peek(EventDag(events))
    self.assertEquals(events, new_dag.events)
    new_dag = self.snapshot_peeker.peek(EventDag(events))
    self.assertEquals(events, new_dag.events)

  def test_basic_no_prune(self):
    inp1 = MockConnectToControllers(fingerprint="a")
    inp2 = MockInputEvent(fingerprint="b")
    int1 = MockInternalEvent(fingerprint="c")
    inp3 =  MockInputEvent(fingerprint="d")
    events = [ inp1, inp2, int1, inp3 ]

    def fake_find_internal_events(replay_dag, inject_input, wait_time):
      if inject_input == inp1:
        return []
      elif inject_input == inp2:
        return [ int1 ]
      elif inject_input == inp3:
        return []
      else:
        raise AssertionError("Unexpected event sequence queried: %s" % replay_dag.events)

    # first, prefix peeker
    self.prefix_peeker.find_internal_events = fake_find_internal_events
    new_dag = self.prefix_peeker.peek(EventDag(events))
    self.assertEquals(events, new_dag.events)

    # next, snapshot peeker
    # Hack alert! throw away first two args
    def snapshotter_fake_find_internal_events(s, c, dag_interval,
                                              inject_input, wait_time):
      return (fake_find_internal_events(dag_interval, inject_input, wait_time), self.mock_snapshotter)
    self.snapshot_peeker.find_internal_events = snapshotter_fake_find_internal_events
    new_dag = self.snapshot_peeker.peek(EventDag(events))
    self.assertEquals(events, new_dag.events)

  def test_basic_prune(self):
    inp2 = MockConnectToControllers(fingerprint="b")
    int1 = MockInternalEvent(fingerprint="c")
    inp3 =  MockInputEvent(fingerprint="d")
    int2 = MockInternalEvent(fingerprint="e")
    sub_events = [ inp2, int1, inp3, int2 ]

    def fake_find_internal_events(replay_dag, inject_input, wait_time):
      if inject_input == inp2:
        # int1 disappears
        return []
      elif inject_input == inp3:
        # int2 does not
        return [ int2 ]
      else:
        raise AssertionError("Unexpected event sequence queried: %s" % replay_dag.events)

    # first, prefix peeker
    self.prefix_peeker.find_internal_events = fake_find_internal_events
    new_dag = self.prefix_peeker.peek(EventDag(sub_events))
    self.assertEquals([inp2, inp3, int2], new_dag.events)

    # next, snapshot peeker
    # Hack alert! throw away first two args
    def snapshotter_fake_find_internal_events(s, c, dag_interval,
                                              inject_input, wait_time):
      return (fake_find_internal_events(dag_interval, inject_input, wait_time), self.mock_snapshotter)
    self.snapshot_peeker.find_internal_events = snapshotter_fake_find_internal_events
    new_dag = self.snapshot_peeker.peek(EventDag(sub_events))
    self.assertEquals([inp2, inp3, int2], new_dag.events)

# TODO(cs): update these tests to reflect new match_fingerprints!
#class MatchFingerPrintTest(unittest.TestCase):
#  def test_match_fingerprints_simple(self):
#    expected = [ MockInternalEvent(fingerprint) for fingerprint in ["a","b","c"] ]
#    actual = [ MockInternalEvent(fingerprint) for fingerprint
#               in ["a","d","d","d","d","b","d","d","d"] ]
#
#    result = match_fingerprints(actual, expected)
#    result = [ r.fingerprint for r in result ]
#    self.assertEqual(["a","d","d","d","d","b"], result)
#
#  def test_match_fingerprints_duplicate_expected(self):
#    expected = [ MockInternalEvent(fingerprint) for fingerprint
#                 in ["a","b","c","b","c","f"] ]
#    actual = [ MockInternalEvent(fingerprint) for fingerprint
#               in ["a","d","d","d","d","c","b","d","d","d","c","d"] ]
#
#    result = match_fingerprints(actual, expected)
#    result = [ r.fingerprint for r in result ]
#    self.assertEqual(["a","d","d","d","d","c","b","d","d","d","c"], result)
#
#  def test_match_fingerprints_duplicate_inferred(self):
#    expected = [ MockInternalEvent(fingerprint) for fingerprint
#                 in ["a","b","c"] ]
#    actual = [ MockInternalEvent(fingerprint) for fingerprint
#               in ["a","d","d","d","d","c","b","d","d","d","c","d"] ]
#
#    result = match_fingerprints(actual, expected)
#    result = [ r.fingerprint for r in result ]
#    # TODO(cs): perhaps we should include "b"? [i.e., make the inferrence
#    # unordered or semi-ordered]
#    self.assertEqual(["a","d","d","d","d","c"], result)
#
#  def test_match_fingerprints_empty(self):
#    expected = [ MockInternalEvent(fingerprint) for fingerprint
#                 in ["a","b","c"] ]
#    actual = [ MockInternalEvent(fingerprint) for fingerprint
#               in ["d","e","f"] ]
#
#    result = match_fingerprints(actual, expected)
#    result = [ r.fingerprint for r in result ]
#    # TODO(cs): perhaps we should include "b"? [i.e., make the inferrence
#    # unordered or semi-ordered]
#    self.assertEqual([], result)


