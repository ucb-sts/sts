'''
control flow for running the simulation forward.
  - Replayer: takes as input a `superlog` with causal dependencies, and
    iteratively prunes until the MCS has been found
'''

from sts.control_flow.interactive import Interactive
from sts.control_flow.event_scheduler import DumbEventScheduler, EventScheduler
from sts.replay_event import *
from sts.event_dag import EventDag
import sts.log_processing.superlog_parser as superlog_parser
from sts.util.console import color
from sts.control_flow.base import ControlFlow, ReplaySyncCallback
from sts.util.convenience import find
from sts.topology import BufferedPatchPanel

import signal
import sys
import time
import random
import logging

log = logging.getLogger("Replayer")

class Replayer(ControlFlow):
  '''
  Replay events from a `superlog` with causal dependencies, pruning as we go

  To set the event scheduling paramters, pass them as keyword args to the
  constructor of this class, which will pass them on to the EventScheduler object it creates.
  '''

  # Runtime stats:
  total_replays = 0
  total_inputs_replayed = 0
  # Interpolated time parameter. *not* the event scheduling epsilon:
  time_epsilon_microseconds = 500

  def __init__(self, simulation_cfg, superlog_path_or_dag, create_event_scheduler=None,
               print_buffers=True, wait_on_deterministic_values=False,
               fail_to_interactive=False, **kwargs):
    ControlFlow.__init__(self, simulation_cfg)
    if wait_on_deterministic_values:
      self.sync_callback = ReplaySyncCallback()
    else:
      self.sync_callback = ReplaySyncCallback(self.get_interpolated_time)

    if type(superlog_path_or_dag) == str:
      superlog_path = superlog_path_or_dag
      # The dag is codefied as a list, where each element has
      # a list of its dependents
      self.dag = EventDag(superlog_parser.parse_path(superlog_path))
    else:
      self.dag = superlog_path_or_dag

    self.dp_checker = DataplaneChecker(self.dag)

    self.print_buffers = print_buffers

    # compute interpolate to time to be just before first event
    self.compute_interpolated_time(self.dag.events[0])
    self.unexpected_state_changes = []
    self.early_state_changes = []
    self.event_scheduler_stats = None
    self.fail_to_interactive = fail_to_interactive

    if create_event_scheduler:
      self.create_event_scheduler = create_event_scheduler
    else:
      self.create_event_scheduler = \
        lambda simulation: EventScheduler(simulation,
            **{ k: v for k,v in kwargs.items()
                if k in EventScheduler.kwargs })

  def get_interpolated_time(self):
    '''
    During divergence, the controller may ask for the current time more or
    less times than they did in the original run. We control the time, so we
    need to give them some answer. The answers we give them should be
    (i) monotonically increasing, and (ii) between the time of the last
    recorded ("landmark") event and the next landmark event, and (iii)
    as close to the recorded times as possible

    Our temporary solution is to always return the time right before the next
    landmark
    '''
    # TODO(cs): implement Andi's improved time heuristic
    return self.interpolated_time

  def compute_interpolated_time(self, current_event):
    next_time = current_event.time
    just_before_micro = next_time.microSeconds - self.time_epsilon_microseconds
    just_before_micro = max(0, just_before_micro)
    self.interpolated_time = SyncTime(next_time.seconds, just_before_micro)

  def increment_round(self):
    msg.event(color.CYAN + ( "Round %d" % self.logical_time) + color.WHITE)
    pass

  def simulate(self, post_bootstrap_hook=None):
    ''' Caller *must* call simulation.clean_up() '''
    Replayer.total_replays += 1
    Replayer.total_inputs_replayed += len(self.dag.input_events)
    self.simulation = self.simulation_cfg.bootstrap(self.sync_callback)
    assert(isinstance(self.simulation.patch_panel, BufferedPatchPanel))
    ### TODO aw remove this hack
    self.simulation.fail_to_interactive = self.fail_to_interactive
    self.logical_time = 0
    self.run_simulation_forward(self.dag, post_bootstrap_hook)
    if self.print_buffers:
      self._print_buffers()
    return self.simulation

  def _print_buffers(self):
    log.debug("Pending Message Receives:")
    for p in self.simulation.god_scheduler.pending_receives():
      log.debug("- %s", p)
    log.debug("Pending State Changes:")
    for p in self.sync_callback.pending_state_changes():
      log.debug("- %s", p)

  def run_simulation_forward(self, dag, post_bootstrap_hook=None):
    event_scheduler = self.create_event_scheduler(self.simulation)
    self.event_scheduler_stats = event_scheduler.stats
    if post_bootstrap_hook is not None:
      post_bootstrap_hook()

    self.interrupted = False
    old_interrupt = None

    def interrupt(sgn, frame):
      msg.interactive("Interrupting replayer, dropping to console (press ^C again to terminate)")
      signal.signal(signal.SIGINT, self.old_interrupt)
      self.old_interrupt = None
      self.interrupted = True
      raise KeyboardInterrupt()
    self.old_interrupt = signal.signal(signal.SIGINT, interrupt)

    try:
      for i, event in enumerate(dag.events):
        try:
          self.logical_time += 1
          self.compute_interpolated_time(event)
          self.dp_checker.check_dataplane(i, self.simulation)
          if isinstance(event, InputEvent):
            self._check_early_state_changes(dag, i, event)
          self._check_new_state_changes(dag, i)
          # TODO(cs): quasi race-condition here. If unexpected state change
          # happens *while* we're waiting for event, we basically have a
          # deadlock (if controller logging is set to blocking) until the
          # timeout occurs
          event_scheduler.schedule(event)
          self.increment_round()
        except KeyboardInterrupt as e:
          if self.interrupted:
            interactive = Interactive(self.simulation_cfg)
            interactive.simulate(self.simulation, bound_objects=( ('replayer', self), ))
            self.old_interrupt = signal.signal(signal.SIGINT, interrupt)
          else:
            raise e
    finally:
      if self.old_interrupt:
        signal.signal(signal.SIGINT, self.old_interrupt)
      msg.event(color.B_BLUE+"Event Stats: %s" % str(event_scheduler.stats))
      msg.event(color.B_BLUE+"DataplaneDrop Stats: %s" % str(self.dp_checker.stats))

  def _check_early_state_changes(self, dag, current_index, input):
    ''' Check whether the any pending state change were supposed to come
    *after* the current input. If so, we have violated causality.'''
    pending_state_changes = self.sync_callback.pending_state_changes()
    if len(pending_state_changes) > 0:
      # TODO(cs): currently assumes a single controller (-> single pending state
      # change)
      state_change = pending_state_changes[0]
      next_expected = dag.next_state_change(current_index)
      original_input_index = dag.get_original_index_for_event(input)
      if (next_expected is not None and
          state_change == next_expected.pending_state_change and
          dag.get_original_index_for_event(next_expected) > original_input_index):
        raise RuntimeError("State change happened before expected! Causality violated")
        self.early_state_changes.append(repr(next_expected))

  def _check_new_state_changes(self, dag, current_index):
    ''' If we are blocking controllers, it's bad news bears if an unexpected
    internal state change occurs. Check if there are any, and ACK them so that
    the execution can proceed.'''
    pending_state_changes = self.sync_callback.pending_state_changes()
    if len(pending_state_changes) > 0:
      # TODO(cs): currently assumes a single controller (-> single pending state
      # change)
      state_change = pending_state_changes[0]
      next_expected = dag.next_state_change(current_index)
      if (next_expected is None or
          state_change != next_expected.pending_state_change):
        log.info("Unexpected state change. Ack'ing")
        self.unexpected_state_changes.append(repr(state_change))
        self.sync_callback.ack_pending_state_change(state_change)

# TODO(cs): should this go in event_scheduler.py?
class DataplaneChecker(object):
  ''' Dataplane permits are the default, *unless* they were explicitly dropped in the
  initial run. This class keeps track of whether pending dataplane events should
  be dropped or forwarded during replay'''
  def __init__(self, event_dag, slop_buffer=7):
    ''' Consider the position i of a DataplaneDrop in the original
    event ordering. slop_buffer defines how tolerant we are to differences in
    the position of the correspdonding DataplaneDrop event in the
    pruned run. A slop_buffer of 4 says that we will tolerate the same
    DataplaneDrop in the pruned run occuring in the range [i-4,i+4].
    If the corresponding DataplaneDrop occurs outside of this window, we won't
    detect it, and will treat it as a default DataplanePermit'''
    # Note it is not sufficient to simply track the entire list of drops/permits from
    # the original run, since the sequence of dataplane events may be different
    # in the pruned run.
    self.events = list(event_dag.events)
    self.stats = DataplaneCheckerStats(self.events)
    # The current sequence of dataplane events we expect within the current
    # window
    self.current_dp_fingerprints = []
    # Mapping from fingerprint in current_dp_fingerprints to the index of the
    # event in self.events
    self.fingerprint_2_event_idx = {}
    self.slop_buffer = slop_buffer

  def decide_drop(self, dp_event):
    ''' Returns True if this event should be dropped, False otherwise '''
    # dp_event is a DpPacketOut object
    # TODO(cs): should have a sanity check in here somewhere to make sure
    # we're still dropping the right number of packets. Test on a high drop
    # rate fuzzer_params
    dp_fingerprint = (DPFingerprint.from_pkt(dp_event.packet),
                      dp_event.node.dpid, dp_event.port.port_no)

    # Skip over the class name (first element of the tuple)
    event_fingerprint = find(lambda f: f[1:] == dp_fingerprint,
                             self.current_dp_fingerprints)
    if event_fingerprint is None:
      # Default to permit if we didn't expect this dp event
      return False
    # Flush this event from both our current window and our events list, so
    # that we don't accidentally conflate distinct dp_events with the same
    # fingerprint
    self.current_dp_fingerprints.remove(event_fingerprint)
    event_idx = self.fingerprint_2_event_idx[event_fingerprint]
    self.events.pop(event_idx)
    # First element of the tuple is the Event class name
    if event_fingerprint[0] == "DataplanePermit":
      return False
    self.stats.record_drop(event_fingerprint)
    return True # DataplaneDrop

  def update_window(self, current_event_idx):
    ''' Update the current slop buffer ("the dp_events we expect to see") '''
    self.current_dp_fingerprints = []
    self.fingerprint_2_event_idx = {}
    head_idx = max(current_event_idx - self.slop_buffer, 0)
    tail_idx = min(current_event_idx + self.slop_buffer, len(self.events))
    for i in xrange(head_idx, tail_idx):
      if (type(self.events[i]) == DataplanePermit or
          type(self.events[i]) == DataplaneDrop):
        fingerprint = self.events[i].fingerprint
        self.current_dp_fingerprints.append(fingerprint)
        self.fingerprint_2_event_idx[fingerprint] = i

  def check_dataplane(self, current_event_idx, simulation):
    ''' Check dataplane events for before playing then next event.
       - current_event_idx allows us to adjust our current slop buffer
    '''
    self.update_window(current_event_idx)

    for dp_event in simulation.patch_panel.queued_dataplane_events:
      if self.decide_drop(dp_event):
        simulation.patch_panel.drop_dp_event(dp_event)
      else:
        simulation.patch_panel.permit_dp_event(dp_event)

class DataplaneCheckerStats(object):
  ''' Tracks how many drops we actually performed vs. how many we expected to
  perform '''
  def __init__(self, events):
    self.expected_drops = [e.fingerprint for e in events if type(e) == DataplaneDrop]
    self.actual_drops = []

  def record_drop(self, fingerprint):
    self.actual_drops.append(fingerprint)

  def __str__(self):
    ''' Warning: not idempotent! '''
    s = ["Expected drops (%d), Actual drops (%d)" % (len(self.expected_drops),
                                                    len(self.actual_drops)) ]
    s.append("Missed Drops (expected if TrafficInjections pruned):")
    for drop in self.expected_drops:
      if len(self.actual_drops) == 0 or drop != self.actual_drops[0]:
        s.append("  %s" % str(drop))
      elif len(self.actual_drops) != 0 and drop == self.actual_drops[0]:
        self.actual_drops.pop(0)
    return "\n".join(s)
