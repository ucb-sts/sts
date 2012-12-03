from sts.input_traces.fingerprints import *
from sts.replay_event import *
from pox.openflow.software_switch import DpPacketOut
import logging
import time
import math
from sys import maxint
from sts.util.convenience import find_index
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
    return [ e for e in self._events_list if isinstance(e, InputEvent) ]

  def input_subset(self, subset):
    '''pre: subset must be a subset of only this view'''
    return self._parent.input_subset(subset)

  def input_complement(self, subset):
    return self._parent.input_complement(subset, self._events_list)


  def __len__(self):
    return len(self._events_list)

  # TODO(cs): refactor caller of prepare()
  def prepare_for_replay(self, unused_simulation):
    pass

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
  _failure_types = set([SwitchFailure, LinkFailure, ControllerFailure, ControlChannelBlock])
  # NOTE: we treat failure/recovery as an atomic pair, since it doesn't make
  # much sense to prune a recovery event
  _recovery_types = set([SwitchRecovery, LinkRecovery, ControllerRecovery, ControlChannelUnblock])
  # For now, we're ignoring these input types, since their dependencies with
  # other inputs are too complicated to model
  # TODO(cs): model these!
  _ignored_input_types = set([DataplaneDrop, WaitTime, DataplanePermit, HostMigration, CheckInvariants])

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

  @property
  def events(self):
    '''Return the events in the DAG'''
    return self._events_list

  @property
  def input_events(self):
    # TODO(cs): memoize?
    return [ e for e in self._events_list if isinstance(e, InputEvent) ]

  def filter_unsupported_input_types(self):
    return EventDagView(self, (e for e in self._events_list
                              if type(e) not in self._ignored_input_types))

  def compute_remaining_input_events(self, ignored_portion, events_list=None):
    ''' ignore all input events in ignored_inputs,
    as well all of their dependent input events'''
    if events_list is None:
      events_list = self.events
    # Note that dependent_labels only contains dependencies between input
    # events. Dependencies with internal events are inferred by EventScheduler.
    # Also note that we treat failure/recovery as an atomic pair, so we don't prune
    # recovery events on their own
    ignored_portion = set(e for e in ignored_portion
                          if (isinstance(e, InputEvent) and
                              type(e) not in self._recovery_types))
    remaining = []
    for event in events_list:
      if event not in ignored_portion:
        remaining.append(event)
      else:
        # Add dependent to ignored_portion
        for label in event.dependent_labels:
          dependent_event = self._label2event[label]
          ignored_portion.add(dependent_event)
    return remaining

  def input_subset(self, subset):
    ''' Return a view of the dag with only the subset dependents
    removed'''
    ignored = self._events_set - set(subset)
    remaining_events = self.compute_remaining_input_events(ignored)
    return EventDagView(self, remaining_events)

  def input_complement(self, subset, events_list=None):
    ''' Return a view of the dag with only the subset dependents
    removed'''
    remaining_events = self.compute_remaining_input_events(subset, events_list)
    return EventDagView(self, remaining_events)

  def mark_invalid_input_sequences(self):
    '''Fill in domain knowledge about valid input
    sequences (e.g. don't prune failure without pruning recovery.)
    Only do so if this isn't a view of a previously computed DAG'''

    # TODO(cs): should this be factored out?

    # Note: we treat each failure/recovery pair atomically, since it doesn't
    # make much sense to prune recovery events. Also note that that we will
    # never see two failures (for a particular node) in a row without an
    # interleaving recovery event
    fingerprint2previousfailure = {}

    # NOTE: mutates self._events
    for event in self._events_list:
      # Skip over the class name
      if hasattr(event, 'fingerprint'):
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

  def __len__(self):
    return len(self._events_list)

def get_expected_internal_events(input1_index, input2_index, input_events,
                                 events_list):
  ''' Return previously observed internal events between input1_index and
  input2_index*

  *indices of input_events, not events_list

  input1_index may be before the beginning of input_events, in which
  case we return any input events before input2

  input2_index may also be past the end of input_events, in which case we return
  all internal events following input1
  '''
  if input1_index < 0:
    left_idx = 0
  else:
    left_sentinel = input_events[input1_index]
    left_idx = events_list.index(left_sentinel)

  if input2_index >= len(input_events):
    right_idx = len(events_list)
  else:
    right_sentinel = input_events[input2_index]
    right_idx = events_list.index(right_sentinel)

  return [ i for i in events_list[left_idx:right_idx]
             if isinstance(i, InternalEvent) ]

# Note that we recompute wait times for every view, since the set of
# inputs and intervening expected internal events changes
def get_wait_times(input_events, events_list,
                   peek_seconds=EventDag._peek_seconds):
  idxrange2wait_seconds = {}
  for i in xrange(0, len(input_events)-1):
    start_input = input_events[i]
    next_input = input_events[i+1]
    wait_time = (next_input.time.as_float() -
                 start_input.time.as_float() + peek_seconds)
    idxrange2wait_seconds[(i,i+1)] = wait_time
  # For the last event, we wait until the last internal event
  last_wait_time = (events_list[-1].time.as_float() -
                    input_events[-1].time.as_float() +
                    peek_seconds)
  final_idx_range = (len(input_events)-1,len(input_events))
  idxrange2wait_seconds[final_idx_range] = last_wait_time
  return idxrange2wait_seconds

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

def get_prefix_tail_idx(current_input_prefix, input_events):
  # prefix_tail is the last input in the prefix
  if current_input_prefix == []:
    # We start by injecting the 0th input (not included in prefix)
    prefix_tail_idx = -1
  else:
    prefix_tail_idx = input_events.index(current_input_prefix[-1])
  return prefix_tail_idx

def actual_peek(simulation, inferred_events, inject_input, wait_time,
                inject_input_idx, following_input_idx,
                idxrange2wait_seconds, expected_internal_events,
                switch_init_sleep_seconds):
  ''' Do the peek()'ing! '''
  # First set the BufferedPatchPanel to "pass through"
  def pass_through_packets(event):
    simulation.patch_panel.permit_dp_event(event)
  def post_bootstrap_hook():
    simulation.patch_panel.addListener(DpPacketOut,
                                       pass_through_packets)
  # Now replay the prefix plus the next input
  prefix_dag = PeekingEventDag(inferred_events + [inject_input],
                               wait_time=wait_time,
                               switch_init_sleep_seconds=switch_init_sleep_seconds)
  # Avoid circular dependencies!
  from sts.control_flow import Replayer
  replayer = Replayer(prefix_dag,
                      switch_init_sleep_seconds=switch_init_sleep_seconds)
  log.debug("Replaying prefix")
  replayer.simulate(simulation, post_bootstrap_hook=post_bootstrap_hook)

  # Directly after the last input has been injected, flush the internal
  # event buffers in case there were unaccounted internal events
  # Note that there isn't a race condition between flush()'ing and
  # incoming internal events, since sts is single-threaded
  simulation.god_scheduler.flush()
  simulation.controller_sync_callback.flush()

  # Now set all internal event buffers (GodScheduler for
  # ControlMessageReceives and ReplaySyncCallback for state changes)
  # to "pass through + record"
  simulation.set_pass_through()

  # Now sit tight for wait_seconds
  idx_range = (inject_input_idx,following_input_idx)
  wait_seconds = idxrange2wait_seconds[idx_range]
  # Note that this is the monkey patched version of time.sleep
  log.debug("peek()'ing for %f seconds" % wait_seconds)
  time.sleep(wait_seconds)

  # Now turn off those pass-through and grab the inferred events
  newly_inferred_events = simulation.unset_pass_through()

  log.debug("Matching fingerprints")
  log.debug("Expected: %s" % str(expected_internal_events))
  log.debug("Inferred: %s" % str(newly_inferred_events))
  newly_inferred_events = match_fingerprints(newly_inferred_events,
                                             expected_internal_events)
  log.debug("Matched events: %s" % str(newly_inferred_events))
  return newly_inferred_events


class PeekingEventDag(object):
  def __init__(self, events, **kwargs):
    super(PeekingEventDag, self).__init__(events, **kwargs)
    try:
      import pytrie
    except ImportError:
      raise RuntimeError("Need to install pytrie: `sudo pip install pytrie`")
    # The prefix trie stores lists of input events as keys,
    # and lists of both input and internal events as values
    # Note that we pass the trie around between DAG views
    self._prefix_trie = pytrie.Trie()

  def prepare_for_replay(self, simulation):
    '''Perform whatever computation we need to prepare our internal/external
    events for replay '''
    # Now run peek() to hide the internal events that will no longer occur
    # Note that causal dependencies change depending on what the prefix is!
    # So we have to run peek() once per prefix
    self.peek(simulation)

  def peek(self, simulation):
    ''' Infer which internal events are/aren't going to occur, '''
    # TODO(cs): optimization: write the prefix trie to a file, in case we want to run
    # FindMCS again?
    input_events = self.input_events

    if len(input_events) == 0:
      # Postcondition: input_events[-1] is not None
      #                and self._events_list[-1] is not None
      return

    log.debug("Computing wait times")
    idxrange2wait_seconds = get_wait_times(input_events, self._events_list)

    # Now, play the execution forward iteratively for each input event, and
    # record what internal events happen between the injection and the
    # wait_time

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

    prefix_tail_idx = get_prefix_tail_idx(current_input_prefix, input_events)

    # While we still have inputs to inject
    while prefix_tail_idx + 1 < len(input_events):
      # The input we're about to inject
      inject_input_idx = prefix_tail_idx + 1
      inject_input = input_events[inject_input_idx]
      # The input following the one we're going to inject
      following_input_idx = inject_input_idx + 1
      log.debug("peek()'ing between input %d and %d" %
                (inject_input_idx, following_input_idx))
      expected_internal_events = get_expected_internal_events(inject_input_idx,
                                                              following_input_idx,
                                                              input_events,
                                                              self._events_list)

      # Optimization: if no internal events occured between this input and the
      # next, no need to peek()
      if expected_internal_events == []:
        log.debug("Optimization: no expected internal events")
        newly_inferred_events = []
      else:
        newly_inferred_events = actual_peek(simulation, inferred_events,
                                            inject_input, self.wait_time,
                                            inject_input_idx,
                                            following_input_idx,
                                            idxrange2wait_seconds,
                                            expected_internal_events,
                                            self._switch_init_sleep_seconds)

      (current_input_prefix,
       inferred_events) = self._update_trie(current_input_prefix, inject_input,
                                            inferred_events, newly_inferred_events)
      prefix_tail_idx += 1

    # Now that the new execution has been inferred,
    # present a view of ourselves that only includes the updated
    # events
    self._events_list = inferred_events
    self._populate_indices(self._label2event)

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

