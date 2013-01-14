'''
Three control flow types for running the simulation forward.
  - Fuzzer: injects input events at random intervals, periodically checking
    for invariant violations
  - Interactive: presents an interactive prompt for injecting events and
    checking for invariants at the users' discretion
'''

from sts.topology import BufferedPatchPanel
from sts.traffic_generator import TrafficGenerator
from sts.util.console import msg
from sts.replay_event import *
from pox.lib.util import TimeoutError

from sts.control_flow.base import ControlFlow, RecordingSyncCallback

import sys
import time
import random
import logging

log = logging.getLogger("control_flow")

class Fuzzer(ControlFlow):
  '''
  Injects input events at random intervals, periodically checking
  for invariant violations. (Not the proper use of the term `Fuzzer`)
  '''
  def __init__(self, simulation_cfg, fuzzer_params="config.fuzzer_params",
               check_interval=None, traffic_inject_interval=10, random_seed=None,
               delay=0.1, steps=None, input_logger=None,
               invariant_check=InvariantChecker.check_correspondence,
               halt_on_violation=False, log_invariant_checks=True,
               delay_startup=True):
    ControlFlow.__init__(self, simulation_cfg)
    self.sync_callback = RecordingSyncCallback(input_logger)

    self.check_interval = check_interval
    self.invariant_check = invariant_check
    self.log_invariant_checks = log_invariant_checks
    self.traffic_inject_interval = traffic_inject_interval
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
    self.delay_startup = delay_startup

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

  def simulate(self):
    """Precondition: simulation.patch_panel is a buffered patch panel"""
    self.simulation = self.simulation_cfg.bootstrap(self.sync_callback)
    assert(isinstance(self.simulation.patch_panel, BufferedPatchPanel))
    self.loop()

  def loop(self):
    if self.steps:
      end_time = self.logical_time + self.steps
    else:
      end_time = sys.maxint

    try:
      if self.delay_startup:
        # Wait until the first OpenFlow message is received
        log.info("Waiting until first OpenfFlow message received..")
        self._input_logger.disallow_timeouts()
        while self.simulation.god_scheduler.pending_receives() == []:
          simulation.io_master.select(self.delay)
        self._input_logger.allow_timeouts()

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
        self._input_logger.close(self.simulation_cfg)

  def maybe_check_invariant(self):
    if (self.check_interval is not None and
        (self.logical_time % self.check_interval) == 0):
      # Time to run correspondence!
      # TODO(cs): may need to revert to threaded version if runtime is too
      # long
      def do_invariant_check():
        if self.log_invariant_checks:
          self._log_input_event(CheckInvariants(invariant_check=self.invariant_check,
                                                fail_on_error=self.halt_on_violation))

        controllers_with_violations = self.invariant_check(self.simulation)

        if controllers_with_violations != []:
          msg.fail("The following controllers had correctness violations!: %s"
                   % str(controllers_with_violations))
          self._log_input_event(InvariantViolation(controllers_with_violations))
          if self.halt_on_violation:
            return True
        else:
          msg.interactive("No correctness violations!")
      return do_invariant_check()

  def maybe_inject_trace_event(self):
    if (self.simulation.dataplane_trace and
        (self.logical_time % self.traffic_inject_interval) == 0):
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
    try:
      restart_switches(crashed_this_round)
    except TimeoutError:
      log.warn("Unable to connect to controllers")

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


