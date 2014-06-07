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

'''
control flow for running the simulation forward.
  - Replayer: takes as input a `superlog` with causal dependencies, and
    iteratively prunes until the MCS has been found
'''

from sts.replay_event import InvariantViolation
from sts.control_flow.interactive import Interactive
from sts.control_flow.event_scheduler import EventScheduler
from sts.replay_event import *
from sts.event_dag import EventDag
import sts.input_traces.log_parser as log_parser
from sts.util.console import color
from sts.control_flow.base import ControlFlow, ReplaySyncCallback
from sts.util.convenience import find, find_index, base64_encode
from sts.topology import BufferedPatchPanel
from sts.entities import FuzzSoftwareSwitch
from config.invariant_checks import name_to_invariant_check

import signal
import logging
import time
import sys
from collections import defaultdict

log = logging.getLogger("Replayer")

class Replayer(ControlFlow):
  '''
  Replay events from a trace

  To set the event scheduling parameters, pass them as keyword args to the
  constructor of this class, which will pass them on to the EventScheduler object it creates.
  '''

  # Interpolated time parameter. *not* the event scheduling epsilon:
  time_epsilon_microseconds = 500

  kwargs = EventScheduler.kwargs | set(['create_event_scheduler', 'print_buffers',
                'wait_on_deterministic_values', 'default_dp_permit',
                'fail_to_interactive', 'fail_to_interactive_on_persistent_violations',
                'end_in_interactive', 'input_logger',
                'allow_unexpected_messages',
                'expected_message_round_window',
                'pass_through_whitelisted_messages',
                'delay_flow_mods', 'invariant_check_name',
                'bug_signature', 'end_wait_seconds',
                'transform_dag', 'pass_through_sends'])

  def __init__(self, simulation_cfg, superlog_path_or_dag, create_event_scheduler=None,
               print_buffers=True, wait_on_deterministic_values=False, default_dp_permit=False,
               fail_to_interactive=False, fail_to_interactive_on_persistent_violations=False,
               end_in_interactive=False, input_logger=None,
               allow_unexpected_messages=False,
               expected_message_round_window=3,
               pass_through_whitelisted_messages=False,
               delay_flow_mods=False, invariant_check_name="",
               bug_signature="", end_wait_seconds=0.5,
               transform_dag=None, pass_through_sends=False,
               **kwargs):
    '''
     - If invariant_check_name is not None, check it at the end for the
       execution
     - If bug_signature is not None, check whether this particular signature
       appears in the output of the invariant check at the end of the
       execution
    '''
    ControlFlow.__init__(self, simulation_cfg)
    # Label uniquely identifying this replay, set in init_results()
    self.replay_id = "N/A"
    self.logical_time = 0
    if wait_on_deterministic_values:
      self.sync_callback = ReplaySyncCallback()
    else:
      self.sync_callback = ReplaySyncCallback(self.get_interpolated_time)

    if type(superlog_path_or_dag) == str:
      superlog_path = superlog_path_or_dag
      # The dag is codefied as a list, where each element has
      # a list of its dependents
      self.dag = EventDag(log_parser.parse_path(superlog_path))
    else:
      self.dag = superlog_path_or_dag

    if len(self.dag.events) == 0:
      raise ValueError("No events to replay!")

    self.default_dp_permit = default_dp_permit
    self.dp_checker = self._setup_dp_checker(default_dp_permit)
    if self.default_dp_permit:
      # Set DataplanePermit and DataplaneDrop to passive if permit is set
      # to default
      # TODO(cs): rather than setting these to passive (which still causes them to
      # be scheduled as regular events) should these just be removed from the
      # event dag altogether?
      for event in [ e for e in self.dag.events if type(e) in dp_events ]:
        event.passive = default_dp_permit

    self.print_buffers_flag = print_buffers

    # compute interpolate to time to be just before first event
    self.compute_interpolated_time(self.dag.events[0])
    # String repesentations of unexpected state changes we've passed through, for
    # statistics purposes.
    self.unexpected_state_changes = []
    self.early_state_changes = []
    self.event_scheduler_stats = None
    self.end_in_interactive = end_in_interactive
    self.fail_to_interactive = fail_to_interactive
    self.fail_to_interactive_on_persistent_violations =\
      fail_to_interactive_on_persistent_violations
    self._input_logger = input_logger
    self.allow_unexpected_messages = allow_unexpected_messages
    self.expected_message_round_window = expected_message_round_window
    self.pass_through_whitelisted_messages = pass_through_whitelisted_messages
    self.pass_through_sends = pass_through_sends
    # How many logical rounds to peek ahead when deciding if a message is
    # expected or not.
    # String repesentations of unexpected messages we've passed through, for
    # statistics purposes.
    self.passed_unexpected_messages = []
    self.delay_flow_mods = delay_flow_mods
    self.end_wait_seconds = end_wait_seconds
    self.transform_dag = transform_dag
    self.bug_signature = bug_signature
    self.invariant_check_name = invariant_check_name
    self.invariant_check = None
    if self.invariant_check_name:
      if self.invariant_check_name not in name_to_invariant_check:
        raise ValueError('''Unknown invariant check %s.\n'''
                         '''Invariant check name must be defined in config.invariant_checks''',
                         self.invariant_check_name)
      self.invariant_check = name_to_invariant_check[self.invariant_check_name]

    if self.pass_through_whitelisted_messages:
      for event in self.dag.events:
        if hasattr(event, "ignore_whitelisted_packets"):
          event.ignore_whitelisted_packets = True

    if self.simulation_cfg.ignore_interposition:
      self._ignore_interposition()

    if create_event_scheduler:
      self.create_event_scheduler = create_event_scheduler
    else:
      if self.default_dp_permit:
        # Tell EventScheduler to use call into us whenever it wants to sleep or
        # select, so that we can keep forwarding dataplane packets.
        kwargs['sleep_continuation'] = self._sleep_with_dataplane_passthrough
        kwargs['select_continuation'] = self._select_with_dataplane_passthrough

      self.create_event_scheduler = \
        lambda simulation: EventScheduler(simulation,
            **{ k: v for k,v in kwargs.items()
                if k in EventScheduler.kwargs })

    unknown_kwargs = [ k for k in kwargs.keys() if k not in EventScheduler.kwargs ]
    if unknown_kwargs != []:
      raise ValueError("Unknown kwargs %s" % str(unknown_kwargs))

  def _log_input_event(self, event, **kws):
    if self._input_logger is not None:
      self._input_logger.log_input_event(event, **kws)

  def _setup_dp_checker(self, default_dp_permit):
    no_dp_drops = [ e for e in self.dag.events if type(e) == DataplaneDrop ] == []
    if not default_dp_permit and no_dp_drops:
      print >> sys.stderr, ('''No DataplaneDrops to replay. We suggest you '''
                            '''set Replayer's default_dp_permit=True ''')
    if default_dp_permit:
      if no_dp_drops:
        return AlwaysAllowDataplane(self.dag)
      else:
        return DataplaneChecker(self.dag)
    return None

  def _ignore_interposition(self):
    '''
    Configure all interposition points to immediately pass through all
    internal events
    (possibly useful for replays affected by non-determinism)
    '''
    filtered_events = [e for e in self.dag.events if type(e) not in all_internal_events]
    self.dag = EventDag(filtered_events)
    self.default_dp_permit = True
    self.dp_checker = AlwaysAllowDataplane(self.dag)

  def _sleep_with_dataplane_passthrough(self, seconds):
    ''' Pre: simulate() has been called '''
    start = time.time()
    while not self.simulation.io_master.closed:
      elapsed = time.time() - start
      remaining = seconds - elapsed
      if remaining < 0.01:
        break
      self._select_with_dataplane_passthrough(remaining)

  def _select_with_dataplane_passthrough(self, timeout_seconds):
    ''' Pre: simulate() has been called '''
    if self.default_dp_permit:
      self.dp_checker.check_dataplane(-1, self.simulation)
    return self.simulation.io_master.select(timeout_seconds)

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
    msg.event(color.CYAN + ("Round %d" % self.logical_time) + color.WHITE)

  def init_results(self, results_dir):
    self.replay_id = results_dir
    if self._input_logger:
      self._input_logger.open(results_dir)

  def set_pass_through_sends(self, simulation):
    simulation.openflow_buffer.pass_through_sends_only()
    for e in self.dag.events:
      if type(e) == ControlMessageSend:
        e.pass_through_sends = True

  def simulate(self, post_bootstrap_hook=None):
    ''' Caller *must* call simulation.clean_up() '''
    if self.transform_dag:
      log.info("Transforming dag")
      self.dag = self.transform_dag(self.dag)
      log.info("Proceeding with normal replay")

    self.simulation = self.simulation_cfg.bootstrap(self.sync_callback)
    assert(isinstance(self.simulation.patch_panel, BufferedPatchPanel))
    # TODO(aw): remove this hack
    self.simulation.fail_to_interactive = self.fail_to_interactive
    self.simulation.fail_to_interactive_on_persistent_violations =\
      self.fail_to_interactive_on_persistent_violations
    self.simulation.openflow_buffer.pass_through_whitelisted_packets =\
      self.pass_through_whitelisted_messages
    if self.pass_through_sends:
      self.set_pass_through_sends(self.simulation)
    if self.delay_flow_mods:
      for switch in self.simulation.topology.switches:
        assert(isinstance(switch, FuzzSoftwareSwitch))
        switch.use_delayed_commands()
    self.run_simulation_forward(post_bootstrap_hook)
    if self.print_buffers_flag:
      self._print_buffers()
    return self.simulation

  def _print_buffers(self):
    log.debug("Pending Message Receives:")
    for p in self.simulation.openflow_buffer.pending_receives:
      log.debug("- %s", p)
    log.debug("Pending State Changes:")
    for p in self.sync_callback.pending_state_changes():
      log.debug("- %s", p)

  def run_simulation_forward(self, post_bootstrap_hook=None):
    event_scheduler = self.create_event_scheduler(self.simulation)
    event_scheduler.set_input_logger(self._input_logger)
    self.event_scheduler_stats = event_scheduler.stats
    if post_bootstrap_hook is not None:
      post_bootstrap_hook()

    def interrupt(sgn, frame):
      msg.interactive("Interrupting replayer, dropping to console (press ^C again to terminate)")
      signal.signal(signal.SIGINT, self.old_interrupt)
      self.old_interrupt = None
      raise KeyboardInterrupt()
    self.old_interrupt = signal.signal(signal.SIGINT, interrupt)

    try:
      for i, event in enumerate(self.dag.events):
        try:
          self.compute_interpolated_time(event)
          if self.default_dp_permit:
            self.dp_checker.check_dataplane(i, self.simulation)
          if isinstance(event, InputEvent):
            self._check_early_state_changes(self.dag, i, event)
          self._check_new_state_changes(self.dag, i)
          self._check_unexpected_cp_messages(self.dag, i)
          # TODO(cs): quasi race-condition here. If unexpected state change
          # happens *while* we're waiting for event, we basically have a
          # deadlock (if controller logging is set to blocking) until the
          # timeout occurs
          # TODO(cs): we don't actually allow new internal message events
          # through.. we only let new state changes through. Should experiment
          # with whether we would get better fidelity if we let them through.
          event_scheduler.schedule(event)
          if self.logical_time != event.round:
            self.logical_time = event.round
            self.increment_round()
        except KeyboardInterrupt:
          interactive = Interactive(self.simulation_cfg,
                                    input_logger=self._input_logger)
          interactive.simulate(self.simulation, bound_objects=( ('replayer', self), ))
          # If Interactive terminated due to ^D, return to our fuzzing loop,
          # prepared again to drop into Interactive on ^C.
          self.old_interrupt = signal.signal(signal.SIGINT, interrupt)
        except Exception:
          log.critical("Exception raised while scheduling event %s, replay %s"
                       % (str(event), self.replay_id))
          raise

      if self.invariant_check:
        # Wait a bit in case the bug takes awhile to happen
        # TODO(cs): may be redundant with WaitTime events at the end of the
        # trace.
        log.debug("Sleeping %d seconds after run" % self.end_wait_seconds)
        if self.default_dp_permit:
          self._sleep_with_dataplane_passthrough(self.end_wait_seconds)
        else:
          self.sleep(self.end_wait_seconds)

        # TODO(cs): this does not verify whether the violation is persistent
        # or transient. Perhaps it should?
        violations = self.invariant_check(self.simulation)
        self.simulation.violation_found = False
        if violations != []:
          self._log_input_event(InvariantViolation(violations))
          msg.fail("Violations at end of trace: %s" % str(violations))
          if self.bug_signature:
            if self.bug_signature in violations:
              self.simulation.violation_found = True
              msg.success("Violation found %s" % self.bug_signature)
            else:
              msg.fail("Violation does not match violation signature!")
          else:
            self.simulation.violation_found = True
        else:
          msg.success("No correctness violations!")
    finally:
      if self.old_interrupt:
        signal.signal(signal.SIGINT, self.old_interrupt)
      msg.event(color.B_BLUE+"Event Stats: %s" % str(event_scheduler.stats))
      if self.default_dp_permit:
        msg.event(color.B_BLUE+"DataplaneDrop Stats: %s" % str(self.dp_checker.stats))
    if self.end_in_interactive:
      interactive = Interactive(self.simulation_cfg, input_logger=self._input_logger)
      interactive.simulate(self.simulation, bound_objects=( ('replayer', self), ))

  def _check_early_state_changes(self, dag, current_index, input):
    ''' Check whether any pending state change that were supposed to come
    *after* the current input have occured. If so, we have violated causality.'''
    # Note that we never violate causality due to message sends/receipts,
    # since we buffer all messages.
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
        # raise RuntimeError("State change happened before expected! Causality violated")
        log.warn("State change happened before expected! Causality violated")
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
        log.info("Unexpected state change. Ack'ing %s" % str(state_change))
        log_event = ControllerStateChange.from_pending_state_change(state_change)
        # Monkeypatch a "new internal event" marker to be logged to the JSON trace
        # (All fields picked up by event.to_json())
        log_event.new_internal_event = True
        log_event.replay_time = SyncTime.now()
        self._log_input_event(log_event)
        self.unexpected_state_changes.append(repr(state_change))
        self.sync_callback.ack_pending_state_change(state_change)

  def _check_unexpected_cp_messages(self, dag, current_index):
    ''' If throughout replay we observe new messages that weren't in the
    original trace, we (usually) want to let them through. This is especially true
    for messages that are related to timers, such as LLDP, since timings will
    often change during replay, and we don't want to unnecessarily change the
    controller's behavior. '''
    if not self.allow_unexpected_messages:
      return
    # TODO(cs): evaluate whether _check_unexpected_cp_messages is more or less
    # effective than whitelisting cp message types (in OpenflowBuffer).
    # Compare executions with visualization tool.
    # Currently it appears that this method is too liberal, and ends up
    # causing timouts as a result of letting messages through.

    # First, build a set of expected ControlMessageSends/Receives fingerprints
    # within the next expected_message_round_window rounds.
    start_round = dag.events[current_index].round
    expected_receive_fingerprints = set()
    expected_send_fingerprints = set()
    for i in xrange(current_index, len(dag.events)):
      event = dag.events[i]
      if event.round - start_round > self.expected_message_round_window:
        break
      if type(event) == ControlMessageReceive:
        (_, of_fingerprint, dpid, cid) = event.fingerprint
        expected_receive_fingerprints.add((of_fingerprint, dpid, cid))
      if type(event) == ControlMessageSend:
        (_, of_fingerprint, dpid, cid) = event.fingerprint
        expected_send_fingerprints.add((of_fingerprint, dpid, cid))

    # Now check pending messages.
    for expected_fingerprints, messages in [
         (expected_receive_fingerprints, self.simulation.openflow_buffer.pending_receives),
         (expected_send_fingerprints, self.simulation.openflow_buffer.pending_sends)]:
      for pending_message in messages:
        fingerprint = (pending_message.fingerprint,
                       pending_message.dpid,
                       pending_message.controller_id)
        if fingerprint not in expected_fingerprints:
          message = self.simulation.openflow_buffer.schedule(pending_message)
          log.debug("Allowed unexpected message %s" % message)
          b64_packet = base64_encode(message)
          # Monkeypatch a "new internal event" marker to be logged to the JSON trace
          # (All fields picked up by event.to_json())
          event_type = ControlMessageReceive if type(pending_message) == PendingReceive else ControlMessageSend
          log_event = event_type(pending_message.dpid, pending_message.controller_id,
                                 pending_message.fingerprint, b64_packet=b64_packet)
          log_event.new_internal_event = True
          log_event.replay_time = SyncTime.now()
          self.passed_unexpected_messages.append(repr(log_event))
          self._log_input_event(log_event)

class AlwaysAllowDataplane(object):
  ''' A dataplane checker that always allows through events. Should not be
  used if there are any DataplaneDrops in the trace; in that case, use
  DataplaneChecker
  '''
  def __init__(self, event_dag):
    self.stats = DataplaneCheckerStats(list(event_dag.events))

  def check_dataplane(self, i, simulation):
    for dp_event in simulation.patch_panel.queued_dataplane_events:
      simulation.patch_panel.permit_dp_event(dp_event)

# --- Note: use DataplaneChecker at your own risk. I have observed it fail to
#     reproduce a bug that was reproducible with dataplane timeouts.
# TODO(cs): should this go in event_scheduler.py?
class DataplaneChecker(object):
  ''' Dataplane permits are the default, *unless* they were explicitly dropped in the
  initial run. This class keeps track of whether pending dataplane events should
  be dropped or forwarded during replay.

  Note that whenever DataplaneChecker is in use, it should always be the case
  that DataplanePermit and DataplaneDrop events are set to "passive" mode,
  where their proceed() method always returns True.'''
  def __init__(self, event_dag, slop_buffer=10):
    ''' Consider the round i of a DataplaneDrop in the original
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
    event_idx = self.fingerprint_2_event_idx[event_fingerprint].pop()
    self.events.pop(event_idx)
    # First element of the tuple is the Event class name
    if event_fingerprint[0] == "DataplanePermit":
      return False
    self.stats.record_drop(event_fingerprint)
    return True # DataplaneDrop

  def update_window(self, current_round):
    ''' Update the current slop buffer ("the dp_events we expect to see") '''
    self.current_dp_fingerprints = []
    self.fingerprint_2_event_idx = defaultdict(list)
    # TODO(cs): O(n) operation
    head_idx = find_index(lambda e: e.round == current_round - self.slop_buffer,
                          self.events)
    head_idx = max(head_idx, 0)
    tail_idx = find_index(lambda e: e.round == current_round + self.slop_buffer,
                          self.events)
    if tail_idx is None:
      tail_idx = len(self.events)
    for i in xrange(head_idx, tail_idx):
      if (type(self.events[i]) == DataplanePermit or
          type(self.events[i]) == DataplaneDrop):
        fingerprint = self.events[i].fingerprint
        self.current_dp_fingerprints.append(fingerprint)
        self.fingerprint_2_event_idx[fingerprint].append(i)

  def check_dataplane(self, current_round, simulation):
    ''' Check dataplane events for before playing then next event.
       - current_event_idx allows us to adjust our current slop buffer
    '''
    if current_round != -1:
      self.update_window(current_round)

    for dp_event in simulation.patch_panel.queued_dataplane_events:
      if not simulation.topology.ok_to_send(dp_event):
        log.warn("Not valid to send dp_event %s" % str(dp_event))
        simulation.patch_panel.drop_dp_event(dp_event)
      elif self.decide_drop(dp_event):
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
