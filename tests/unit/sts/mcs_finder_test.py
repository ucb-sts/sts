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
import shutil

from sts.control_flow.mcs_finder import MCSFinder, EfficientMCSFinder
from sts.replay_event import InputEvent, InvariantViolation
from sts.event_dag import EventDag
import logging

sys.path.append(os.path.dirname(__file__) + "/../../..")

class MockSimulationConfig(object):
  def __init__(self, ignore_interposition=False):
    self.ignore_interposition = ignore_interposition

class MockMCSFinderBase(MCSFinder):
  ''' Overrides self.invariant_check and run_simulation_forward() '''
  def __init__(self, event_dag, mcs):
    super(MockMCSFinderBase, self).__init__(MockSimulationConfig(), event_dag,
                                            invariant_check_name="InvariantChecker.check_liveness")
    # Hack! Give a fake name in config.invariant_checks.name_to_invariant_checks, but
    # but remove it from our dict directly after. This is to prevent
    # sanity check exceptions from being thrown.
    self.invariant_check = self._invariant_check
    self.new_dag = None
    self.mcs = mcs
    self.simulation = None
    self.transform_dag = None

  def log(self, message):
    self._log.info(message)

  def _invariant_check(self, _):
    for e in self.mcs:
      if e not in self.new_dag._events_set:
        return []
    return ["violation"]

  def replay(self, new_dag, hook=None, ignore_runtime_stats=False):
    self.new_dag = new_dag
    return self.invariant_check(new_dag)

# Horrible horrible hack. This way lies insanity
class MockMCSFinder(MockMCSFinderBase, MCSFinder):
  def __init__(self, event_dag, mcs):
    MockMCSFinderBase.__init__(self, event_dag, mcs)
    self._log = logging.getLogger("mock_mcs_finder")

class MockEfficientMCSFinder(MockMCSFinderBase, EfficientMCSFinder):
  def __init__(self, event_dag, mcs):
    MockMCSFinderBase.__init__(self, event_dag, mcs)
    self._log = logging.getLogger("mock_efficient_mcs_finder")

class MockInputEvent(InputEvent):
  def __init__(self, fingerprint=None, **kws):
    super(MockInputEvent, self).__init__(**kws)
    self._fingerprint = fingerprint
    self.timed_out = False

  @property
  def fingerprint(self):
    return self._fingerprint

  def proceed(self, simulation):
    return True

mcs_results_path = "/tmp/mcs_results"

class MCSFinderTest(unittest.TestCase):
  def test_basic(self):
    self.basic(MockMCSFinder)

  def test_basic_efficient(self):
    self.basic(MockEfficientMCSFinder)

  def basic(self, mcs_finder_type):
    trace = [ MockInputEvent(fingerprint=("class",f)) for f in range(1,7) ]
    trace.append(InvariantViolation(["violation"], persistent=True))
    dag = EventDag(trace)
    mcs = [trace[0]]
    mcs_finder = mcs_finder_type(dag, mcs)
    try:
      os.makedirs(mcs_results_path)
      mcs_finder.init_results(mcs_results_path)
      mcs_finder.simulate()
    finally:
      shutil.rmtree(mcs_results_path)
    self.assertEqual(mcs, mcs_finder.dag.input_events)

  def test_straddle(self):
    self.straddle(MockMCSFinder)

  def test_straddle_efficient(self):
    self.straddle(MockEfficientMCSFinder)

  def straddle(self, mcs_finder_type):
    trace = [ MockInputEvent(fingerprint=("class",f)) for f in range(1,7) ]
    trace.append(InvariantViolation(["violation"], persistent=True))
    dag = EventDag(trace)
    mcs = [trace[0],trace[5]]
    mcs_finder = mcs_finder_type(dag, mcs)
    try:
      os.makedirs(mcs_results_path)
      mcs_finder.init_results(mcs_results_path)
      mcs_finder.simulate()
    finally:
      shutil.rmtree(mcs_results_path)
    self.assertEqual(mcs, mcs_finder.dag.input_events)

  def test_all(self):
    self.all(MockMCSFinder)

  def test_all_efficient(self):
    self.all(MockEfficientMCSFinder)

  def all(self, mcs_finder_type):
    trace = [ MockInputEvent(fingerprint=("class",f)) for f in range(1,7) ]
    trace.append(InvariantViolation(["violation"], persistent=True))
    dag = EventDag(trace)
    mcs = trace[0:6]
    mcs_finder = mcs_finder_type(dag, mcs)
    try:
      os.makedirs(mcs_results_path)
      mcs_finder.init_results(mcs_results_path)
      mcs_finder.simulate()
    finally:
      shutil.rmtree(mcs_results_path)
    self.assertEqual(mcs, mcs_finder.dag.input_events)

if __name__ == '__main__':
  unittest.main()
