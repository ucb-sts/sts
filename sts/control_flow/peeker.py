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

from sts.replay_event import *
from sts.event_dag import EventDag
from sts.control_flow.replayer import Replayer
from sts.control_flow.base import ReplaySyncCallback
from sts.control_flow.snapshot_utils import *
from sts.replay_event import InternalEvent, NOPInput
from sts.util.rpc_forker import LocalForker
from sts.util.convenience import find
from sts.input_traces.log_parser import parse

log = logging.getLogger("peeker")

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

  def __init__(self, simulation_cfg, default_wait_time_seconds=0.05,
               epsilon_time=0.05):
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
  def __init__(self, simulation_cfg, default_wait_time_seconds=0.05,
               epsilon_time=0.05, **kwargs):
    if len(simulation_cfg.controller_configs) != 1:
      raise ValueError("Only one controller supported for snapshotting")
    if simulation_cfg.controller_configs[0].sync is not None:
      raise ValueError("STSSyncProto currently incompatible with snapshotting")
    super(SnapshotPeeker, self).__init__(simulation_cfg,
                                         default_wait_time_seconds=default_wait_time_seconds,
                                         epsilon_time=epsilon_time)
    self.forker = LocalForker()
    if 'default_dp_permit' in kwargs and not kwargs['default_dp_permit']:
      raise ValueError('''Non-default DP Permit not currently supported '''
                       '''Please implement the TODO near the sleep() call '''
                       '''in play_forward()''')
    kwargs['default_dp_permit'] = True
    if 'pass_through_whitelisted_messages' not in kwargs:
      kwargs['pass_through_whitelisted_messages'] = False
    self.kwargs = kwargs
    unknown_kwargs = [ k for k in kwargs.keys() if k not in Replayer.kwargs ]
    if unknown_kwargs != []:
      raise ValueError("Unknown kwargs %s" % str(unknown_kwargs))

  def setup_simulation(self):
    # TODO(cs): currently assumes that STSSyncProto is not used alongside
    # snapshotting.
    # N.B. bootstrap() does not connect switches to controllers.
    # ConnectionToControllers is an input event, which we peek() for like
    # any other input event.
    simulation = self.simulation_cfg.bootstrap(ReplaySyncCallback(None))
    simulation.openflow_buffer.pass_through_whitelisted_packets = self.kwargs['pass_through_whitelisted_messages']
    controller = simulation.controller_manager.controllers[0]
    return (simulation, controller)

  def peek(self, dag):
    '''
    If dag.events == [], returns immediately.

    If dag.events != [], assumes that isinstance(dag.events[0], ConnectToControllers)
    '''
    if dag.input_events == []:
      return dag
    # post: len(dag.input_events) > 0

    unsupported_types = [ProcessFlowMod, DataplaneDrop]
    if find(lambda e: type(e) in unsupported_types, dag.events) is not None:
      raise ValueError('''Delayed flow_mods not yet supported. Please '''
                       '''implement the TODO near the sleep() call in play_forward()''')

    if not isinstance(dag.events[0], ConnectToControllers):
      raise ValueError("First event must be ConnectToControllers")

    simulation = None
    try:
      # Inferred events includes input events and internal events
      inferred_events = []

      (simulation, controller) = self.setup_simulation()

      # dag.input_events returns only prunable input events. We also need
      # include ConnectToControllers, which is a non-prunable input event.
      assert(dag.input_events[0] != dag.events[0])
      snapshot_inputs = [dag.events[0]] + dag.input_events

      # The input event from the previous iteration, followed by the internal
      # events that were inferred from the previous peek().
      # Since we assume that the first event is always ConnectToControllers,
      # there are never internal events (nor input events) preceding the
      # initial ConnectToControllers.
      # TODO(cs): might not want to contrain the caller's dag in this way.
      events_inferred_last_iteration = []

      for inject_input_idx in xrange(0, len(snapshot_inputs)):
        inject_input = get_inject_input(inject_input_idx, snapshot_inputs)
        following_input = get_following_input(inject_input_idx, snapshot_inputs)
        expected_internal_events = \
           get_expected_internal_events(inject_input, following_input, dag.events)

        log.debug("peek()'ing after input %d (%s)" %
                  (inject_input_idx, str(inject_input)))

        inferred_events += events_inferred_last_iteration

        # We replay events_inferred_last_iteration (internal events preceding
        # inject_input), as well as a NOPInput with the same timestamp as inject_input
        # to ensure that the timing is the same before peek()ing.
        fencepost = NOPInput(time=inject_input.time, round=inject_input.round)
        dag_interval = EventDag(events_inferred_last_iteration + [fencepost])

        if expected_internal_events == []:
          # Optimization: if no internal events occured between this input and the
          # next, no need to peek(), just bring the simulation's state forward up to
          # inject_input
          log.debug("Optimization: no expected internal events")
          Peeker.ambiguous_counts[0.0] += 1
          self.replay_interval(simulation, dag_interval, 0)
          events_inferred_last_iteration = [inject_input]
          continue

        wait_time_seconds = self.get_wait_time_seconds(inject_input, following_input)
        (found_events, snapshotter) = self.find_internal_events(simulation, controller,
                                                                dag_interval, inject_input,
                                                                wait_time_seconds)
        events_inferred_last_iteration = [inject_input]
        events_inferred_last_iteration += match_and_filter(found_events, expected_internal_events)
        snapshotter.snapshot_proceed()

      # Don't forget the final iteration's output
      inferred_events += events_inferred_last_iteration
    finally:
      if simulation is not None:
        simulation.clean_up()

    return EventDag(inferred_events)

  def replay_interval(self, simulation, dag_interval, initial_wait_seconds):
    assert(dag_interval.events != [])
    # TODO(cs): set EventScheduler's epsilon_seconds parameter?
    replayer = Replayer(self.simulation_cfg, dag_interval,
                        initial_wait=initial_wait_seconds,
                        **self.kwargs)
    replayer.simulation = simulation
    if 'pass_through_sends' in self.kwargs and self.kwargs['pass_through_sends']:
      replayer.set_pass_through_sends(simulation)
    replayer.run_simulation_forward()

  def find_internal_events(self, simulation, controller, dag_interval,
                           inject_input, wait_time_seconds):
    initial_wait_seconds = (inject_input.time.as_float() -
                            dag_interval.events[-1].time.as_float())
    self.replay_interval(simulation, dag_interval, initial_wait_seconds)
    # Now peek() for internal events following inject_input
    return self.snapshot_and_play_forward(simulation, controller,
                                          inject_input, wait_time_seconds)

  def snapshot_and_play_forward(self, simulation, controller, inject_input, wait_time_seconds):
    snapshotter = Snapshotter(simulation, controller)
    snapshotter.snapshot_controller()

    # Here we also fork() ourselves (the network simulator), since we need
    # switches to respond to messages, and potentially change their state in
    # order to properly peek().
    # TODO(cs): I believe that to be technically correct we need to use Chandy-Lamport
    # here, since STS + POX = a distributed system.
    def play_forward_and_marshal():
      # Can't marshal the simulation object, so use this method as a closure
      # instead.
      # N.B. depends on LocalForker() -- cannot be used with RemoteForker().
      # TODO(cs): even though DataplaneDrops are technically InputEvents, they
      # may time out, and we might do well to try to infer this somehow.
      found_events = play_forward(simulation, inject_input, wait_time_seconds)
      # TODO(cs): DataplaneDrops are a special case of an InputEvent that may
      # time out. We should check whether the input for this peek() was a
      # DataplaneDrop, and return whether it timed out.
      return [ e.to_json() for e in found_events ]

    self.forker.register_task("snapshot_fork_task", play_forward_and_marshal)
    # N.B. play_forward cleans up the simulation, including snaphotted controller
    unmarshalled_found_events = self.forker.fork("snapshot_fork_task")
    found_events = parse(unmarshalled_found_events)

    # Finally, bring the controller back to the state it was at just after
    # injecting inject_input
    # N.B. this must be invoked in the parent process (not a forker.fork()ed
    # child), since it mutates class variables in Controller.
    return (found_events, snapshotter)

class PrefixPeeker(Peeker):
  ''' O(n^2) peeker that replays each prefix of the subseqeuence from the beginning. '''
  def __init__(self, simulation_cfg, default_wait_time_seconds=0.05,
               epsilon_time=0.05):
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
    if len(dag.input_events) == 0:
      # Postcondition: input_events[-1] is not None
      #                and self._events_list[-1] is not None
      return dag

    # dag.input_events returns only prunable input events. We also need
    # include ConnectToControllers, which is a non-prunable input event.
    if not isinstance(dag.events[0], ConnectToControllers):
      raise ValueError("First event must be ConnectToControllers")
    assert(dag.input_events[0] != dag.events[0])
    input_events = [dag.events[0]] + dag.input_events

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
        # We inject a NOPInput with the same timestamp as inject_input
        # to ensure that the timing is the same before peek()ing, then replay
        # inject_input in play_forward()
        fencepost = NOPInput(time=inject_input.time, round=inject_input.round)
        replay_dag = EventDag(inferred_events + [ fencepost ])
        found_events = self.find_internal_events(replay_dag, inject_input, wait_time_seconds)
        newly_inferred_events = match_and_filter(found_events, expected_internal_events)

      (current_input_prefix,
       inferred_events) = self._update_trie(current_input_prefix, inject_input,
                                            inferred_events, newly_inferred_events)
      inject_input_idx += 1

    return EventDag(inferred_events)

  def find_internal_events(self, replay_dag, inject_input, wait_time_seconds):
    ''' Replay the replay_dag, then wait for wait_time_seconds and collect internal
        events that occur. Return the list of internal events. '''
    replayer = Replayer(self.simulation_cfg, replay_dag)
    log.debug("Replaying prefix")
    simulation = replayer.simulate()
    newly_inferred_events = play_forward(simulation, inject_input, wait_time_seconds)
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

def play_forward(simulation, inject_input, wait_time_seconds, flush_buffers=False):
  # Directly before the last input has been injected, flush the internal
  # event buffers in case there were unaccounted internal events
  # Note that there isn't a race condition between flush()'ing and
  # incoming internal events, since sts is single-threaded
  # TODO(cs): flush() is no longer needed!
  if flush_buffers:
    simulation.openflow_buffer.flush()
    simulation.controller_sync_callback.flush()

  # Now set all internal event buffers (GodScheduler for
  # ControlMessageReceives and ReplaySyncCallback for state changes)
  # to "pass-through and record"
  simulation.set_pass_through()

  # we inject input after setting pass_through, since some internal
  # events may occur immediately after the input is injected.
  log.info("Injecting input %s" % str(inject_input))
  inject_input.proceed(simulation)

  # Note that this is the monkey patched version of time.sleep
  # TODO(cs): should we subtract the time it took to inject input from
  # wait_time_seconds?
  log.info("peek()'ing for %f seconds" % wait_time_seconds)
  start_time = time.time()
  while time.time() - start_time < wait_time_seconds:
    # Allow through dataplane sends
    for dp_event in simulation.patch_panel.queued_dataplane_events:
      # TODO(cs): record these DataplanePermits rather than enforcing
      # default_dp_permit=True.
      simulation.patch_panel.permit_dp_event(dp_event)
    time.sleep(0.01)

  # Now turn off pass through and grab the inferred events
  newly_inferred_events = simulation.unset_pass_through()
  # Finally, clean up.
  simulation.clean_up()
  log.debug("Recorded %d events" % len(newly_inferred_events))
  return newly_inferred_events

def match_and_filter(newly_inferred_events, expected_internal_events):
  expected_internal_events = [ e for e in expected_internal_events
                               if not isinstance(e, DataplanePermit) ]
  newly_inferred_events = [ e for e in newly_inferred_events
                            if not isinstance(e, DataplanePermit) ]
  log.debug("Matching fingerprints")
  log.info("Expected total: %d" % (len(expected_internal_events)))
  log.info("Inferred total: %d" % (len(newly_inferred_events)))
  if log.getEffectiveLevel() <= logging.DEBUG:
    log.debug("Expected: %s" % (str(expected_internal_events)))
    log.debug("Inferred: %s" % (str(newly_inferred_events)))

  (newly_inferred_events, unmatched_events) = match_fingerprints(newly_inferred_events,
                                                                 expected_internal_events)
  #count_overlapping_fingerprints(newly_inferred_events,
  #                               expected_internal_events)
  # TODO(cs): correct timestamps of unexpected internal events.
  #newly_inferred_events = correct_timestamps(newly_inferred_events,
  #                                           expected_internal_events)

  if log.getEffectiveLevel() <= logging.DEBUG:
    log.debug("Matched events: %s" % (str(newly_inferred_events)))
    log.debug("Unmatched events: %s" % (str(unmatched_events)))

  log.info("Matched events total: %d" % (len(newly_inferred_events)))
  log.info("Unmatched events total: %d" % (len(unmatched_events)))
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

def deprecated_match_fingerprints(newly_inferred_events, expected_internal_events):
  ''' Deprecated. '''
  # Truncate the newly inferred events based on the expected
  # predecessors of next_input+1
  # inferred_events (and ignore internal events that come afterward)

  # TODO(cs): need to prune any successors of e_i, in case we waited too
  # long

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

def match_fingerprints(newly_inferred_events, expected_internal_events):
  # TODO(cs): we currently enforce something stronger than
  # happens-before: we enforce a total ordering of events (the serial order
  # recorded in the original trace). I wonder if enforcing a
  # partial ordering would make replay more effective?
  # N.B. expected_internal_events are ordered, whereas newly_inferred_events
  # may not be.
  inferred_fingerprints = Counter([e.fingerprint for e in newly_inferred_events])

  # N.B. to allow unexpected messages through after peek() has finished, set
  # Replayer's "allow_unexpected_messages" parameter.
  ordered_inferred_events = []
  unmatched_events = []
  for e in expected_internal_events:
    if e.fingerprint in inferred_fingerprints:
      ordered_inferred_events.append(e)
      inferred_fingerprints[e.fingerprint] -= 1
      if inferred_fingerprints[e.fingerprint] == 0:
        del inferred_fingerprints[e.fingerprint]
    else:
      unmatched_events.append(e)
  return (ordered_inferred_events, unmatched_events)

def correct_timestamps(new_events, old_events):
  ''' Set new_events' timestamps to approximately the same timestamp as
  old_events.

  Precondition: old_events != []
  '''
  # Lazy strategy: assign all new timestamps to the last timestamp of
  # old_events
  # TODO(cs): match up more carefully, since the timestamps affect how long
  # EventScheduler waits.
  latest_old_ts = old_events[-1].time
  for e in new_events:
    e.time = latest_old_ts
  return new_events
