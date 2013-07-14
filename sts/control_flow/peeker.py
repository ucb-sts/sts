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
from collections import Counter

from sts.event_dag import EventDag
from sts.control_flow.replayer import Replayer
from sts.replay_event import InternalEvent

log = logging.getLogger("sts")

class Peeker(object):
  # { % of inferred fingerprints that were ambiguous ->
  #   # of replays where this % occurred }
  ambiguous_counts = Counter()
  # { class of event -> # occurences of ambiguity }
  ambiguous_events = Counter()

  def __init__(self, simulation_cfg, default_wait_time_seconds=0.5, epsilon_time=0.2):
    try:
      import pytrie
    except ImportError:
      raise RuntimeError("Need to install pytrie: `sudo pip install pytrie`")
    # The prefix trie stores lists of input events as keys,
    # and lists of both input and internal events as values
    # Note that we pass the trie around between DAG views
    self.simulation_cfg = simulation_cfg
    self._prefix_trie = pytrie.Trie()
    self.default_wait_time_seconds = default_wait_time_seconds
    self.epsilon_time = epsilon_time

  def peek(self, dag):
    ''' Infer which internal events are/aren't going to occur, '''
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

      if inject_input_idx < len(input_events) - 1:
        # there is a following input_event
        following_input = input_events[inject_input_idx + 1]
      else:
        following_input = None

      # The input following the one we're going to inject
      log.debug("peek()'ing after input %d" %
                (inject_input_idx))

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
        newly_inferred_events = self.match_and_filter(found_events, expected_internal_events)

      (current_input_prefix,
       inferred_events) = self._update_trie(current_input_prefix, inject_input,
                                            inferred_events, newly_inferred_events)
      inject_input_idx += 1

    return EventDag(inferred_events)

  def get_wait_time_seconds(self, first_event, second_event):
    if first_event is None or second_event is None:
      return self.default_wait_time_seconds
    else:
      return second_event.time.as_float() - first_event.time.as_float() + \
          self.epsilon_time

  def find_internal_events(self, replay_dag, wait_time_seconds):
    ''' Replay the replay_dag, then wait for wait_time_seconds and collect internal
        events that occur. Return the list of internal events. '''
    replayer = Replayer(self.simulation_cfg, replay_dag)
    log.debug("Replaying prefix")
    simulation = replayer.simulate()

    # Directly after the last input has been injected, flush the internal
    # event buffers in case there were unaccounted internal events
    # Note that there isn't a race condition between flush()'ing and
    # incoming internal events, since sts is single-threaded
    # TODO(cs): flush() is not longer needed!
    simulation.god_scheduler.flush()
    simulation.controller_sync_callback.flush()

    # Now set all internal event buffers (GodScheduler for
    # ControlMessageReceives and ReplaySyncCallback for state changes)
    # to "pass through + record"
    simulation.set_pass_through()

    # Note that this is the monkey patched version of time.sleep
    log.debug("peek()'ing for %f seconds" % wait_time_seconds)
    time.sleep(wait_time_seconds)

    # Now turn off those pass-through and grab the inferred events
    newly_inferred_events = simulation.unset_pass_through()
    simulation.clean_up()
    return newly_inferred_events

  def match_and_filter(self, newly_inferred_events, expected_internal_events):
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
