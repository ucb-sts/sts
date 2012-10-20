from sts.input_traces.fingerprints import *
from sts.replay_event import *
from pox.openflow.software_switch import DpPacketOut
import sts.control_flow
import logging
import time
import math
from sys import maxint
from sts.util.convenience import find_index
log = logging.getLogger("event_dag")

class EventDag(object):
  # We peek ahead this many seconds after the timestamp of the subseqeunt
  # event
  # TODO(cs): be smarter about this -- peek() too far, and peek()'ing not far
  # enough can both have negative consequences
  _peek_seconds = 0.5
  # If we prune a failure, make sure that the subsequent
  # recovery doesn't occur
  _failure_types = set([SwitchFailure, LinkFailure, ControllerFailure, ControlChannelBlock])
  # NOTE: we treat failure/recovery as an atomic pair, since it doesn't make
  # much sense to prune a recovery event
  _recovery_types = set([SwitchRecovery, LinkRecovery, ControllerRecovery, ControlChannelUnblock])
  # For now, we're ignoring these input types, since their dependencies with
  # other inputs are too complicated to model
  # TODO(cs): model these!
  _ignored_input_types = set([DataplaneDrop, DataplanePermit, HostMigration,
                              WaitTime, CheckInvariants])

  '''A collection of Event objects. EventDags are primarily used to present a
  view of the underlying events with some subset of the input events pruned
  '''
  def __init__(self, events, is_view=False, prefix_trie=None,
               label2event=None, wait_time=0.05, max_rounds=None):
    '''events is a list of EventWatcher objects. Refer to log_parser.parse to
    see how this is assembled.'''
    self.wait_time=wait_time
    if type(max_rounds) == int:
      self.max_rounds = max_rounds
    else:
      self.max_rounds = maxint

    self._events_list = events
    self._events_set = set(self._events_list)
    self._populate_indices(label2event)

    # TODO(cs): there is probably a cleaner way to implement views
    if not is_view:
      try:
        import pytrie
      except ImportError:
        raise RuntimeError("Need to install pytrie: `sudo pip install pytrie`")
      prefix_trie = pytrie.Trie()
    # The prefix trie stores lists of input events as keys,
    # and lists of both input and internal events as values
    # Note that we pass the trie around between DAG views
    self._prefix_trie = prefix_trie

  def _populate_indices(self, label2event):
    #self._event_to_index = {
    #  e : i
    #  for i, e in enumerate(self._events_list)
    #}
    # Optimization: only compute label2event once (at the first unpruned
    # initialization)
    # TODO(cs): need to ensure that newly added events get labeled
    # uniquely. (Easy, but inelegant way: set the label generator's
    # initial value to max(labels) + 1)
    if label2event is None:
      self._label2event = {
        event.label : event
        for event in self._events_list
      }
    else:
      self._label2event = label2event

  def filter_unsupported_input_types(self):
    self._events_list = [ e for e in self._events_list
                          if type(e) not in self._ignored_input_types ]

  @property
  def events(self):
    '''Return the events in the DAG'''
    return self._events_list

  @property
  def event_watchers(self):
    '''Return a generator of the EventWatchers in the DAG'''
    for e in self._events_list:
      yield EventWatcher(e, wait_time=self.wait_time, max_rounds=self.max_rounds)

  def _remove_event(self, event):
    ''' Recursively remove the event and its dependents '''
    if event in self._events_set:
      # TODO(cs): This shifts other indices and screws up self._event_to_index!
      #list_idx = self._event_to_index[event]
      #del self._event_to_index[event]
      #self._events_list.pop(list_idx)
      self._events_list.remove(event)
      self._events_set.remove(event)

    # Note that dependent_labels only contains dependencies between input
    # events. We run peek() to infer dependencies with internal events
    for label in event.dependent_labels:
      if label in self._label2event:
        dependent_event = self._label2event[label]
        self._remove_event(dependent_event)

  def remove_events(self, ignored_portion, simulation):
    ''' Mutate the DAG: remove all input events in ignored_inputs,
    as well all of their dependent input events'''
    # Note that we treat failure/recovery as an atomic pair, so we don't prune
    # recovery events on their own
    for event in [ e for e in ignored_portion
                   if (isinstance(e, InputEvent) and
                       type(e) not in self._recovery_types) ]:
      self._remove_event(event)
    # Now run peek() to hide the internal events that will no longer occur
    # Note that causal dependencies change depending on what the prefix is!
    # So we have to run peek() once per prefix
    self.peek(simulation)

  def ignore_portion(self, ignored_portion, simulation):
    ''' Return a view of the dag with ignored_portion and its dependents
    removed'''
    dag = EventDag(list(self._events_list), is_view=True,
                   prefix_trie=self._prefix_trie,
                   label2event=self._label2event,
                   wait_time=self.wait_time, max_rounds=self.max_rounds)
    # TODO(cs): potentially some redundant computation here
    dag.remove_events(ignored_portion, simulation)
    return dag

  def split_inputs(self, split_ways):
    ''' Split our events into split_ways separate lists '''
    events = self._events_list
    if len(events) == 0:
      return [[]]
    if split_ways == 1:
      return [events]
    if split_ways < 1 or split_ways > len(events):
      raise ValueError("Invalid split ways %d" % split_ways)

    splits = []
    split_interval = int(math.ceil(len(events) * 1.0 / split_ways))
    start_idx = 0
    split_idx = start_idx + split_interval
    while start_idx < len(events):
      splits.append(events[start_idx:split_idx])
      start_idx = split_idx
      # Account for odd numbered splits -- if we're about to eat up
      # all elements even though we will only have added split_ways-1
      # splits, back up the split interval by 1
      if (split_idx + split_interval >= len(events) and
          len(splits) == split_ways - 2):
        split_interval -= 1
      split_idx += split_interval
    return splits

  def peek(self, simulation):
    ''' Infer which internal events are/aren't going to occur, '''
    # TODO(cs): optimization: write the prefix trie to a file, in case we want to run
    # FindMCS again?
    input_events = [ e for e in self._events_list if isinstance(e, InputEvent) ]
    if len(input_events) == 0:
      # Postcondition: input_events[-1] is not None
      #                and self._events_list[-1] is not None
      return

    # Note that we recompute wait times for every view, since the set of
    # inputs and intervening expected internal events changes
    def get_wait_times(input_events):
      idxrange2wait_seconds = {}
      for i in xrange(0, len(input_events)-1):
        start_input = input_events[i]
        next_input = input_events[i+1]
        wait_time = (next_input.time.as_float() -
                     start_input.time.as_float() + self._peek_seconds)
        idxrange2wait_seconds[(i,i+1)] = wait_time
      # For the last event, we wait until the last internal event
      last_wait_time = (self._events_list[-1].time.as_float() -
                        input_events[-1].time.as_float() +
                        self._peek_seconds)
      idxrange2wait_seconds[(len(input_events),len(input_events)+1] = last_wait_time
      return event2wait_time

    log.debug("Computing wait times")
    idxrange2wait_seconds = get_wait_times(input_events)

    def get_expected_internal_events(input1_index, input2_index, input_events):
      ''' Return previously observed internal events between input1_index and
      input2_index*

      *indices of input_events, not self._events_list

      input1_index may be before the beginning of input_events, in which
      case we return any input events before input2

      input2_index may also be past the end of input_events, in which case we return
      all internal events following input1
      '''
      if input1_index < 0:
        left_idx = 0
      else:
        left_sentinel = input_events[input1_index]
        left_idx = self._events_list.index(left_sentinel)

      if input2_index > len(input_events):
        right_idx = len(self._events_list)
      else:
        right_sentinel = input_events[input2_index]
        right_idx = self._events_list.index(right_sentinel)

      return [ i for i in self._events_list[left_idx:right_idx]
                 if isinstance(i, InternalEvent) ]

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

    # prefix_tail is the last input in the prefix
    if current_input_prefix == []:
      # We start by injecting the 0th input (not included in prefix)
      prefix_tail_idx = -1
    else:
      prefix_tail_idx = input_events.index(current_input_prefix[-1])

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
                                                              input_events)

      # Optimization: if no internal events occured between this input and the
      # next, no need to peek()
      if expected_internal_events == []:
        log.debug("Optimization: no expected internal events")
        # Only the input we've injected, no internal events following it
        newly_inferred_events = [inject_input]
      else:
        # Now actually do the peek()'ing!
        # First set the BufferedPatchPanel to "pass through"
        def pass_through_packets(event):
          simulation.patch_panel.permit_dp_event(event)
        def post_bootstrap_hook():
          simulation.patch_panel.addListener(DpPacketOut,
                                             pass_through_packets)
        # Now replay the prefix plus the next input
        prefix_dag = EventDag(inferred_events + [inject_input],
                              wait_time=self.wait_time,
                              max_rounds=self.max_rounds)
        replayer = sts.control_flow.Replayer(prefix_dag)
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
        simulation.god_scheduler.set_pass_through()
        simulation.controller_sync_callback.set_pass_through()

        # Now sit tight for wait_seconds
        idx_range = (inject_input_idx,following_input,idx)
        wait_seconds = idxrange2wait_seconds[idx_range]
        # Note that this is the monkey patched version of time.sleep
        log.debug("peek()'ing for %f seconds" % wait_seconds)
        time.sleep(wait_seconds)

        # Now turn off those pass-through and grab the inferred events
        # (starting with the input we injected)
        newly_inferred_events = [inject_input]
        newly_inferred_events += simulation.god_scheduler.unset_pass_through()
        newly_inferred_events += simulation.controller_sync_callback.unset_pass_through()

        # Finally, truncate the newly inferred events based on the expected
        # predecessors of next_input+1
        # inferred_events (and ignore internal events that come afterward)
        def match_fingerprints(newly_inferred_events, expected_internal_events):
          # Find the last internal event in expected_internal_events that
          # matches an event in newly_inferred_events. That is the new causal
          # parent of following_input
          expected_internal_events.reverse()
          inferred_fingerprints = set([e.fingerprint
                                       for e in newly_inferred_events])
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
              # 1-based indexing
              instance_of_expected = len(expected_internal_events)
              observed_instance = 0
              parent_index = -1
              for index, event in enumerate(newly_inferred_events):
                if event.fingerprint == expected.fingerprint:
                  observed_instance += 1
                  if observed_instance == instance_of_expected:
                    parent_index = index
                    break

              if parent_index == -1:
                raise NotImplementedError('''There were fewer instances of '''
                                          '''inferred %s fingerprint than expected %s ''' %
                                          (str(newly_inferred_events),str(expected_internal_events)))
              newly_inferred_events = newly_inferred_events[:parent_index+1]
              return newly_inferred_events
          # Else, no expected internal event was observed. Only return the
          # injected input (0th element)
          return newly_inferred_events[0:1]

        log.debug("Matching fingerprints")
        log.debug("Expected: %s" % str(expected_internal_events))
        log.debug("Inferred: %s" % str(newly_inferred_events))
        newly_inferred_events = match_fingerprints(newly_inferred_events,
                                                   expected_internal_events)
        log.debug("Matched events: %s" % str(newly_inferred_events))

      # Update the trie for this prefix
      current_input_prefix.append(inject_input)
      # Note that newly_inferred_events already includes current_input
      inferred_events += newly_inferred_events
      self._prefix_trie[current_input_prefix] = inferred_events

      prefix_tail_idx += 1

    # Now that the new execution has been inferred,
    # present a view of ourselves that only includes the updated
    # events
    self._events_list = inferred_events
    self._populate_indices(self._label2event)

  def mark_invalid_input_sequences(self):
    '''Fill in domain knowledge about valid input
    sequences (e.g. don't prune failure without pruning recovery.)
    Only do so if this isn't a view of a previously computed DAG'''

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

class EventWatcher(object):
  '''EventWatchers watch events. This class can be used to wrap either
  InternalEvents or ExternalEvents to perform pre and post functionality.'''

  kwargs = set(['wait_time', 'max_rounds'])

  def __init__(self, event, wait_time, max_rounds):
    assert(max_rounds > 0 and wait_time > 0)
    self.wait_time = wait_time
    self.max_rounds = max_rounds
    self.event = event

  def run(self, simulation):
    self._pre()
    round = 0

    while round < self.max_rounds and not self.event.proceed(simulation):
      time.sleep(self.wait_time)
      round += 1
      log.debug(".")

    self._post(round)

  def _pre(self):
    log.debug("Executing %s" % str(self.event))

  def _post(self, round):
    if round < self.max_rounds:
      log.debug("Finished Executing %s" % str(self.event))
    else:
      log.warn("Timing out waiting for Event %s" % str(self.event))
