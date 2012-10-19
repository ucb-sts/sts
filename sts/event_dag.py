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
      event2wait_time = {}
      for i in xrange(0, len(input_events)-1):
        current_input = input_events[i]
        next_input = input_events[i+1]
        wait_time = (next_input.time.as_float() - current_input.time.as_float()) + self._peek_seconds
        event2wait_time[current_input] = wait_time
      # For the last event, we wait until the last internal event
      last_wait_time = (self._events_list[-1].time.as_float() - input_events[-1].time.as_float()) + self._peek_seconds
      event2wait_time[input_events[-1]] = last_wait_time
      return event2wait_time

    log.debug("Computing wait times")
    event2wait_time = get_wait_times(input_events)

    # Also compute the internal events that we expect for each interval between
    # input events
    def get_expected_internal_events(input_events):
      input_to_expected_events = {}
      for i in xrange(0, len(input_events)-1):
        # Infer the internal events that we expect
        current_input = input_events[i]
        # TODO(cs): ineffient
        current_input_idx = self._events_list.index(current_input)
        next_input = input_events[i+1]
        next_input_idx = self._events_list.index(next_input)
        expected_internal_events = \
                self._events_list[current_input_idx+1:next_input_idx]
        input_to_expected_events[current_input] = expected_internal_events
      # The last input's expected internal events are anything that follow it
      # in the log.
      last_input = input_events[-1]
      last_input_idx = self._events_list.index(last_input)
      input_to_expected_events[last_input] = self._events_list[last_input_idx:]
      return input_to_expected_events

    log.debug("Computing expected internal events")
    input_to_expected_events = get_expected_internal_events(input_events)

    # Now, play the execution forward iteratively for each input event, and
    # record what internal events happen between the injection and the
    # wait_time

    # Initilize current_input_prefix to the longest_match prefix we've
    # inferred previously (or [] if this is an entirely new prefix)
    current_input_prefix = list(self._prefix_trie\
                               .longest_prefix(input_events, default=[]))

    log.debug("Current input prefix: %s" % str(current_input_prefix))
    # The value is both internal events and input events (values of the trie)
    # leading up to, but not including the next input following the tail of the prefix
    inferred_events = list(self._prefix_trie\
                          .longest_prefix_value(input_events, default=[]))

    # current_input is the next input after the tail of the prefix
    if current_input_prefix == []:
      current_input_idx = 0
    else:
      current_input_idx = input_events.index(current_input_prefix[-1]) + 1

    while current_input_idx < len(input_events):
      log.debug("Pruning input index %d" % current_input_idx)
      current_input = input_events[current_input_idx]
      expected_internal_events = input_to_expected_events[current_input]
      # Optimization: if no internal events occured between this input and the
      # next, no need to peek()
      if expected_internal_events == []:
        log.debug("Optimization: no expected internal events")
        newly_inferred_events = [current_input]
      else:
        # Now actually do the peek()'ing!
        # First set the BufferedPatchPanel to "pass through"
        def pass_through_packets(event):
          simulation.patch_panel.permit_dp_event(event)
        def post_bootstrap_hook():
          simulation.patch_panel.addListener(DpPacketOut,
                                             pass_through_packets)
        # Now replay the prefix plus the next input
        prefix_dag = EventDag(inferred_events + [current_input],
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
        wait_seconds = event2wait_time[current_input]
        # Note that this is the monkey patched version of time.sleep
        log.debug("peek()'ing for %f seconds" % wait_seconds)
        time.sleep(wait_seconds)

        # Now turn off those pass-through and grab the inferred events
        newly_inferred_events = []
        newly_inferred_events += simulation.god_scheduler.unset_pass_through()
        newly_inferred_events += simulation.controller_sync_callback.unset_pass_through()

        # Finally, insert current_input into the appropriate place in
        # inferred_events (and ignore internal events that come afterward)
        def match_fingerprints(newly_inferred_events, expected_internal_events):
          # Find the last internal event in expected_internal_events that
          # matches an event in newly_inferred_events. That is the new causal
          # parent of current_input
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
              # We've found our insertion point.
              # Insert the input after the expected internal event, and ignore all
              # internal events that come after it.

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
              newly_inferred_events.append(current_input)
              return newly_inferred_events
          # Else, no expected internal event was observed, so just insert
          # current_input by itself
          return [current_input]

        log.debug("Matching fingerprints")
        log.debug("Expected: %s" % str(expected_internal_events))
        log.debug("Inferred: %s" % str(newly_inferred_events))
        newly_inferred_events = match_fingerprints(newly_inferred_events,
                                                   expected_internal_events)
        log.debug("Matched events: %s" % str(newly_inferred_events))

      # Update the trie for this prefix
      current_input_prefix.append(current_input)
      # Note that newly_inferred_events already includes current_input
      inferred_events += newly_inferred_events
      self._prefix_trie[current_input_prefix] = inferred_events

      current_input_idx += 1

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
      if type(event) in self._failure_types:
        # Insert it into the previous failure hash
        fingerprint2previousfailure[event.fingerprint] = event
      elif type(event) in self._recovery_types:
        # Check if there were any failure predecessors
        if event.fingerprint in fingerprint2previousfailure:
          failure = fingerprint2previousfailure[event.fingerprint]
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
