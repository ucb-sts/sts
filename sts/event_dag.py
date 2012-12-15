from sts.fingerprints.messages import *
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
  _ignored_input_types = set([DataplaneDrop, WaitTime, DataplanePermit])

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

    # keep track of the most recent location of the host that did not involve
    # a pruned HostMigration event
    # location is: (ingress dpid, ingress port no)
    currentloc2unprunedloc = {}

    for m in [e for e in events_list if type(e) == HostMigration]:
      src = (m.old_ingress_dpid, m.old_ingress_port_no)
      dst = (m.new_ingress_dpid, m.new_ingress_port_no)
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
          (old_dpid, old_port) = currentloc2unprunedloc[src]
          del currentloc2unprunedloc[src]
          (new_dpid, new_port) = dst
          # Don't mutate m -- instead, replace m
          new_migration = HostMigration(old_dpid, old_port, new_dpid,
                                        new_port, time=m.time, label=m.label)
          index = remaining.index(m)
          remaining[index] = new_migration

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

  def __len__(self):
    return len(self._events_list)


