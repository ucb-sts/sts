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

import logging
import time
import abc
from collections import Counter

from sts.replay_event import WaitTime
from sts.event_dag import EventDag
from sts.control_flow.replayer import Replayer
from sts.control_flow.base import RecordingSyncCallback
from sts.control_flow.snapshot_utils import *
from sts.replay_event import InternalEvent

log = logging.getLogger("sts")

# TODO(cs): is it problematic if we stop responding to OFP_PING / LLDP during
# peek()?

# TODO(cs): peek() should be run as a subprocesses to cope with memory
# constraints, as in mcs_finder. We would need to refactor the class variables
# (convert them to RPC return values, as in client_stats_dict()) below to enable this.

class Peeker(object):
  ''' Peekers are DAG `transformers' that infer the internal events that are or
  are not going to occur for a given event subsequence. '''
  __metaclass__ = abc.ABCMeta
  # { % of inferred fingerprints that were ambiguous ->
  #   # of replays where this % occurred }
  ambiguous_counts = Counter()
  # { class of event -> # occurences of ambiguity }
  ambiguous_events = Counter()

  def __init__(self, simulation_cfg, default_wait_time_seconds=0.5, epsilon_time=0.2):
    self.simulation_cfg = simulation_cfg
    self.default_wait_time_seconds = default_wait_time_seconds
    self.epsilon_time = epsilon_time

  @abc.abstractmethod
  def peek(self, dag):
    '''
    Return a transformed EventDag complete with the internal events that
    are going to occur for the input sequence reflected in the given
    EventDag

    Pre: there is not a simulation (i.e. running controller) in progress
    '''
    pass

  def get_wait_time_seconds(self, first_event, second_event):
    if first_event is None or second_event is None:
      return self.default_wait_time_seconds
    else:
      return second_event.time.as_float() - first_event.time.as_float() + \
             self.epsilon_time


class SnapshotPeeker(Peeker):
  ''' O(n) peeker that takes controller snapshots at each input, peeks
  forward, then restarts the snapshot up until the next input'''
  def __init__(self, simulation_cfg, default_wait_time_seconds=0.5, epsilon_time=0.2):
    if len(simulation_cfg.controller_configs) != 1:
      raise ValueError("Only one controller supported for snapshotting")
    if simulation_cfg.controller_configs[0].sync is not None:
      raise ValueError("STSSyncProto currently incompatible with snapshotting")
    super(SnapshotPeeker, self).__init__(simulation_cfg,
                                         default_wait_time_seconds=default_wait_time_seconds,
                                         epsilon_time=epsilon_time)

  def setup_simulation(self):
    # TODO(cs): currently assumes that STSSyncProto is not used alongside
    # snapshotting.
    simulation = self.simulation_cfg.bootstrap(RecordingSyncCallback(None))
    simulation.openflow_buffer.pass_through_whitelisted_messages = True
    simulation.connect_to_controllers()
    controller = simulation.controller_manager.controllers[0]
    return (simulation, controller)

  def peek(self, dag):
    if dag.input_events == []:
      return dag

    # Inferred events includes input events and internal events
    inferred_events = []

    (simulation, controller) = self.setup_simulation()

    # Internal events inferred in the previous iteration of the following for
    # loop
    events_inferred_last_iteration = []

    # Note that there may be internal events before the first input, so we
    # start the input index at -1
    for inject_input_idx in xrange(-1, len(dag.input_events)):
      log.debug("peek()'ing after input %d" % (inject_input_idx))

      inject_input = get_inject_input(inject_input_idx, dag.input_events)
      following_input = get_following_input(inject_input_idx, dag.input_events)
      expected_internal_events = \
         get_expected_internal_events(inject_input, following_input, dag.events)

      inferred_events += events_inferred_last_iteration
      if inject_input is not None:
        inferred_events.append(inject_input)

      if expected_internal_events == []:
        # Optimization: if no internal events occured between this input and the
        # next, no need to peek(), just replay the next input
        log.debug("Optimization: no expected internal events")
        Peeker.ambiguous_counts[0.0] += 1
        events_inferred_last_iteration = []
        continue

      # Play forward the internal events inferred from last round and the
      # input to be injected
      if inject_input is None:
        wait_time = WaitTime(following_input.time.as_float() -
                             dag.events[0].time.as_float())
        dag_interval = EventDag([wait_time])
      else:
        dag_interval = EventDag(events_inferred_last_iteration + [inject_input])

      assert(dag_interval.events != [])
      wait_time_seconds = self.get_wait_time_seconds(inject_input, following_input)
      found_events = self.find_internal_events(simulation, controller, dag_interval, wait_time_seconds)
      events_inferred_last_iteration = match_and_filter(found_events, expected_internal_events)

    inferred_events += events_inferred_last_iteration
    return EventDag(inferred_events)

  def find_internal_events(self, simulation, controller, dag_interval, wait_time_seconds):
    replayer = Replayer(self.simulation_cfg, dag_interval,
                        pass_through_whitelisted_messages=True)
    replayer.simulation = simulation
    replayer.run_simulation_forward()

    # Now peek() for internal events following inject_input
    snapshotter = Snapshotter(simulation, controller)
    snapshotter.snapshot_controller()

    found_events = play_forward(simulation, wait_time_seconds)

    # Finally, bring the controller back to the state it was at just after
    # injecting inject_input
    snapshotter.snapshot_proceed()
    return found_events

class PrefixPeeker(Peeker):
  ''' O(n^2) peeker that replays each prefix of the subseqeuence from the beginning. '''
  def __init__(self, simulation_cfg, default_wait_time_seconds=0.5, epsilon_time=0.2):
    super(PrefixPeeker, self).__init__(simulation_cfg,
                                       default_wait_time_seconds=default_wait_time_seconds,
                                       epsilon_time=epsilon_time)
    try:
      import pytrie
    except ImportError:
      raise RuntimeError("Need to install pytrie: `sudo pip install pytrie`")
    # The prefix trie stores lists of input events as keys,
    # and lists of both input and internal events as values
    # Note that we pass the trie around between DAG views
    self._prefix_trie = pytrie.Trie()

  def peek(self, dag):
    ''' Infer which internal events are/aren't going to occur (for the entire
    sequence of input events in dag)'''
    # TODO(cs): optimization: write the prefix trie to a file, in case we want to run
    # FindMCS again?
    input_events = dag.input_events

    if len(input_events) == 0:
      # Postcondition: input_events[-1] is not None
      #                and self._events_list[-1] is not None
      return dag

    # Initilize current_input_prefix to the longest_match prefix we've
    # inferred previously (or [] if this is an entirely new prefix)
    current_input_prefix = list(self._prefix_trie\
                                .longest_prefix(input_events, default=[]))
    log.debug("Current input prefix: %s" % str(current_input_prefix))

    # The value is both internal events and input events (values of the trie)
    # leading up, but not including the next input following the tail of the
    # prefix.
    # Note that we assume that there are no internal events before the first
    # input event (i.e. we assume quiescence)
    inferred_events = list(self._prefix_trie\
                           .longest_prefix_value(input_events, default=[]))
    log.debug("Current inferred_events: %s" % str(inferred_events))
    inject_input_idx = len(current_input_prefix)

    # While we still have inputs to inject
    while inject_input_idx < len(input_events):
      # The input we're about to inject
      inject_input = input_events[inject_input_idx]
      following_input = get_following_input(inject_input_idx, dag.input_events)

      # The input following the one we're going to inject
      log.debug("peek()'ing after input %d" % (inject_input_idx))

      expected_internal_events = \
        get_expected_internal_events(inject_input, following_input, dag.events)

      # Optimization: if no internal events occured between this input and the
      # next, no need to peek()
      if expected_internal_events == []:
        log.debug("Optimization: no expected internal events")
        newly_inferred_events = []
        Peeker.ambiguous_counts[0.0] += 1
      else:
        wait_time_seconds = self.get_wait_time_seconds(inject_input, following_input)
        replay_dag = EventDag(inferred_events + [ inject_input ])
        found_events = self.find_internal_events(replay_dag, wait_time_seconds)
        newly_inferred_events = match_and_filter(found_events, expected_internal_events)

      (current_input_prefix,
       inferred_events) = self._update_trie(current_input_prefix, inject_input,
                                            inferred_events, newly_inferred_events)
      inject_input_idx += 1

    return EventDag(inferred_events)

  def find_internal_events(self, replay_dag, wait_time_seconds):
    ''' Replay the replay_dag, then wait for wait_time_seconds and collect internal
        events that occur. Return the list of internal events. '''
    replayer = Replayer(self.simulation_cfg, replay_dag)
    log.debug("Replaying prefix")
    simulation = replayer.simulate()
    newly_inferred_events = play_forward(simulation, wait_time_seconds)
    simulation.clean_up()
    return newly_inferred_events

  def _update_trie(self, current_input_prefix, inject_input, inferred_events,
                   newly_inferred_events):
    ''' Update the trie for this prefix '''
    current_input_prefix = list(current_input_prefix)
    current_input_prefix.append(inject_input)
    # Make sure to prepend the input we just injected
    inferred_events = list(inferred_events)
    inferred_events.append(inject_input)
    inferred_events += newly_inferred_events
    self._prefix_trie[current_input_prefix] = inferred_events
    return (current_input_prefix, inferred_events)

def get_inject_input(inject_input_idx, input_events):
  ''' Return the input at inject_input_index, or None if
  index is negative'''
  if inject_input_idx < 0:
    return None
  else:
    return input_events[inject_input_idx]

def get_following_input(inject_input_idx, input_events):
  ''' Return the event following inject_input_index, or None if
  inject_input_index is the last input '''
  if inject_input_idx < len(input_events) - 1:
    # there is a following input_event
    return input_events[inject_input_idx + 1]
  else:
    return None

def get_expected_internal_events(left_input, right_input, events_list):
  ''' Return previously observed internal events between the left_input and
  the right_input event

  left_input may be None case we return events from the beginning of events_list

  right_input may also be None, in which case we return all events following left_input
  '''
  if left_input is None:
    left_idx = 0
  else:
    left_idx = events_list.index(left_input)

  if right_input is None:
    right_idx = len(events_list)
  else:
    right_idx = events_list.index(right_input)

  return [ i for i in events_list[left_idx:right_idx]
           if isinstance(i, InternalEvent) ]

def play_forward(simulation, wait_time_seconds):
  # Directly after the last input has been injected, flush the internal
  # event buffers in case there were unaccounted internal events
  # Note that there isn't a race condition between flush()'ing and
  # incoming internal events, since sts is single-threaded
  # TODO(cs): flush() is no longer needed!
  simulation.openflow_buffer.flush()
  simulation.controller_sync_callback.flush()

  # Now set all internal event buffers (GodScheduler for
  # ControlMessageReceives and ReplaySyncCallback for state changes)
  # to "record only"
  simulation.set_record_only()

  # Note that this is the monkey patched version of time.sleep
  log.debug("peek()'ing for %f seconds" % wait_time_seconds)
  time.sleep(wait_time_seconds)

  # Now turn off record only through and grab the inferred events
  newly_inferred_events = simulation.unset_record_only()
  return newly_inferred_events

def match_and_filter(newly_inferred_events, expected_internal_events):
  log.debug("Matching fingerprints")
  log.debug("Expected: %s" % str(expected_internal_events))
  log.debug("Inferred: %s" % str(newly_inferred_events))
  # TODO(cs): currently not calling this, out of paranoia. May inadvertently
  # prune expected internal events -- largely serves as an optimization
  #newly_inferred_events = match_fingerprints(newly_inferred_events,
  #                                           expected_internal_events)
  # TODO(cs): need to prune any successors of e_i, in case we waited too
  # long
  count_overlapping_fingerprints(newly_inferred_events,
                                 expected_internal_events)
  newly_inferred_events = correct_timestamps(newly_inferred_events,
                                             expected_internal_events)
  log.debug("Matched events: %s" % str(newly_inferred_events))
  return newly_inferred_events

def count_overlapping_fingerprints(newly_inferred_events,
                                   expected_internal_events):
  ''' Track # of instances where an expected event matches 2 or more inferred
  events. Mutates Peeker.ambiguous_counts and Peeker.ambiguous_events'''
  expected_counts = Counter([e.fingerprint for e in expected_internal_events])
  inferred_counts = Counter([e.fingerprint for e in newly_inferred_events])
  total_redundant = 0
  for fingerprint, count in expected_counts.iteritems():
    if fingerprint in inferred_counts and inferred_counts[fingerprint] > count:
      redundant = inferred_counts[fingerprint] - count
      total_redundant += redundant
      # fingerprints[0] is the class name
      Peeker.ambiguous_events[fingerprint[0]] += redundant

  if len(newly_inferred_events) > 0:
    percent_redundant = total_redundant*1.0 / len(newly_inferred_events)
  else:
    percent_redundant = 0.0
  Peeker.ambiguous_counts[percent_redundant] += 1

# Truncate the newly inferred events based on the expected
# predecessors of next_input+1
# inferred_events (and ignore internal events that come afterward)
# TODO(cs): perhaps these should be unordered
def match_fingerprints(newly_inferred_events, expected_internal_events):
  # Find the last internal event in expected_internal_events that
  # matches an event in newly_inferred_events. That is the new causal
  # parent of following_input
  expected_internal_events.reverse()
  inferred_fingerprints = set([e.fingerprint for e in
                               newly_inferred_events])
  if len(inferred_fingerprints) != len(newly_inferred_events):
    log.warn("Overlapping fingerprints in peek() (%d unique, %d total)" %
             (len(inferred_fingerprints),len(newly_inferred_events)))

  expected_fingerprints = set([e.fingerprint
                               for e in expected_internal_events])
  if len(expected_fingerprints) != len(expected_internal_events):
    log.warn("Overlapping expected fingerprints (%d unique, %d total)" %
             (len(expected_fingerprints),len(expected_internal_events)))

  for expected in expected_internal_events:
    if expected.fingerprint in inferred_fingerprints:
      # We've found our truncation point
      # following_input goes after the expected internal event
      # (we ignore all internal events that come after it)
      # TODO(cs): if the inferred events show up in a different order
      # than the expected events did originally, this algorithm might
      # inadvertently prune expected events (it assumes events are ordered)

      # If there are multiple matching fingerprints, find the instance of
      # the expected fingerprint (e.g., 2nd instance of the expected
      # fingerprint), and match it up with the same instance
      # of the inferred fingerprints
      expected_internal_events = [e for e in expected_internal_events
                                  if e.fingerprint == expected.fingerprint]
      # 1-based indexing of observed instances
      # Note that we are iterating through expected_internal_events in reverse
      # order
      instance_of_expected = len(expected_internal_events)
      observed_instance = 0
      idx_of_last_observed_instance = -1
      parent_index = -1
      for index, event in enumerate(newly_inferred_events):
        if event.fingerprint == expected.fingerprint:
          observed_instance += 1
          idx_of_last_observed_instance = index
          if observed_instance == instance_of_expected:
            parent_index = index
            break

      if parent_index == -1:
        log.warn(('''There were fewer instances of '''
                  '''inferred %s fingerprint than expected %s ''' %
                  (str(newly_inferred_events),str(expected_internal_events))))
        # Set parent_index to the index of the last occurrence
        parent_index = idx_of_last_observed_instance
      newly_inferred_events = newly_inferred_events[:parent_index+1]
      return newly_inferred_events
  # Else, no expected internal event was observed.
  return []

def correct_timestamps(new_events, old_events):
  ''' Set new_events' timestamps to approximately the same timestamp as
  old_events.

  Precondition: old_events != []
  '''
  # Lazy strategy: assign all new timestamps to the last timestamp of
  # old_events
  latest_old_ts = old_events[-1].time
  for e in new_events:
    e.time = latest_old_ts
  return new_events
