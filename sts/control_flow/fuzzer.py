# Copyright 2011-2013 Colin Scott
# Copyright 2011-2013 Andreas Wundsam
# Copyright 2012-2013 Sam Whitlock
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
Three control flow types for running the simulation forward.
  - Fuzzer: injects input events at random intervals, periodically checking
    for invariant violations
  - Interactive: presents an interactive prompt for injecting events and
    checking for invariants at the users' discretion
'''

from sts.control_flow.interactive import Interactive
from sts.topology import BufferedPatchPanel
from sts.traffic_generator import TrafficGenerator
from sts.replay_event import *
from pox.lib.util import TimeoutError
from pox.lib.packet.lldp import *
from config.invariant_checks import name_to_invariant_check
from sts.util.convenience import base64_encode
from sts.entities import FuzzSoftwareSwitch, ControllerState
from sts.openflow_buffer import OpenFlowBuffer

from sts.control_flow.base import ControlFlow, RecordingSyncCallback

import os
import re
import shutil
import signal
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
               invariant_check_name="InvariantChecker.check_correspondence",
               halt_on_violation=False, log_invariant_checks=True,
               delay_startup=True, print_buffers=True,
               record_deterministic_values=False,
               mock_link_discovery=False,
               never_drop_whitelisted_packets=True,
               initialization_rounds=0, send_all_to_all=False):
    '''
    Options:
      - fuzzer_params: path to event probabilities
      - check_interval: the period for checking invariants, in terms of
        logical rounds
      - traffic_inject_interval: how often to inject dataplane trace packets
      - random_seed: optionally set the seed of the random number generator
      - delay: how long to sleep between each logical round
      - input_logger: None, or a InputLogger instance
      - invariant_check_name: the name of the invariant check, from
        config/invariant_checks.py
      - halt_on_violation: whether to stop after a bug has been detected
      - log_invariant_checks: whether to log InvariantCheck events
      - delay_startup: whether to until the first OpenFlow message is received
        before proceeding with fuzzing
      - print_buffers: whether to print the remaining contents of the
        dataplane/controlplane buffers at the end of the execution
      - record_deterministic_values: whether to record gettimeofday requests
        for replay
      - mock_link_discovery: optional module for POX to experiment with
        better determinism -- tell POX exactly when links should be discovered
      - initialization_rounds: if non-zero, will wait the specified rounds to
        let the controller discover the topology before injecting inputs
    '''
    ControlFlow.__init__(self, simulation_cfg)
    self.sync_callback = RecordingSyncCallback(input_logger,
                           record_deterministic_values=record_deterministic_values)

    self.check_interval = check_interval
    if self.check_interval is None:
      print >> sys.stderr, "Fuzzer Warning: Check interval is not specified... not checking invariants"
    if invariant_check_name not in name_to_invariant_check:
      raise ValueError('''Unknown invariant check %s.\n'''
                       '''Invariant check name must be defined in config.invariant_checks''',
                       invariant_check_name)
    self.invariant_check_name = invariant_check_name
    self.invariant_check = name_to_invariant_check[invariant_check_name]
    self.log_invariant_checks = log_invariant_checks
    self.traffic_inject_interval = traffic_inject_interval
    # Make execution deterministic to allow the user to easily replay
    if random_seed is None:
      random_seed = random.randint(0, sys.maxint)

    self.random_seed = random_seed
    self.random = random.Random(random_seed)
    self.traffic_generator = TrafficGenerator(self.random)

    self.delay = delay
    self.steps = steps
    self.params = object()
    self._load_fuzzer_params(fuzzer_params)
    self._input_logger = input_logger
    self.halt_on_violation = halt_on_violation
    self.delay_startup = delay_startup
    self.print_buffers = print_buffers
    self.mock_link_discovery = mock_link_discovery
    # How many rounds to let the controller initialize:
    # send one round of packets directed at the source host itself (to facilitate
    # learning), then send all-to-all packets until all pairs have been
    # pinged. Tell MCSFinder not to prune initial inputs during this period.
    self.initialization_rounds = initialization_rounds
    # Always send packets destined for self at the end of initialization
    self._pending_self_packets = self.initialization_rounds != 0
    # Whether to send all-to-all pings before starting any events
    self._pending_all_to_all = send_all_to_all
    # Our current place in the all-to-all cycle. Stop when == len(hosts)
    self._all_to_all_iterations = 0
    # How often (in terms of logical rounds) to inject all-to-all packets
    self._all_to_all_interval = 5
    self.blocked_controller_pairs = []
    self.unblocked_controller_pairs = []

    # Logical time (round #) for the simulation execution
    self.logical_time = 0
    self.never_drop_whitelisted_packets = never_drop_whitelisted_packets

    # Determine whether to use delayed and randomized flow mod processing
    # (Set by fuzzer_params, not by an optional __init__ argument)
    self.delay_flow_mods = False

  def _log_input_event(self, event, **kws):
    if self._input_logger is not None:
      if self._initializing():
        # Tell MCSFinder never to prune this event
        event.prunable = False

      event.round = self.logical_time
      self._input_logger.log_input_event(event, **kws)

  def _load_fuzzer_params(self, fuzzer_params_path):
    if fuzzer_params_path.endswith('.py'):
      fuzzer_params_path = fuzzer_params_path[:-3].replace("/", ".")

    try:
      self.params = __import__(fuzzer_params_path, globals(), locals(), ["*"])
      # TODO(cs): temporary hack until we get determinism figured out
      self.params.link_discovery_rate = 0.1
    except:
      raise IOError("Could not find fuzzer params config file: %s" %
                    fuzzer_params_path)

  def _compute_unblocked_controller_pairs(self):
    sorted_controllers = sorted(self.simulation.controller_manager.controllers, key=lambda c: c.cid)
    unblocked_pairs = []
    for i in xrange(0, len(sorted_controllers)):
      for j in xrange(i+1, len(sorted_controllers)):
        c1 = sorted_controllers[i]
        c2 = sorted_controllers[j]
        # Make sure all controller pairs are unblocked on startup
        c1.unblock_peer(c2)
        c2.unblock_peer(c1)
        unblocked_pairs.append((c1.cid, c2.cid))
    return unblocked_pairs

  def init_results(self, results_dir):
    if self._input_logger:
      self._input_logger.open(results_dir)
    params_file = re.sub(r'\.pyc$', '.py', self.params.__file__)
    # Move over our fuzzer params
    if os.path.exists(params_file):
      new_params_file = os.path.join(results_dir, os.path.basename(params_file))
      if os.path.abspath(params_file) != os.path.abspath(new_params_file):
        shutil.copy(params_file, new_params_file)
      # make sure to modify orig_config.py to point to new fuzzer_params.
      orig_config_path = os.path.join(results_dir, "orig_config.py")
      if os.path.exists(orig_config_path):
        with open(orig_config_path, "a") as out:
          # TODO(cs): too lazy for now to re-parse the config file and place
          # the fuzzer_params parameter in the correct place. So for now,
          # force the human to do it for us.
          out.write('''\nraise RuntimeError("Please add this parameter to Fuzzer: '''
                    '''fuzzer_params='%s'")''' % new_params_file)

  def _initializing(self):
    return self._pending_self_packets or self._pending_all_to_all

  def simulate(self):
    """Precondition: simulation.patch_panel is a buffered patch panel"""
    self.simulation = self.simulation_cfg.bootstrap(self.sync_callback)
    assert(isinstance(self.simulation.patch_panel, BufferedPatchPanel))
    self.traffic_generator.set_topology(self.simulation.topology)
    self.unblocked_controller_pairs = self._compute_unblocked_controller_pairs()

    self.delay_flow_mods = self.params.ofp_cmd_passthrough_rate != 1.0
    if self.delay_flow_mods:
      for switch in self.simulation.topology.switches:
        assert(isinstance(switch, FuzzSoftwareSwitch))
        switch.use_delayed_commands()
        switch.randomize_flow_mods()
    return self.loop()

  def loop(self):
    if self.steps:
      end_time = self.logical_time + self.steps
    else:
      end_time = sys.maxint

    self.interrupted = False
    self.old_interrupt = None

    def interrupt(sgn, frame):
      msg.interactive("Interrupting fuzzer, dropping to console (press ^C again to terminate)")
      # If ^C is triggered twice in a row, invoke the original handler.
      signal.signal(signal.SIGINT, self.old_interrupt)
      self.old_interrupt = None
      self.interrupted = True
      raise KeyboardInterrupt()

    # signal.signal returns the previous interrupt handler.
    self.old_interrupt = signal.signal(signal.SIGINT, interrupt)

    try:
      # Always connect to controllers explicitly
      self._log_input_event(ConnectToControllers())
      self.simulation.connect_to_controllers()

      if self.delay_startup:
        # Wait until the first OpenFlow message is received
        log.info("Waiting until first OpenFlow message received..")
        while len(self.simulation.openflow_buffer.pending_receives) == 0:
          self.simulation.io_master.select(self.delay)

      while self.logical_time < end_time:
        self.logical_time += 1
        try:
          if not self._initializing():
            self.trigger_events()
            halt = self.maybe_check_invariant()
            if halt:
              self.simulation.set_exit_code(5)
              break
            self.maybe_inject_trace_event()
          else:  # Initializing
            self.check_pending_messages(pass_through=True)
            if self.logical_time > self.initialization_rounds:
              if self._pending_self_packets:
                # Only need to send self packets once
                self._send_initialization_packets(send_to_self=True)
                self._pending_self_packets = False
              elif self._pending_all_to_all and (self.logical_time % self._all_to_all_interval) == 0: # All-to-all mode
                self._send_initialization_packets(send_to_self=False)
                self._all_to_all_iterations += 1
                if self._all_to_all_iterations > len(self.simulation.topology.hosts):
                  log.info("Done initializing")
                  self._pending_all_to_all = False
            self.check_dataplane(pass_through=True)

          msg.event("Round %d completed." % self.logical_time)
          # Note that time.sleep triggers a round of select.select()
          time.sleep(self.delay)
        except KeyboardInterrupt as e:
          if self.interrupted:
            interactive = Interactive(self.simulation_cfg, self._input_logger)
            interactive.simulate(self.simulation, bound_objects=( ('fuzzer', self), ))
            # If Interactive terminated due to ^D, return to our replaying loop,
            # prepared again to drop into Interactive on ^C.
            self.old_interrupt = signal.signal(signal.SIGINT, interrupt)
          else:
            raise e

      log.info("Terminating fuzzing after %d rounds" % self.logical_time)
      if self.print_buffers:
        self._print_buffers()

    finally:
      if self.old_interrupt:
        signal.signal(signal.SIGINT, self.old_interrupt)
      if self._input_logger is not None:
        self._input_logger.close(self, self.simulation_cfg)

    return self.simulation

  def _send_initialization_packet(self, host, send_to_self=False):
    traffic_type = "icmp_ping" if send_to_self else "arp_query"
    (dp_event, send) = self.traffic_generator.generate(traffic_type, host, send_to_self=send_to_self)
    self._log_input_event(TrafficInjection(dp_event=dp_event, host_id=host.hid))
    send()

  def _send_initialization_packets(self, send_to_self=False):
    for host in self.simulation.topology.hosts:
      self._send_initialization_packet(host, send_to_self=send_to_self)

  def _print_buffers(self):
    # TODO(cs): this method should also be added to Interactive.
    # Note that there shouldn't be any pending state changes in record mode,
    # only pending message sends/receives.
    buffered_events = []
    log.info("Pending Messages:")
    for event_type, pending_queue in [
            (ControlMessageReceive, self.simulation.openflow_buffer.pending_receives),
            (ControlMessageSend, self.simulation.openflow_buffer.pending_sends)]:
      for (dpid, controller_id) in pending_queue.conn_ids():
        for p in pending_queue.get_message_ids(dpid, controller_id):
          conn_mesages = pending_queue.get_all_by_message_id(p)
          log.info("- %r", p)
          for _, ofp_message in conn_messages:
            b64_packet = base64_encode(ofp_message)
            event = event_type(p.dpid, p.controller_id, p.fingerprint, b64_packet=b64_packet)
            buffered_events.append(event)

    if self._input_logger is not None:
      self._input_logger.dump_buffered_events(buffered_events)

  def maybe_check_invariant(self):
    if (self.check_interval is not None and
        (self.logical_time % self.check_interval) == 0):
      # Time to run correspondence!
      # TODO(cs): may need to revert to threaded version if runtime is too
      # long
      def do_invariant_check():
        if self.log_invariant_checks:
          self._log_input_event(CheckInvariants(round=self.logical_time,
                                 invariant_check_name=self.invariant_check_name))

        violations = self.invariant_check(self.simulation)
        self.simulation.violation_tracker.track(violations, self.logical_time)
        persistent_violations = self.simulation.violation_tracker.persistent_violations
        transient_violations = list(set(violations) - set(persistent_violations))

        if violations != []:
          msg.fail("The following correctness violations have occurred: %s"
                   % str(violations))
        else:
          msg.success("No correctness violations!")
        if transient_violations != []:
          self._log_input_event(InvariantViolation(transient_violations))
        if persistent_violations != []:
          msg.fail("Persistent violations detected!: %s"
                   % str(persistent_violations))
          self._log_input_event(InvariantViolation(persistent_violations, persistent=True))
          if self.halt_on_violation:
            return True
      return do_invariant_check()

  def maybe_inject_trace_event(self):
    if (self.simulation.dataplane_trace and
        (self.logical_time % self.traffic_inject_interval) == 0):
      (dp_event, host) = self.simulation.dataplane_trace.peek()
      if dp_event is not None:
        self._log_input_event(TrafficInjection(dp_event=dp_event,
                                               host_id=host.hid))
        self.simulation.dataplane_trace.inject_trace_event()

  def trigger_events(self):
    self.check_dataplane()
    self.check_tcp_connections()
    self.check_pending_messages()
    self.check_pending_commands()
    self.check_switch_crashes()
    self.check_link_failures()
    self.fuzz_traffic()
    self.check_controllers()
    self.check_migrations()
    self.check_intracontroller_blocks()

  def check_dataplane(self, pass_through=False):
    ''' Decide whether to delay, drop, or deliver packets '''
    def drop(dp_event, log_event=True):
      if log_event:
        self._log_input_event(DataplaneDrop(dp_event.fingerprint,
                                            host_id=dp_event.get_host_id(),
                                          dpid=dp_event.get_switch_id()))
      self.simulation.patch_panel.drop_dp_event(dp_event)
    def permit(dp_event):
      self._log_input_event(DataplanePermit(dp_event.fingerprint))
      self.simulation.patch_panel.permit_dp_event(dp_event)

    def in_whitelist(dp_event):
      return (self.never_drop_whitelisted_packets and
              OpenFlowBuffer.in_whitelist(dp_event.fingerprint[0]))

    for dp_event in self.simulation.patch_panel.queued_dataplane_events:
      if pass_through:
        permit(dp_event)
      elif not self.simulation.topology.ok_to_send(dp_event):
        drop(dp_event, log_event=False)
      elif (self.random.random() >= self.params.dataplane_drop_rate or in_whitelist(dp_event)):
        permit(dp_event)
      else:
        drop(dp_event)

    # TODO(cs): temporary hack until we have determinism figured out
    if self.mock_link_discovery and self.random.random() < self.params.link_discovery_rate:
      # Pick a random link to be discovered
      link = self.random.choice(self.simulation.topology.network_links)
      attrs = [link.start_software_switch.dpid, link.start_port.port_no,
               link.end_software_switch.dpid, link.end_port.port_no]
      # Send it to a random controller
      live_controllers = self.simulation.controller_manager.live_controllers
      if live_controllers != []:
        c = self.random.choice(list(live_controllers))
        self._log_input_event(LinkDiscovery(c.cid, attrs))
        c.sync_connection.send_link_notification(attrs)

  def check_tcp_connections(self):
    ''' Decide whether to block or unblock control channels '''
    for (switch, connection) in self.simulation.topology.unblocked_controller_connections:
      if self.random.random() < self.params.controlplane_block_rate:
        self._log_input_event(ControlChannelBlock(switch.dpid,
                              connection.get_controller_id()))
        self.simulation.topology.block_connection(connection)

    for (switch, connection) in self.simulation.topology.blocked_controller_connections:
      if self.random.random() < self.params.controlplane_unblock_rate:
        self._log_input_event(ControlChannelUnblock(switch.dpid,
                              controller_id=connection.get_controller_id()))
        self.simulation.topology.unblock_connection(connection)

  def check_pending_messages(self, pass_through=False):
    pending_receives = self.simulation.openflow_buffer.pending_receives
    for (dpid, controller_id) in pending_receives.conn_ids():
      for pending_receipt in pending_receives.get_message_ids(dpid, controller_id):
        if ( not pass_through and
            self.random.random() > self.params.ofp_message_receipt_rate):
          break
        message = self.simulation.openflow_buffer.get_message_receipt(pending_receipt)
        b64_packet = base64_encode(message)
        self._log_input_event(ControlMessageReceive(pending_receipt.dpid,
                                                    pending_receipt.controller_id,
                                                    pending_receipt.fingerprint,
                                                    b64_packet=b64_packet))
        self.simulation.openflow_buffer.schedule(pending_receipt)

    pending_sends = self.simulation.openflow_buffer.pending_sends
    for (dpid, controller_id) in pending_sends.conn_ids():
      for pending_send in pending_sends.get_message_ids(dpid, controller_id):
        if ( not pass_through and
            self.random.random() > self.params.ofp_message_send_rate):
          break
        message = self.simulation.openflow_buffer.get_message_send(pending_send)
        b64_packet = base64_encode(message)
        self._log_input_event(ControlMessageSend(pending_send.dpid,
                                                 pending_send.controller_id,
                                                 pending_send.fingerprint,
                                                 b64_packet=b64_packet))
        self.simulation.openflow_buffer.schedule(pending_send)

  def check_pending_commands(self):
    ''' If Fuzzer is configured to delay flow mods, this decides whether
    each switch is allowed to process a buffered flow mod '''
    if self.delay_flow_mods:
      for switch in self.simulation.topology.switches:
        assert(isinstance(switch, FuzzSoftwareSwitch))
        # first decide if we should try to process the next command from the switch
        if switch.has_pending_commands() and (self.random.random() < self.params.ofp_cmd_passthrough_rate):
          (cmd, pending_receipt) = switch.get_next_command()
          eventclass = ProcessFlowMod
          b64_packet = base64_encode(cmd)
          self._log_input_event(eventclass(pending_receipt.dpid,
                                           pending_receipt.controller_id,
                                           pending_receipt.fingerprint,
                                           b64_packet=b64_packet))
          switch.process_delayed_command(pending_receipt)

  def check_switch_crashes(self):
    ''' Decide whether to crash or restart switches, links and controllers '''
    def crash_switches():
      crashed_this_round = set()
      for software_switch in list(self.simulation.topology.live_switches):
        if self.random.random() < self.params.switch_failure_rate:
          crashed_this_round.add(software_switch)
          self._log_input_event(SwitchFailure(software_switch.dpid))
          self.simulation.topology.crash_switch(software_switch)
      return crashed_this_round

    def restart_switches(crashed_this_round):
      # Make sure we don't try to connect to dead controllers
      down_controller_ids = None

      for software_switch in list(self.simulation.topology.failed_switches):
        if software_switch in crashed_this_round:
          continue
        if self.random.random() < self.params.switch_recovery_rate:
          if down_controller_ids is None:
            self.simulation.controller_manager.check_controller_status()
            down_controller_ids = [ c.cid for c in self.simulation.controller_manager.controllers\
                                    if c.state == ControllerState.STARTING or\
                                       c.state == ControllerState.DEAD ]
          self._log_input_event(SwitchRecovery(software_switch.dpid))
          connected = self.simulation.topology\
                          .recover_switch(software_switch,
                                          down_controller_ids=down_controller_ids)
          if not connected:
            log.warn('''Switch %s was not able to connect. Down '''
                     '''controllers != actually down controllers? %s''' %
                     (str(software_switch), str(down_controller_ids)))

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
          self._log_input_event(LinkFailure(
                                link.start_software_switch.dpid,
                                link.start_port.port_no,
                                link.end_software_switch.dpid,
                                link.end_port.port_no))
          self.simulation.topology.sever_link(link)
      return cut_this_round

    def repair_links(cut_this_round):
      for link in list(self.simulation.topology.cut_links):
        if link in cut_this_round:
          continue
        if self.random.random() < self.params.link_recovery_rate:
          self._log_input_event(LinkRecovery(
                                link.start_software_switch.dpid,
                                link.start_port.port_no,
                                link.end_software_switch.dpid,
                                link.end_port.port_no))
          self.simulation.topology.repair_link(link)

    cut_this_round = sever_links()
    repair_links(cut_this_round)

  def fuzz_traffic(self):
    if not self.simulation.dataplane_trace:
      # randomly generate messages from switches
      for host in self.simulation.topology.hosts:
        if self.random.random() < self.params.traffic_generation_rate:
          if len(host.interfaces) > 0:
            msg.event("Injecting a random packet")
            traffic_type = "icmp_ping"
            (dp_event, send) = self.traffic_generator.generate(traffic_type, host)
            self._log_input_event(TrafficInjection(dp_event=dp_event))
            send()

  def check_controllers(self):
    def crash_controllers():
      crashed_this_round = set()
      for controller in self.simulation.controller_manager.live_controllers:
        if self.random.random() < self.params.controller_crash_rate:
          crashed_this_round.add(controller)
          self._log_input_event(ControllerFailure(controller.cid))
          controller.kill()
      return crashed_this_round

    def reboot_controllers(crashed_this_round):
      for controller in self.simulation.controller_manager.down_controllers:
        if controller in crashed_this_round:
          continue
        if self.random.random() < self.params.controller_recovery_rate:
          self._log_input_event(ControllerRecovery(controller.cid))
          controller.restart()

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
          msg.event("Migrating host %s, New switch %s, New port %s" %
                    (str(access_link.host),str(new_switch_dpid),str(new_port_no)))
          self._log_input_event(HostMigration(old_ingress_dpid,
                                              old_ingress_port_no,
                                              new_switch_dpid,
                                              new_port_no,
                                              access_link.host.hid))
          self.simulation.topology.migrate_host(old_ingress_dpid,
                                                old_ingress_port_no,
                                                new_switch_dpid,
                                                new_port_no)
          self._send_initialization_packet(access_link.host, send_to_self=True)

  def check_intracontroller_blocks(self):
    blocked_this_round = None

    # Block at most one controller pair per round.
    if (len(self.unblocked_controller_pairs) > 0 and
        self.random.random() < self.params.intracontroller_block_rate):
      (cid1, cid2) = self.random.choice(self.unblocked_controller_pairs)
      msg.event("Unblocking controllers %s, %s" % (cid1, cid2))
      blocked_this_round = (cid1, cid2)
      self.unblocked_controller_pairs.remove((cid1, cid2))
      self._log_input_event(BlockControllerPair(cid1, cid2))
      if self.simulation.controller_patch_panel is not None:
        self.simulation.controller_patch_panel.block_controller_pair(cid1, cid2)
      else:
        (c1, c2) = [ self.simulation.controller_manager.get_controller(cid)
                      for cid in [cid1, cid2] ]
        c1.block_peer(c2)
        c2.block_peer(c1)

    if (len(self.blocked_controller_pairs) > 0 and
        self.random.random() < self.params.intracontroller_unblock_rate):
      (cid1, cid2) = self.random.choice(self.blocked_controller_pairs)
      msg.event("Blocking controllers %s, %s" % (cid1, cid2))
      self.blocked_controller_pairs.remove((cid1, cid2))
      self.unblocked_controller_pairs.append((cid1, cid2))
      self._log_input_event(UnblockControllerPair(cid1, cid2))
      if self.simulation.controller_patch_panel is not None:
        self.simulation.controller_patch_panel.unblock_controller_pair(cid1, cid2)
      else:
        (c1, c2) = [ self.simulation.controller_manager.get_controller(cid)
                      for cid in [cid1, cid2] ]
        c1.unblock_peer(c2)
        c2.unblock_peer(c1)

    if blocked_this_round is not None:
      self.blocked_controller_pairs.append(blocked_this_round)
