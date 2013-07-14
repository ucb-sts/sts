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
import os.path

sys.path.append(os.path.dirname(__file__) + "/../../..")

from sts.replay_event import *
from sts.event_dag import *

class MockEvent(InputEvent):
  def proceed(self, simulation):
    pass

class MockInternalEvent(InternalEvent):
  def __init__(self, fingerprint, label=None):
    InternalEvent.__init__(self, label)
    self.timed_out = False
    self._fingerprint = fingerprint

  @property
  def fingerprint(self):
    return self._fingerprint

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

  def test_migration_simple(self):
    events = [ MockInternalEvent('a'), HostMigration(1,1,2,2,"host1"),
               MockInternalEvent('b'), HostMigration(2,2,3,3,"host1"),
               MockInputEvent() ]
    # Don't prune anything
    event_dag = EventDag(events)
    new_dag = event_dag.input_subset(events)
    self.assertEqual(events, new_dag.events)

  def test_migration_prune_1(self):
    events = [ MockInternalEvent('a'), HostMigration(1,1,2,2,"host1"),
               MockInternalEvent('b'), HostMigration(2,2,3,3,"host1"),
               MockInputEvent() ]
    # Prune the first migration
    subset = [events[1]]
    event_dag = EventDag(events)
    new_dag = event_dag.input_complement(subset)
    fingerprint = ('HostMigration',1,1,3,3,"host1")
    self.assertEqual(fingerprint, new_dag.events[2].fingerprint)

  def test_migration_prune_2(self):
    events = [ MockInternalEvent('a'), HostMigration(1,1,2,2,"host1"),
               MockInternalEvent('b'), HostMigration(2,2,3,3,"host1"),
               MockInputEvent(), HostMigration(3,3,4,4,"host1"),
               HostMigration(4,4,5,5,"host1") ]
    # Prune the seconds and third migration
    subset = [events[3], events[4], events[5]]
    event_dag = EventDag(events)
    new_dag = event_dag.input_complement(subset)
    fingerprint = ('HostMigration',2,2,5,5,"host1")
    self.assertEqual(fingerprint, new_dag.events[3].fingerprint)

  def test_migration_prune_last(self):
    events = [ MockInternalEvent('a'), HostMigration(1,1,2,2,"host1"),
               MockInternalEvent('b'), HostMigration(2,2,3,3,"host1"),
               MockInputEvent() ]
    # Prune the last migration
    subset = [events[3]]
    event_dag = EventDag(events)
    new_dag = event_dag.input_complement(subset)
    fingerprint = ('HostMigration',1,1,2,2,"host1")
    self.assertEqual(fingerprint, new_dag.events[1].fingerprint)


if __name__ == '__main__':
  unittest.main()
