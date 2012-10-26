'''
Three control flow types for running the simulation forward.
  - Replayer: takes as input a `superlog` with causal dependencies, and
    iteratively prunes until the MCS has been found
  - Fuzzer: injects input events at random intervals, periodically checking
    for invariant violations
  - Interactive: presents an interactive prompt for injecting events and
    checking for invariants at the users' discretion
'''

import pox.openflow.libopenflow_01 as of
from topology import BufferedPatchPanel
from traffic_generator import TrafficGenerator
from sts.util.console import msg
from sts.replay_event import *
import sts.event_dag
from sts.syncproto.sts_syncer import STSSyncCallback
import sts.log_processing.superlog_parser as superlog_parser
from sts.syncproto.base import SyncTime
from pox.lib.revent import EventMixin, Event

import sys
import time
import random
import logging
from collections import Counter

log = logging.getLogger("control_flow")

class ControlFlow(object):
  ''' Superclass of ControlFlow types '''
  def __init__(self, sync_callback):
    self.sync_callback = sync_callback

  def simulate(self, simulation):
    ''' Move the simulation forward! Take the state of the system as a
    parameter'''
    pass

  def get_sync_callback(self):
    return self.sync_callback

class Replayer(ControlFlow):
  time_epsilon_microseconds = 500

  '''
  Replay events from a `superlog` with causal dependencies, pruning as we go

  To set the wait_time and max_rounds, pass them as keyword args to the
  constructor of this class, which will pass them on to the EventDay object it creates.
  '''
  def __init__(self, superlog_path_or_dag, **kwargs):
    ControlFlow.__init__(self, ReplaySyncCallback(self.get_interpolated_time))
    if type(superlog_path_or_dag) == str:
      superlog_path = superlog_path_or_dag
      # The dag is codefied as a list, where each element has
      # a list of its dependents
      event_dag_kwargs = { k: v for k,v in kwargs.items()
                          if k in sts.event_dag.EventWatcher.kwargs }
      self.dag = sts.event_dag.EventDag(superlog_parser.parse_path(superlog_path), **event_dag_kwargs)
    else:
      self.dag = superlog_path_or_dag
    # compute interpolate to time to be just before first event
    self.compute_interpolated_time(self.dag.events[0])

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
    pass

  def simulate(self, simulation, post_bootstrap_hook=None):
    self.simulation = simulation
    self.run_simulation_forward(self.dag, post_bootstrap_hook)

  def run_simulation_forward(self, dag, post_bootstrap_hook=None):
    # Note that bootstrap() flushes any state from previous runs
    self.simulation.bootstrap()
    if post_bootstrap_hook is not None:
      post_bootstrap_hook()
    for event_watcher in dag.event_watchers:
      self.compute_interpolated_time(event_watcher.event)
      event_watcher.run(self.simulation)
      self.increment_round()

class MCSFinder(Replayer):
  def __init__(self, superlog_path_or_dag,
               invariant_check=InvariantChecker.check_correspondence, **kwargs):
    super(MCSFinder, self).__init__(superlog_path_or_dag, **kwargs)
    self.invariant_check = invariant_check
    self.log = logging.getLogger("mcs_finder")

  def simulate(self, simulation, check_reproducability=True):
    self.simulation = simulation
    if check_reproducability:
      # First, run through without pruning to verify that the violation exists
      Replayer.simulate(self, self.simulation)
      # Check invariants
      violations = self.invariant_check(self.simulation)
      if violations == []:
        self.log.warn("Unable to reproduce correctness violation!")
        sys.exit(5)

      self.log.info("Violation reproduced successfully! Proceeding with pruning")

    # Now start pruning
    self.dag.mark_invalid_input_sequences()
    self.dag.filter_unsupported_input_types()
    self._ddmin(2)
    msg.interactive("Final MCS (%d elts): %s" % (len(self.dag.input_events),str(self.dag.input_events)))
    return self.dag.events

  def _ddmin(self, split_ways, precomputed_subsets=None):
    # This is the delta-debugging algorithm from:
    #   http://www.st.cs.uni-saarland.de/papers/tse2002/tse2002.pdf,
    # Section 3.2
    # TODO(cs): we could do much better if we leverage domain knowledge (e.g.,
    # start by pruning all LinkFailures)
    if split_ways > len(self.dag):
      self.log.debug("Done")
      return

    if precomputed_subsets is None:
      precomputed_subsets = set()

    self.log.debug("Checking %d subsets" % split_ways)
    subsets = self.dag.split_inputs(split_ways)
    self.log.debug("Subsets: %s" % str(subsets))
    for i, subset in enumerate(subsets):
      # Note that subset() invokes peek()
      new_dag = self.dag.subset(subset, self.simulation)
      input_sequence = tuple(new_dag.input_events)
      self.log.debug("Current subset: %s" % str(input_sequence))
      if input_sequence in precomputed_subsets:
        self.log.debug("Already computed. Skipping")
        continue
      precomputed_subsets.add(input_sequence)

      violation = self._check_violation(new_dag, i)
      if violation:
        self.dag = new_dag
        return self._ddmin(2, precomputed_subsets=precomputed_subsets)

    self.log.debug("No subsets with violations. Checking complements")
    for i, subset in enumerate(subsets):
      # Note that complement() invokes peek()
      new_dag = self.dag.complement(subset, self.simulation)
      input_sequence = tuple(new_dag.input_events)
      self.log.debug("Current complement: %s" % str(input_sequence))
      if input_sequence in precomputed_subsets:
        self.log.debug("Already computed. Skipping")
        continue
      precomputed_subsets.add(input_sequence)
      violation = self._check_violation(new_dag, i)
      if violation:
        self.dag = new_dag
        return self._ddmin(max(split_ways - 1, 2),
                           precomputed_subsets=precomputed_subsets)

    self.log.debug("No complements with violations.")
    if split_ways < len(self.dag):
      self.log.debug("Increasing granularity.")
      return self._ddmin(min(len(self.dag), split_ways*2),
                         precomputed_subsets=precomputed_subsets)

  def _check_violation(self, new_dag, subset_index):
    ''' Check if there were violations '''
    # Run the simulation forward
    self.run_simulation_forward(new_dag)
    violations = self.invariant_check(self.simulation)
    if violations == []:
      # No violation!
      # If singleton, this must be part of the MCS
      self.log.debug("No violation in %d'th..." % subset_index)
      return False
    else:
      # Violation in the subset
      self.log.debug("Violation! Considering %d'th" % subset_index)
      return True

class Fuzzer(ControlFlow):
  '''
  Injects input events at random intervals, periodically checking
  for invariant violations. (Not the proper use of the term `Fuzzer`)
  '''
  def __init__(self, fuzzer_params="config.fuzzer_params",
               check_interval=None, trace_interval=10, random_seed=None,
               delay=0.1, steps=None, input_logger=None,
               invariant_check=InvariantChecker.check_correspondence,
               halt_on_violation=False):
    ControlFlow.__init__(self, RecordingSyncCallback(input_logger))

    self.check_interval = check_interval
    self.invariant_check = invariant_check
    self.trace_interval = trace_interval
    # Make execution deterministic to allow the user to easily replay
    if random_seed is None:
      self.random = random.Random()
    else:
      self.random = random.Random(random_seed)
    self.traffic_generator = TrafficGenerator(self.random)

    self.delay = delay
    self.steps = steps
    self.params = object()
    self._load_fuzzer_params(fuzzer_params)
    self._input_logger = input_logger
    self.halt_on_violation = halt_on_violation

    # Logical time (round #) for the simulation execution
    self.logical_time = 0

  def _log_input_event(self, event, **kws):
    if self._input_logger is not None:
      self._input_logger.log_input_event(event, **kws)

  def _load_fuzzer_params(self, fuzzer_params_path):
    try:
      self.params = __import__(fuzzer_params_path, globals(), locals(), ["*"])
    except:
      raise IOError("Could not find logging config file: %s" %
                    fuzzer_params_path)

  def simulate(self, simulation):
    """Precondition: simulation.patch_panel is a buffered patch panel"""
    self.simulation = simulation
    self.simulation.bootstrap()
    assert(isinstance(simulation.patch_panel, BufferedPatchPanel))
    self.loop()

  def loop(self):
    if self.steps:
      end_time = self.logical_time + self.steps
    else:
      end_time = sys.maxint

    try:
      while self.logical_time < end_time:
        self.logical_time += 1
        self.trigger_events()
        msg.event("Round %d completed." % self.logical_time)
        halt = self.maybe_check_invariant()
        if halt:
          break
        self.maybe_inject_trace_event()
        time.sleep(self.delay)
    finally:
      if self._input_logger is not None:
        self._input_logger.close(self.simulation)

  def maybe_check_invariant(self):
    if (self.check_interval is not None and
        (self.logical_time % self.check_interval) == 0):
      # Time to run correspondence!
      # spawn a thread for running correspondence. Make sure the controller doesn't
      # think we've gone idle though: send OFP_ECHO_REQUESTS every few seconds
      # TODO(cs): this is a HACK
      def do_invariant_check():
        controllers_with_violations = self.invariant_check(self.simulation)

        if controllers_with_violations != []:
          msg.fail("The following controllers had correctness violations!: %s"
                   % str(controllers_with_violations))
          if self.halt_on_violation:
           return True
        else:
          msg.interactive("No correctness violations!")
      # use a non-threaded version of correspondence for now. otherwise
      # communication / snapshotting has to be done in the main thread.
      do_invariant_check()
      #thread = threading.Thread(target=do_correspondence)
      #thread.start()
      #while thread.isAlive():
      #  for switch in self.simulation.topology.live_switches:
      #    # connection -> deferred io worker -> io worker
      #    switch.send(of.ofp_echo_request().pack())
      #  thread.join(2.0)

  def maybe_inject_trace_event(self):
    if (self.simulation.dataplane_trace and
        (self.logical_time % self.trace_interval) == 0):
      dp_event = self.simulation.dataplane_trace.inject_trace_event()
      self._log_input_event(TrafficInjection(), dp_event=dp_event)

  def trigger_events(self):
    self.check_dataplane()
    self.check_tcp_connections()
    self.check_message_receipts()
    self.check_switch_crashes()
    self.check_link_failures()
    self.fuzz_traffic()
    self.check_controllers()
    self.check_migrations()

  def check_dataplane(self):
    ''' Decide whether to delay, drop, or deliver packets '''
    for dp_event in self.simulation.patch_panel.queued_dataplane_events:
      if self.random.random() < self.params.dataplane_delay_rate:
        self.simulation.patch_panel.delay_dp_event(dp_event)
      elif self.random.random() < self.params.dataplane_drop_rate:
        self.simulation.patch_panel.drop_dp_event(dp_event)
        self._log_input_event(DataplaneDrop(dp_event.fingerprint))
      elif not self.simulation.topology.ok_to_send(dp_event):
        # Switches have very small buffers! drop it on the floor if the link
        # is down
        self.simulation.patch_panel.drop_dp_event(dp_event)
        self._log_input_event(DataplaneDrop(dp_event.fingerprint))
      else:
        self.simulation.patch_panel.permit_dp_event(dp_event)
        self._log_input_event(DataplanePermit(dp_event.fingerprint))

  def check_tcp_connections(self):
    ''' Decide whether to block or unblock control channels '''
    for (switch, connection) in self.simulation.topology.unblocked_controller_connections:
      if self.random.random() < self.params.controlplane_block_rate:
        self.simulation.topology.block_connection(connection)
        self._log_input_event(ControlChannelBlock(switch.dpid,
                              connection.get_controller_id()))

    for (switch, connection) in self.simulation.topology.blocked_controller_connections:
      if self.random.random() < self.params.controlplane_unblock_rate:
        self.simulation.topology.unblock_connection(connection)
        self._log_input_event(ControlChannelUnblock(switch.dpid,
                              controller_id=connection.get_controller_id()))

  def check_message_receipts(self):
    for pending_receipt in self.simulation.god_scheduler.pending_receives():
      # TODO(cs): this is a really dumb way to fuzz packet receipt scheduling
      if self.random.random() < self.params.ofp_message_receipt_rate:
        self.simulation.god_scheduler.schedule(pending_receipt)
        self._log_input_event(ControlMessageReceive(pending_receipt.dpid,
                                                    pending_receipt.controller_id,
                                                    pending_receipt.fingerprint))

  def check_switch_crashes(self):
    ''' Decide whether to crash or restart switches, links and controllers '''
    def crash_switches():
      crashed_this_round = set()
      for software_switch in list(self.simulation.topology.live_switches):
        if self.random.random() < self.params.switch_failure_rate:
          crashed_this_round.add(software_switch)
          self.simulation.topology.crash_switch(software_switch)
          self._log_input_event(SwitchFailure(software_switch.dpid))
      return crashed_this_round

    def restart_switches(crashed_this_round):
      # Make sure we don't try to connect to dead controllers
      down_controller_ids = map(lambda c: c.uuid,
                                self.simulation.controller_manager.down_controllers)

      for software_switch in list(self.simulation.topology.failed_switches):
        if software_switch in crashed_this_round:
          continue
        if self.random.random() < self.params.switch_recovery_rate:
          connected = self.simulation.topology\
                          .recover_switch(software_switch,
                                          down_controller_ids=down_controller_ids)
          if connected:
            self._log_input_event(SwitchRecovery(software_switch.dpid))

    crashed_this_round = crash_switches()
    restart_switches(crashed_this_round)

  def check_link_failures(self):
    def sever_links():
      # TODO(cs): model administratively down links? (OFPPC_PORT_DOWN)
      cut_this_round = set()
      for link in list(self.simulation.topology.live_links):
        if self.random.random() < self.params.link_failure_rate:
          cut_this_round.add(link)
          self.simulation.topology.sever_link(link)
          self._log_input_event(LinkFailure(
                                link.start_software_switch.dpid,
                                link.start_port.port_no,
                                link.end_software_switch.dpid,
                                link.end_port.port_no))
      return cut_this_round

    def repair_links(cut_this_round):
      for link in list(self.simulation.topology.cut_links):
        if link in cut_this_round:
          continue
        if self.random.random() < self.params.link_recovery_rate:
          self.simulation.topology.repair_link(link)
          self._log_input_event(LinkRecovery(
                                link.start_software_switch.dpid,
                                link.start_port.port_no,
                                link.end_software_switch.dpid,
                                link.end_port.port_no))


    cut_this_round = sever_links()
    repair_links(cut_this_round)

  def fuzz_traffic(self):
    if not self.simulation.dataplane_trace:
      # randomly generate messages from switches
      for host in self.simulation.topology.hosts:
        if self.random.random() < self.params.traffic_generation_rate:
          if len(host.interfaces) > 0:
            msg.event("injecting a random packet")
            traffic_type = "icmp_ping"
            # Generates a packet, and feeds it to the software_switch
            dp_event = self.traffic_generator.generate(traffic_type, host)
            self._log_input_event(TrafficInjection(), dp_event=dp_event)

  def check_controllers(self):
    def crash_controllers():
      crashed_this_round = set()
      for controller in self.simulation.controller_manager.live_controllers:
        if self.random.random() < self.params.controller_crash_rate:
          crashed_this_round.add(controller)
          controller.kill()
          self._log_input_event(ControllerFailure(controller.uuid))
      return crashed_this_round

    def reboot_controllers(crashed_this_round):
      for controller in self.simulation.controller_manager.down_controllers:
        if controller in crashed_this_round:
          continue
        if self.random.random() < self.params.controller_recovery_rate:
          controller.start()
          self._log_input_event(ControllerRecovery(controller.uuid))

    crashed_this_round = crash_controllers()
    reboot_controllers(crashed_this_round)

  def check_migrations(self):
    for access_link in list(self.simulation.topology.access_links):
      if self.random.random() < self.params.host_migration_rate:
        old_ingress_dpid = access_link.switch.dpid
        old_ingress_port_no = access_link.switch_port.port_no
        live_edge_switches = list(self.simulation.topology.live_edge_switches)
        if len(live_edge_switches) > 0:
          new_switch = random.choice(live_edge_switches)
          new_switch_dpid = new_switch.dpid
          new_port_no = max(new_switch.ports.keys()) + 1
          self.simulation.topology.migrate_host(old_ingress_dpid,
                                                old_ingress_port_no,
                                                new_switch_dpid,
                                                new_port_no)
          self._log_input_event(HostMigration(old_ingress_dpid,
                                              old_ingress_port_no,
                                              new_switch_dpid,
                                              new_port_no))

class Interactive(ControlFlow):
  '''
  Presents an interactive prompt for injecting events and
  checking for invariants at the users' discretion
  '''
  # TODO(cs): rather than just prompting "Continue to next round? [Yn]", allow
  #           the user to examine the state of the network interactively (i.e.,
  #           provide them with the normal POX cli + the simulated events
  def __init__(self, input_logger=None):
    ControlFlow.__init__(self, RecordingSyncCallback(input_logger))
    self.logical_time = 0
    self._input_logger = input_logger
    # TODO(cs): future feature: allow the user to interactively choose the order
    # events occur for each round, whether to delay, drop packets, fail nodes,
    # etc.
    # self.failure_lvl = [
    #   NOTHING,    # Everything is handled by the random number generator
    #   CRASH,      # The user only controls node crashes and restarts
    #   DROP,       # The user also controls message dropping
    #   DELAY,      # The user also controls message delays
    #   EVERYTHING  # The user controls everything, including message ordering
    # ]

  def _log_input_event(self, event, **kws):
    # TODO(cs): redundant with Fuzzer._log_input_event
    if self._input_logger is not None:
      self._input_logger.log_input_event(event, **kws)

  def simulate(self, simulation):
    self.simulation = simulation
    self.simulation.bootstrap()
    self.loop()

  def loop(self):
    try:
      while True:
        # TODO(cs): print out the state of the network at each timestep? Take a
        # verbose flag..
        time.sleep(0.05)
        self.logical_time += 1
        self.invariant_check_prompt()
        self.dataplane_trace_prompt()
        self.check_dataplane()
        self.check_message_receipts()
        answer = msg.raw_input('Continue to next round? [Yn]').strip()
        if answer != '' and answer.lower() != 'y':
          break
    finally:
      if self._input_logger is not None:
        self._input_logger.close(self.simulation)

  def invariant_check_prompt(self):
    answer = msg.raw_input('Check Invariants? [Ny]')
    if answer != '' and answer.lower() != 'n':
      msg.interactive("Which one?")
      msg.interactive("  'o' - omega")
      msg.interactive("  'c' - connectivity")
      msg.interactive("  'l' - loops")
      answer = msg.raw_input("> ")
      result = None
      message = ""
      if answer.lower() == 'o':
        result = InvariantChecker.check_correspondence(self.simulation)
        message = "Controllers with miscorrepondence: "
      elif answer.lower() == 'c':
        result = self.invariant_checker.check_connectivity(self.simulation)
        message = "Disconnected host pairs: "
      elif answer.lower() == 'l':
        result = self.invariant_checker.check_loops(self.simulation)
        message = "Loops: "
      else:
        log.warn("Unknown input...")

      if result is None:
        return
      else:
        msg.interactive("%s: %s" % (message, str(result)))

  def dataplane_trace_prompt(self):
    if self.simulation.dataplane_trace:
      while True:
        answer = msg.raw_input('Feed in next dataplane event? [Ny]')
        if answer != '' and answer.lower() != 'n':
          dp_event = self.simulation.dataplane_trace.inject_trace_event()
          self._log_input_event(TrafficInjection(), dp_event=dp_event)
        else:
          break

  def check_dataplane(self):
    ''' Decide whether to delay, drop, or deliver packets '''
    if type(self.simulation.patch_panel) == BufferedPatchPanel:
      for dp_event in self.simulation.patch_panel.queued_dataplane_events:
        answer = msg.raw_input('Allow [a], Drop [d], or Delay [e] dataplane packet %s? [Ade]' %
                               dp_event)
        if ((answer == '' or answer.lower() == 'a') and
                self.simulation.topology.ok_to_send(dp_event)):
          self.simulation.patch_panel.permit_dp_event(dp_event)
          self._log_input_event(DataplanePermit(dp_event.fingerprint))
        elif answer.lower() == 'd':
          self.simulation.patch_panel.drop_dp_event(dp_event)
          self._log_input_event(DataplaneDrop(dp_event.fingerprint))
        elif answer.lower() == 'e':
          self.simulation.patch_panel.delay_dp_event(dp_event)
        else:
          log.warn("Unknown input...")
          self.simulation.patch_panel.delay_dp_event(dp_event)

  def check_message_receipts(self):
    for pending_receipt in self.simulation.god_scheduler.pending_receives():
      # For now, just schedule FIFO.
      # TODO(cs): make this interactive
      self.simulation.god_scheduler.schedule(pending_receipt)
      self._log_input_event(ControlMessageReceive(pending_receipt.dpid,
                                                  pending_receipt.controller_id,
                                                  pending_receipt.fingerprint))

  # TODO(cs): add support for control channel blocking + switch, link,
  # controller failures, host migration, god scheduling

# ---------------------------------------- #
#  Callbacks for controller sync messages  #
# ---------------------------------------- #

class StateChange(Event):
  def __init__(self, pending_state_change):
    super(StateChange, self).__init__()
    self.pending_state_change = pending_state_change

class ReplaySyncCallback(STSSyncCallback, EventMixin):

  _eventMixin_events = set([StateChange])

  def __init__(self, get_interpolated_time):
    self.get_interpolated_time = get_interpolated_time
    # TODO(cs): move buffering functionality into the GodScheduler? Or a
    # separate class?
    # Python's Counter object is effectively a multiset
    self._pending_state_changes = Counter()
    self.log = logging.getLogger("synccallback")

  def _pass_through_handler(self, state_change_event):
    state_change = state_change_event.pending_state_change
    # Pass through
    self.gc_pending_state_change(state_change)
    # Record
    replay_event = ControllerStateChange(state_change.controller_id,
                                         state_change.time,
                                         state_change.fingerprint,
                                         state_change.name,
                                         state_change.value)
    self.passed_through_events.append(replay_event)

  def set_pass_through(self):
    '''Cause all pending state changes to pass through without being buffered'''
    self.passed_through_events = []
    self.addListener(StateChange, self._pass_through_handler)

  def unset_pass_through(self):
    '''Unset pass through mode, and return any events that were passed through
    since pass through mode was set'''
    self.removeListener(self._pass_through_handler)
    passed_events = self.passed_through_events
    self.passed_through_events = []
    return passed_events

  def flush(self):
    ''' Remove any pending state changes '''
    num_pending_state_changes = len(self._pending_state_changes)
    if num_pending_state_changes > 0:
      self.log.info("Flushing %d pending state changes" %
                    num_pending_state_changes)
    self._pending_state_changes = Counter()

  def state_change_pending(self, pending_state_change):
    ''' Return whether the PendingStateChange has been observed '''
    return self._pending_state_changes[pending_state_change] > 0

  def gc_pending_state_change(self, pending_state_change):
    ''' Garbage collect the PendingStateChange from our buffer'''
    self._pending_state_changes[pending_state_change] -= 1
    if self._pending_state_changes[pending_state_change] <= 0:
      del self._pending_state_changes[pending_state_change]

  def state_change(self, controller, time, fingerprint, name, value):
    # TODO(cs): unblock the controller after processing the state change?
    pending_state_change = PendingStateChange(controller.uuid, time,
                                              fingerprint, name, value)
    self._pending_state_changes[pending_state_change] += 1
    self.raiseEventNoError(StateChange(pending_state_change))

  def pending_state_changes(self):
    ''' Return any pending state changes '''
    return self._pending_state_changes.keys()

  def get_deterministic_value(self, controller, name):
    if name == "gettimeofday":
      # Note: not a method, but a bound function
      value = self.get_interpolated_time()
      # TODO(cs): implement Andi's improved gettime heuristic
    else:
      raise ValueError("unsupported deterministic value: %s" % name)
    return value

class RecordingSyncCallback(STSSyncCallback):
  def __init__(self, input_logger):
    self.input_logger = input_logger

  def state_change(self, controller, time, fingerprint, name, value):
    if self.input_logger is not None:
      self.input_logger.log_input_event(ControllerStateChange((controller.uuid,
                                                               time,
                                                               fingerprint,
                                                               name, value)))

  def get_deterministic_value(self, controller, name):
    value = None
    if name == "gettimeofday":
      value = SyncTime.now()
      time = value
    else:
      raise ValueError("unsupported deterministic value: %s" % name)

    # TODO(cs): implement Andi's improved gettime heuristic, and uncomment
    #           the following statement
    #self.input_logger.log_input_event(klass="DeterministicValue",
    #                                  controller_id=controller.uuid,
    #                                  time=time, fingerprint="null",
    #                                  name=name, value=value)
    return value
