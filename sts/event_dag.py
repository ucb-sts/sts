# Copyright 2011-2013 Colin Scott
# Copyright 2011-2013 Andreas Wundsam
# Copyright 2012-2013 Sam Whitlock
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

from sts.fingerprints.messages import *
from sts.replay_event import *
import logging
import time
from collections import defaultdict
log = logging.getLogger("event_dag")

def split_list(l, split_ways):
  ''' Split our inputs into split_ways separate lists '''
  if split_ways < 1:
    raise ValueError("Split ways must be greater than 0")

  splits = []
  split_interval = len(l) / split_ways # integer division = floor
  remainder = len(l) % split_ways # remainder is guaranteed to be less than splitways

  start_idx = 0
  while len(splits) < split_ways:
    split_idx = start_idx + split_interval
    # the first 'remainder' chunks are made one element larger to chew
    # up the remaining elements (remainder < splitways)
    # note: len(l) = split_ways *  split_interval + remainder
    if remainder > 0:
      split_idx += 1
      remainder -= 1

    splits.append(l[start_idx:split_idx])
    start_idx = split_idx
  return splits

class AtomicInput(object):
  def __init__(self, failure, recoveries):
    self.failure = failure
    self.recoveries = recoveries

  @property
  def label(self):
    return "a(%s,%s)" % (self.failure.label, [ r.label for r in self.recoveries ])

  def __repr__(self):
    return "AtomicInput:%r%r" % (self.failure, self.recoveries)

class EventDagView(object):
  def __init__(self, parent, events_list):
    ''' subset is a list '''
    self._parent = parent
    self._events_list = list(events_list)
    self._events_set = set(self._events_list)

  @property
  def events(self):
    '''Return the events in the DAG'''
    return self._events_list

  @property
  def input_events(self):
    # TODO(cs): memoize?
    return [ e for e in self._events_list if isinstance(e, InputEvent) and e.prunable ]

  @property
  def atomic_input_events(self):
    return self._parent._atomic_input_events(self.input_events)

  def input_subset(self, subset):
    '''pre: subset must be a subset of only this view'''
    return self._parent.input_subset(subset)

  def atomic_input_subset(self, subset):
    '''pre: subset must be a subset of only this view'''
    return self._parent.atomic_input_subset(subset)

  def input_complement(self, subset):
    return self._parent.input_complement(subset, self._events_list)

  def insert_atomic_inputs(self, inputs):
    return self._parent.insert_atomic_inputs(inputs, events_list=self._events_list)

  def add_inputs(self, inputs):
    return self._parent.add_inputs(inputs, self._events_list)

  def next_state_change(self, index):
    return self._parent.next_state_change(index, events=self.events)

  def get_original_index_for_event(self, event):
    return self._parent.get_original_index_for_event(event)

  def get_last_invariant_violation(self):
    return self._parent.get_last_invariant_violation()

  def set_events_as_timed_out(self, timed_out_event_labels):
    return self._parent.set_events_as_timed_out(timed_out_event_labels)

  def filter_timeouts(self):
    return self._parent.filter_timeouts(events_list=self._events_list)

  def __len__(self):
    return len(self._events_list)

# TODO(cs): move these somewhere else
def migrations_per_host(events):
  host2migrations = defaultdict(list)
  for e in events:
    if type(e) == HostMigration:
      host2migrations[e.host_id].append(e)
  return host2migrations

def replace_migration(replacee, old_location, new_location, event_list):
  # `replacee' is the migration to be replaced
  # Don't mutate replacee -- instead, replace it
  new_migration = HostMigration(old_location[0], old_location[1],
                                new_location[0], new_location[1],
                                host_id=replacee.host_id,
                                time=replacee.time, label=replacee.label)
  # TODO(cs): O(n^2)
  index = event_list.index(replacee)
  event_list[index] = new_migration
  return new_migration

class EventDag(object):
  '''A collection of Event objects. EventDags are primarily used to present a
  view of the underlying events with some subset of the input events pruned
  '''

  # We peek ahead this many seconds after the timestamp of the subseqeunt
  # event
  # TODO(cs): be smarter about this -- peek() too far, and peek()'ing not far
  # enough can both have negative consequences
  _peek_seconds = 0.3
  # If we prune a failure, make sure that the subsequent
  # recovery doesn't occur
  _failure_types = set([SwitchFailure, LinkFailure, ControllerFailure,
                        ControlChannelBlock, BlockControllerPair])
  # NOTE: we treat failure/recovery as an atomic pair, since it doesn't make
  # much sense to prune a recovery event
  _recovery_types = set([SwitchRecovery, LinkRecovery, ControllerRecovery,
                         ControlChannelUnblock, UnblockControllerPair])
  # ignoring these input types
  _ignored_input_types = set([WaitTime])

  def __init__(self, events, prefix_trie=None):
    '''events is a list of EventWatcher objects. Refer to log_parser.parse to
    see how this is assembled.'''
    # TODO(cs): ugly that the superclass has to keep track of
    # PeekingEventDag's data
    self._prefix_trie = prefix_trie
    self._events_list = events
    self._events_set = set(self._events_list)
    self._label2event = {
      event.label : event
      for event in self._events_list
    }
    self._event2idx = {
      event : i
      for i, event in enumerate(self._events_list)
    }
    # TODO(cs): this should be moved to a dag transformer class
    self._host2initial_location = {
      host : migrations[0].old_location
      for host, migrations in migrations_per_host(self._events_list).iteritems()
    }
    self._last_violation = None

  @property
  def events(self):
    '''Return the events in the DAG'''
    return self._events_list

  @property
  def input_events(self):
    # TODO(cs): memoize?
    return [ e for e in self._events_list if isinstance(e, InputEvent) and e.prunable ]

  @property
  def atomic_input_events(self):
    return self._atomic_input_events(self.input_events)

  def _get_event(self, label):
    if label not in self._label2event:
      raise ValueError("Unknown label %s" % str(label))
    return self._label2event[label]

  def _atomic_input_events(self, inputs):
    # TODO(cs): memoize?
    skipped_recoveries = set()
    atomic_inputs = []
    for e in inputs:
      if e in skipped_recoveries:
        continue

      if type(e) in self._failure_types and e.dependent_labels != []:
        recoveries = []
        for label in e.dependent_labels:
          recovery = self._label2event[label]
          skipped_recoveries.add(recovery)
          recoveries.append(recovery)
        atomic_inputs.append(AtomicInput(e, recoveries))
      else:
        atomic_inputs.append(e)
    return atomic_inputs

  def _expand_atomics(self, atomic_inputs):
    inputs = []
    for e in atomic_inputs:
      if type(e) == AtomicInput:
        inputs.append(e.failure)
        for recovery in e.recoveries:
          inputs.append(recovery)
      else:
        inputs.append(e)
    inputs.sort(key=lambda e: self._event2idx[e])
    return inputs

  def filter_unsupported_input_types(self):
    return EventDagView(self, (e for e in self._events_list
                               if type(e) not in self._ignored_input_types))

  def compute_remaining_input_events(self, ignored_portion, events_list=None):
    ''' ignore all input events in ignored_inputs,
    as well all of their dependent input events'''
    if events_list is None:
      events_list = self.events
    remaining = []
    for event in events_list:
      if event not in ignored_portion:
        remaining.append(event)
      else:
        # Add dependent to ignored_portion
        for label in event.dependent_labels:
          # Note that recoveries will be a dependent of preceding failures
          dependent_event = self._label2event[label]
          ignored_portion.add(dependent_event)

    # Update the migration locations in remaining
    self.update_migrations(remaining, ignored_portion, events_list)
    return remaining

  def update_migrations(self, remaining, ignored_portion, events_list):
    ''' Walk through remaining input events, and update the source location of
    the host migration. For example, if one host migrates twice:

    location A -> location B -> location C

    And the first migration is pruned, update the second HostMigration event
    to look like:

    location A -> location C

    Note: mutates remaining
    '''
    # TODO(cs): this should be moved outside of EventDag
    # TODO(cs): this algorithm could be simplified substantially by invoking
    # migrations_per_host()

    # keep track of the most recent location of the host that did not involve
    # a pruned HostMigration event
    # location is: (ingress dpid, ingress port no)
    currentloc2unprunedloc = {}

    for m in [e for e in events_list if type(e) == HostMigration]:
      src = m.old_location
      dst = m.new_location
      if m in ignored_portion:
        if src in currentloc2unprunedloc:
          # There was a prior migration in ignored_portion
          # Update the new dst to point back to the unpruned location
          unprunedlocation = currentloc2unprunedloc[src]
          del currentloc2unprunedloc[src]
          currentloc2unprunedloc[dst] = unprunedlocation
        else:
          # We are the first migration for this host in ignored_portion
          # Point to our tail
          currentloc2unprunedloc[dst] = src
      else: # m in remaining
        if src in currentloc2unprunedloc:
          # There was a prior migration in ignored_portion
          # Replace this HostMigration with a new one, with source at the
          # last unpruned location
          unpruned_loc = currentloc2unprunedloc[src]
          del currentloc2unprunedloc[src]
          new_loc = dst
          replace_migration(m, unpruned_loc, new_loc, remaining)

  def _ignored_except_internals_and_recoveries(self, ignored_portion):
    # Note that dependent_labels only contains dependencies between input
    # events. Dependencies with internal events are inferred by EventScheduler.
    # Also note that we treat failure/recovery as an atomic pair, so we don't prune
    # recovery events on their own.
    return set(e for e in ignored_portion
               if (isinstance(e, InputEvent) and e.prunable and
                   type(e) not in self._recovery_types))

  def _ignored_except_internals(self, ignored_portion):
    return set(e for e in ignored_portion if isinstance(e, InputEvent) and
               e.prunable)

  def input_subset(self, subset):
    ''' Return a view of the dag with only the subset and subset dependents
    remaining'''
    ignored = self._events_set - set(subset)
    ignored = self._ignored_except_internals_and_recoveries(ignored)
    remaining_events = self.compute_remaining_input_events(ignored)
    return EventDagView(self, remaining_events)

  def atomic_input_subset(self, subset):
    ''' Return a view of the dag with only the subset remaining, where
    dependent input pairs remain together'''
    # Relatively simple: expand atomic pairs into individual inputs, take
    # all input events in result, and compute_remaining_input_events as normal
    subset = self._expand_atomics(subset)
    ignored = self._events_set - set(subset)
    ignored = self._ignored_except_internals(ignored)
    remaining_events = self.compute_remaining_input_events(ignored)
    return EventDagView(self, remaining_events)

  def input_complement(self, subset, events_list=None):
    ''' Return a view of the dag with everything except the subset and
    subset dependencies'''
    subset = self._ignored_except_internals_and_recoveries(subset)
    remaining_events = self.compute_remaining_input_events(subset, events_list)
    return EventDagView(self, remaining_events)

  def _straighten_inserted_migrations(self, remaining_events):
    ''' This is a bit hairy: when migrations are added back in, there may be
    gaps in host locations. We need to straighten out those gaps -- i.e. make
    the series of host migrations for any given host a line.

    Pre: remaining_events is sorted in the same relative order as the original
    trace
    '''
    host2migrations = migrations_per_host(remaining_events)
    for host, migrations in host2migrations.iteritems():
      # Prime the loop with the initial location
      previous_location = self._host2initial_location[host]
      for m in migrations:
        if m.old_location != previous_location:
          replacement = replace_migration(m, previous_location,
                                          m.new_location, remaining_events)
        else:
          replacement = m
        previous_location = replacement.new_location
    return remaining_events

  def insert_atomic_inputs(self, atomic_inputs, events_list=None):
    '''Insert inputs into events_list in the same relative order as the
    original events list. This method is needed because set union as used in
    delta debugging does not make sense for event sequences (events are ordered)'''
    # Note: events_list should never be None (I think), since it does not make
    # sense to insert inputs into the original sequence that are already present
    if events_list is None:
      raise ValueError("Shouldn't be adding inputs to the original trace")

    inputs = self._expand_atomics(atomic_inputs)

    if not all(e in self._event2idx for e in inputs):
      raise ValueError("Not all inputs present in original events list %s" %
                       [e for e in input if e not in self._event2idx])
    if not all(e in self._event2idx for e in events_list):
      raise ValueError("Not all events in original events list %s" %
                       [e for e in events_list if e not in self._event2idx])

    result = []
    for _, successor in enumerate(events_list):
      orig_successor_idx = self._event2idx[successor]
      while len(inputs) > 0 and orig_successor_idx > self._event2idx[inputs[0]]:
        # If the current successor did in fact come after the next input in the
        # original trace, insert next input here
        input = inputs.pop(0)
        result.append(input)
      result.append(successor)

    # Any remaining inputs should be appended at the end -- they had no
    # successors
    result += inputs
    # Deal with newly added host migrations
    result = self._straighten_inserted_migrations(result)
    return EventDagView(self, result)

  def mark_invalid_input_sequences(self):
    '''Fill in domain knowledge about valid input
    sequences (e.g. don't prune failure without pruning recovery.)
    Only do so if this isn't a view of a previously computed DAG'''

    # TODO(cs): should this be factored out?

    # Note: we treat each failure/recovery pair atomically, since it doesn't
    # make much sense to prune recovery events. Also note that that we will
    # never see two failures (for a particular node) in a row without an
    # interleaving recovery event.
    fingerprint2previousfailure = {}

    # NOTE: mutates the elements of self._events_list
    for event in self._events_list:
      if hasattr(event, 'fingerprint'):
        # Skip over the class name
        fingerprint = event.fingerprint[1:]
        if type(event) in self._failure_types:
          # Insert it into the previous failure hash
          fingerprint2previousfailure[fingerprint] = event
        elif type(event) in self._recovery_types:
          # Check if there were any failure predecessors
          if fingerprint in fingerprint2previousfailure:
            failure = fingerprint2previousfailure[fingerprint]
            failure.dependent_labels.append(event.label)
        #elif type(event) in self._ignored_input_types:
        #  raise RuntimeError("No support for %s dependencies" %
        #                      type(event).__name__)

  def next_state_change(self, index, events=None):
    ''' Return the next ControllerStateChange that occurs at or after
    index.'''
    if events is None:
      events = self.events
    # TODO(cs): for now, assumes a single controller
    for event in events[index:]:
      if type(event) == ControllerStateChange:
        return event
    return None

  def get_original_index_for_event(self, event):
    return self._event2idx[event]

  def __len__(self):
    return len(self._events_list)

  def get_last_invariant_violation(self):
    if self._last_violation is not None:
      return self._last_violation
    for event in reversed(self._events_list):
      # Match on persistent violations in computing MCS
      if type(event) == InvariantViolation and event.persistent:
        self._last_violation = event
        return event
    return None

  def set_events_as_timed_out(self, timed_out_event_labels):
    for event in self._events_list:
      event.timed_out = False

    for label in timed_out_event_labels:
      self._get_event(label).timed_out = True

  def filter_timeouts(self, events_list=None):
    if events_list is None:
      events_list = self._events_list
    no_timeouts = [ e for e in events_list if not e.timed_out ]
    return EventDagView(self, no_timeouts)
