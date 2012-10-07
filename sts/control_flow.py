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
from invariant_checker import InvariantChecker
from topology import BufferedPatchPanel
from traffic_generator import TrafficGenerator
from sts.util.console import msg
from sts.replay_event import *
from sts.syncproto.sts_syncer import STSSyncCallback
import sts.log_processing.superlog_parser as superlog_parser
from sts.syncproto.base import SyncTime

import os
import sys
import threading
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
  '''
  def __init__(self, superlog_path):
    ControlFlow.__init__(self, ReplaySyncCallback(self.get_interpolated_time))
    # The dag is codefied as a list, where each element has
    # a list of its dependents
    self.dag = EventDag(superlog_parser.parse_path(superlog_path))
    # compute interpolate to time to be just before first event
    self.compute_interpolated_time(self.dag.events().next())

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

  def simulate(self, simulation):
    self.simulation = simulation

    self.simulation.bootstrap()
    for event_watcher in self.dag.event_watchers():
      self.compute_interpolated_time(event_watcher.event)
      event_watcher.run(simulation)
      self.increment_round()
      # TODO(cs): check correspondence

class MCSFinder(Replayer):
  def simulate(self, simulation):
    # First, run through without pruning to verify that the violation exists
    Replayer.simulate(self, simulation)

    # Now start pruning
    mcs = []
    for pruned_event in self.dag.events():
      self.simulation.bootstrap()
      for event_watcher in self.dag.event_watchers(pruned_event):
        event_watcher.run(self.simulation)
        self.increment_round()
    return mcs

class Fuzzer(ControlFlow):
  '''
  Injects input events at random intervals, periodically checking
  for invariant violations. (Not the proper use of the term `Fuzzer`)
  '''
  def __init__(self, fuzzer_params="config.fuzzer_params",
               check_interval=None, trace_interval=10, random_seed=None,
               delay=0.1, steps=None, input_logger=None,
               invariant_check=InvariantChecker.check_correspondence):
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
        self.maybe_check_invariant()
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
        self._log_input_event(DataplaneDrop(dp_event.fingerprint.to_dict()))
      elif not self.simulation.topology.ok_to_send(dp_event):
        # Switches have very small buffers! drop it on the floor if the link
        # is down
        self.simulation.patch_panel.drop_dp_event(dp_event)
        self._log_input_event(DataplaneDrop(dp_event.fingerprint.to_dict()))
      else:
        self.simulation.patch_panel.permit_dp_event(dp_event)
        self._log_input_event(DataplanePermit(dp_event.fingerprint.to_dict()))

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
                                                    pending_receipt.fingerprint.to_dict()))

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
          self._log_input_event(DataplanePermit(dp_event.fingerprint.to_dict()))
        elif answer.lower() == 'd':
          self.simulation.patch_panel.drop_dp_event(dp_event)
          self._log_input_event(DataplaneDrop(dp_event.fingerprint.to_dict()))
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
                                                  pending_receipt.fingerprint.to_dict()))

  # TODO(cs): add support for control channel blocking + switch, link,
  # controller failures, host migration, god scheduling

# ---------------------------------------- #
#  Callbacks for controller sync messages  #
# ---------------------------------------- #

class ReplaySyncCallback(STSSyncCallback):
  def __init__(self, get_interpolated_time):
    self.get_interpolated_time = get_interpolated_time
    # TODO(cs): move buffering functionality into the GodScheduler? Or a
    # separate class?
    # Python's Counter object is effectively a multiset
    # TODO(cs): garbage collect me
    self.pending_state_changes = Counter()

  def state_change_pending(self, pending_state_change):
    ''' Return whether the PendingStateChange has been observed '''
    return self.pending_state_changes[pending_state_change] > 0

  def gc_pending_state_change(self, pending_state_change):
    ''' Garbage collect the PendingStateChange from our buffer'''
    self.pending_state_changes[pending_state_change] -= 1
    if self.pending_state_changes[pending_state_change] <= 0:
      del self.pending_state_changes[pending_state_change]

  def state_change(self, controller, time, fingerprint, name, value):
    # TODO(cs): unblock the controller after processing the state change?
    pending_state_change = PendingStateChange(controller.uuid, time,
                                              fingerprint, name, value)
    self.pending_state_changes[pending_state_change] += 1

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
