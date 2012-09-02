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
from sts.console import msg
from sts.event import EventDag
import log_parsing.superlog_parser as superlog_parser

import os
import time
import sys
import threading
import random
import logging

log = logging.getLogger("control_flow")

class ControlFlow(object):
  ''' Superclass of ControlFlow types '''
  def __init__(self):
    self.invariant_checker = InvariantChecker()

  def simulate(self, simulation):
    pass

class Replayer(ControlFlow):
  '''
  Replay events from a `superlog` with causal dependencies, pruning as we go
  '''
  def __init__(self, superlog_path):
    ControlFlow.__init__(self)
    # The dag is codefied as a list, where each element has
    # a list of its dependents
    self.dag = EventDag(superlog_parser.parse_path(superlog_path))

  def simulate(self, simulation):
    self.simulation = simulation

    def increment_round():
      # TODO(cs): complete this method
      pass

    # First, run through without pruning to verify that the violation exists
    simulation.bootstrap()
    for event_watcher in self.dag.event_watchers():
      event_watcher.run(simulation)
      increment_round()

    # Now start pruning
    for pruned_event in self.dag.events():
      simulation.bootstrap()
      for event_watcher in self.dag.event_watchers(pruned_event):
        event_watcher.run(simulation)
        increment_round()

class Fuzzer(ControlFlow):
  '''
  Injects input events at random intervals, periodically checking
  for invariant violations. (Not the proper use of the term `Fuzzer`)
  '''
  def __init__(self, fuzzer_params="config.fuzzer_params",
               check_interval=35, trace_interval=10, random_seed=0.0,
               delay=0.1, steps=None):
    ControlFlow.__init__(self)

    self.check_interval = check_interval
    self.trace_interval = trace_interval
    # Make execution deterministic to allow the user to easily replay
    self.seed = random_seed
    self.random = random.Random(self.seed)
    self.traffic_generator = TrafficGenerator(self.random)

    self.delay = delay
    self.steps = steps
    self.params = object()
    self._load_fuzzer_params(fuzzer_params)

    # Logical time (round #) for the simulation execution
    self.logical_time = 0

  def _load_fuzzer_params(self, fuzzer_params_path):
    try:
      self.params = __import__(fuzzer_params_path, globals(), locals(), ["*"])
    except:
      raise IOError("Could not find logging config file: %s" %
                    fuzzer_params_path)

  def simulate(self, simulation):
    """Precondition: simulation.patch_panel is a buffered patch panel"""
    assert(isinstance(simulation.patch_panel, BufferedPatchPanel))
    self.simulation = simulation
    self.simulation.bootstrap()
    self.loop()

  def loop(self):
    if self.steps:
      end_time = self.logical_time + self.steps
    else:
      end_time = sys.maxint

    while self.logical_time < end_time:
      self.logical_time += 1
      self.trigger_events()
      msg.event("Round %d completed." % self.logical_time)

      if (self.logical_time % self.check_interval) == 0:
        # Time to run correspondence!
        # spawn a thread for running correspondence. Make sure the controller doesn't
        # think we've gone idle though: send OFP_ECHO_REQUESTS every few seconds
        # TODO(cs): this is a HACK
        def do_correspondence():
          any_policy_violations = self.invariant_checker\
                                      .check_correspondence(self.simulation)

          if any_policy_violations:
            msg.fail("There were policy-violations!")
          else:
            msg.interactive("No policy-violations!")
        thread = threading.Thread(target=do_correspondence)
        thread.start()
        while thread.isAlive():
          for switch in self.simulation.topology.live_switches:
            # connection -> deferred io worker -> io worker
            switch.send(of.ofp_echo_request().pack())
          thread.join(2.0)

      if (self.simulation.dataplane_trace and
          (self.logical_time % self.trace_interval) == 0):
        self.inject_trace_event()

      time.sleep(self.delay)

  def trigger_events(self):
    self.check_dataplane()
    self.check_controlplane()
    self.check_switch_crashes()
    self.check_timeouts()
    self.fuzz_traffic()

  def check_dataplane(self):
    ''' Decide whether to delay, drop, or deliver packets '''
    for dp_event in self.simulation.patch_panel.queued_dataplane_events:
      if self.random.random() < self.params.dataplane_delay_rate:
        self.simulation.delay_dp_event(dp_event)
      elif self.random.random() < self.params.dataplane_drop_rate:
        self.simulation.drop_dp_event(dp_event)
      elif self.topology.ok_to_send(dp_event):
        self.simulation.patch_panel.permit_dp_event(dp_event)

  def check_controlplane(self):
    ''' Decide whether to delay or deliver packets '''
    def check_deliver(connection, delay_function, permit_function):
      if self.random.random() < self.params.controlplane_delay_rate:
        delay_function(connection)
      else:
        permit_function(connection)

    # Check reads
    for connection in self.simulation.topology.cp_connections_with_pending_receives:
      check_deliver(connection, self.simulation.topology.delay_cp_receive,
                    self.simulation.topology.permit_cp_receive)

    # Check writes
    for connection in self.simulation.topology.cp_connections_with_pending_sends:
      check_deliver(connection, self.simulation.topology.delay_cp_send,
                    self.simulation.topology.permit_cp_send)

  def check_switch_crashes(self):
    ''' Decide whether to crash or restart switches, links and controllers '''
    def crash_switches():
      crashed_this_round = set()
      for software_switch in self.simulation.topology.live_switches:
        if self.random.random() < self.params.switch_failure_rate:
          crashed_this_round.add(software_switch)
          self.simulation.topology.crash_switch(software_switch)
      return crashed_this_round

    def restart_switches(crashed_this_round):
      for software_switch in self.simulation.topology.failed_switches:
        if software_switch in crashed_this_round:
          continue
        if self.random.random() < self.params.switch_recovery_rate:
          self.simulation.topology.recover_switch(software_switch)

    def sever_links():
      # TODO(cs): model administratively down links? (OFPPC_PORT_DOWN)
      cut_this_round = set()
      for link in self.simulation.topology.live_links:
        if self.random.random() < self.params.link_failure_rate:
          cut_this_round.add(link)
          self.simulation.topology.sever_link(link)
      return cut_this_round

    def repair_links(cut_this_round):
      for link in self.simulation.topology.cut_links:
        if link in cut_this_round:
          continue
        if self.random.random() < self.params.link_recovery_rate:
          self.simulation.topology.repair_link(link)

    crashed_this_round = crash_switches()
    restart_switches(crashed_this_round)
    cut_this_round = sever_links()
    repair_links(cut_this_round)

  def check_timeouts(self):
    # Interpose on timeouts
    pass

  def fuzz_traffic(self):
    if not self.simulation.dataplane_trace:
      # randomly generate messages from switches
      for software_switch in self.simulation.topology.live_switches:
        if self.random.random() < self.params.traffic_generation_rate:
          if len(software_switch.ports) > 0:
            msg.event("injecting a random packet")
            traffic_type = "icmp_ping"
            # Generates a packet, and feeds it to the software_switch
            self.traffic_generator.generate(traffic_type, software_switch)

class Interactive(ControlFlow):
  '''
  Presents an interactive prompt for injecting events and
  checking for invariants at the users' discretion
  '''
  # TODO(cs): rather than just prompting "Continue to next round? [Yn]", allow
  #           the user to examine the state of the network interactively (i.e.,
  #           provide them with the normal POX cli + the simulated events
  def __init__(self):
    ControlFlow.__init__(self)
    self.logical_time = 0
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

  def simulate(self, simulation):
    self.simulation = simulation
    self.simulation.bootstrap()
    self.loop()

  def loop(self):
    while True:
      # TODO(cs): print out the state of the network at each timestep? Take a
      # verbose flag..
      self.logical_time += 1
      self.invariant_check_prompt()
      self.dataplane_trace_prompt()
      answer = msg.raw_input('Continue to next round? [Yn]').strip()
      if answer != '' and answer.lower() != 'y':
        self.stop()
        break

  def invariant_check_prompt(self):
    answer = msg.raw_input('Check Invariants? [Ny]')
    if answer != '' and answer.lower() != 'n':
      msg.interactive("Which one?")
      msg.interactive("  'l' - loops")
      msg.interactive("  'b' - blackholes")
      msg.interactive("  'r' - routing consistency")
      msg.interactive("  'c' - connectivity")
      msg.interactive("  'o' - omega")
      answer = msg.raw_input("> ")
      result = None
      if answer.lower() == 'l':
        result = self.invariant_checker.check_loops(self.simulation)
      elif answer.lower() == 'b':
        result = self.invariant_checker.check_blackholes(self.simulation)
      elif answer.lower() == 'r':
        result = self.invariant_checker.check_routing_consistency(self.simulation)
      elif answer.lower() == 'c':
        result = self.invariant_checker.check_connectivity(self.simulation)
      elif answer.lower() == 'o':
        result = self.invariant_checker.check_correspondence(self.simulation)
      else:
        log.warn("Unknown input...")

      if result is None:
        return
      else:
        msg.interactive("Result: %s" % str(result))

  def dataplane_trace_prompt(self):
    if self.simulation.dataplane_trace:
      while True:
        answer = msg.raw_input('Feed in next dataplane event? [Ny]')
        if answer != '' and answer.lower() != 'n':
          self.simulation.inject_trace_event()
        else:
          break
