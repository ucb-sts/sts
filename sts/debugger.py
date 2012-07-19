#!/usr/bin/env python
# Nom nom nom nom

# TODO: future feature: colored cli prompts to make packets vs. crashes
#       vs. whatever easy to distinguish

# TODO: rather than just prompting "Continue to next round? [Yn]", allow
#       the user to examine the state of the network interactively (i.e.,
#       provide them with the normal POX cli + the simulated events

import pox.openflow.libopenflow_01 as of
from pox.lib.revent import EventMixin
from debugger_entities import Link, Host

from traffic_generator import TrafficGenerator
from invariant_checker import InvariantChecker
from trace_runner import Context
from sts.experiment_config_lib import Controller

import sys
import threading
import signal
import subprocess
import socket
import time
import random
import os
import logging
import pickle

from sts.console import msg

log = logging.getLogger("debugger")

class FuzzTester (EventMixin):
  """
  This is part of a testing framework for controller applications. It
  acts as a replacement for pox.topology.

  Given a set of event handlers (registered by a controller application),
  it will inject intelligently chosen mock events (and observe
  their responses?)
  """
  def __init__(self, fuzzer_params="fuzzer_params.cfg", interactive=True,
               check_interval=35, trace_interval=10, random_seed=0.0,
               delay=0.1, dataplane_trace=None, control_socket=None, floodlight_port=8080):
    self.interactive = interactive
    self.check_interval = check_interval
    self.trace_interval = trace_interval
    # Format of trace file is a pickled array of DataplaneEvent objects
    self.dataplane_trace = None
    if dataplane_trace:
      self.dataplane_trace = pickle.load(file(dataplane_trace))
    self.running = False
    self.panel = None
    self.switch_impls = []

    self.delay = delay

    self._load_fuzzer_params(fuzzer_params)

    # Logical time (round #) for the simulation execution
    self.logical_time = 0

    # Metatdata for simulated failures
    # sts.debugger_entities.Link objects
    self.cut_links = set()
    # SwitchOutDpEvent objects
    self.dropped_dp_events = []
    # SwitchImpl objects
    self.failed_switches = set()
    # topology.Controller objects
    self.failed_controllers = set()
    # ?
    self.cancelled_timeouts = set()

    # Statistics to print on exit
    self.packets_sent = 0

    # Make execution deterministic to allow the user to easily replay
    self.seed = random_seed
    self.random = random.Random(self.seed)
    self.traffic_generator = TrafficGenerator(self.random)
    self.invariant_checker = InvariantChecker(control_socket, floodlight_port)

    # TODO: future feature: log all events, and allow user to (interactively)
    # replay the execution
    # self.replay_logger = ReplayLogger()
    # Write the seed out to the replay log as the first 4 bytes

    # TODO: future feature: allow the user to interactively choose the order
    # events occur for each round, whether to delay, drop packets, fail nodes,
    # etc.
    # self.failure_lvl = [
    #   NOTHING,    # Everything is handled by the random number generator
    #   CRASH,      # The user only controls node crashes and restarts
    #   DROP,       # The user also controls message dropping
    #   DELAY,      # The user also controls message delays
    #   EVERYTHING  # The user controls everything, including message ordering
    # ]

    # TODO: need a mechanism for signaling  when the distributed controller handshake has completed

  def _load_fuzzer_params(self, fuzzer_params):
    if os.path.exists(fuzzer_params):
      # TODO: more pythonic way to read lines (currently on a plane...)
      # TODO: even better: there is probably a library for parsing config files
      for line in file(fuzzer_params).read().splitlines():
        if line == "[fuzzer]":
          # TODO: handle more directives other than [fuzzer]
          continue
        (kw, eq, val) = line.split()
        val = float(val)
        setattr(self, kw, val)
    else:
      # TODO: default values in case fuzzer_config is not present / missing directives
      raise IOError("Could not find logging config file: %s" % fuzzer_params)
    
  def type_check_dataplane_trace(self):
    if self.dataplane_trace is not None:
      for dp_event in self.dataplane_trace:
        if dp_event.interface not in self.interface2host:
          raise RuntimeError("Dataplane trace does not type check (%s)" % str(dp_event.interface))

  def simulate(self, panel, switch_impls, network_links, hosts, access_links, steps=None):
    """
    Start the fuzzer loop!
    """
    log.debug("Starting fuzz loop")
    self.panel = panel
    self.switch_impls = set(switch_impls)
    self.dataplane_links = set(network_links)
    self.hosts = hosts
    self.interface2host = {}
    for host in hosts:
      for interface in host.interfaces:
        self.interface2host[interface] = host
    self.access_links = set(access_links)
    self.type_check_dataplane_trace()
    self.loop(steps)

  def trace(self, round2Command, topology_generator, steps=None, procs=[]):
    # HOTNETS HACK this is just the rewritten loop that we need for automation for the floodlight bug :P
    # generate context
    self.topology_generator = topology_generator # HACK called by setup_topology, which is called by Context.boot_topology
    self.booted = False
    self.running = True
    context = Context(self, procs)
    end_time = self.logical_time + steps if steps else sys.maxint

    # This loop is purely controlled by commands in the trace, for the most part
    while self.running and self.logical_time < end_time:
      self.logical_time += 1
      if self.logical_time in round2Command:
        for cmd in round2Command[self.logical_time]:
          cmd(context)
      self._trace_trigger_events()
      msg.event("Round %d completed." % self.logical_time)

      time.sleep(self.delay)

  def setup_topology(self):
    (panel, switch_impls, network_links, hosts, access_links) = self.topology_generator()
    del self.topology_generator # don't want to call it twice :P
    self.panel = panel
    self.switch_impls = set(switch_impls)
    self.switch_impls_ordered = switch_impls # HACK for toggling switch up/down
    self.dataplane_links = set(network_links)
    self.hosts = hosts
    self.access_links = access_links
    self.interface2host = {}
    for host in hosts:
      for interface in host.interfaces:
        self.interface2host[interface] = host
    self.booted = True

  def check_correspondence(self,fl_port): # HACK this only works for floodlight -_-
    if self.booted:
      self.invariant_checker.set_floodlight_port(fl_port)
      result = self.invariant_checker.check_correspondence(self.live_switches, self.live_links, self.access_links)
      if result:
        msg.fail("There were policy violations!")
      else:
        msg.interactive("No policy violations!")

  def stop_switch(self,switch_index):
    self.switch_impls_ordered[switch_index].fail()

  def start_switch(self,switch_index,ports=[]): # the ports that it should connect to
    swtch = self.switch_impls_ordered[switch_index]
    swtch.clear_controller_info()
    for p in ports:
      swtch.add_controller_info(Controller(port=p))
    swtch.recover()

  def loop(self, steps=None):
    self.running = True
    end_time = self.logical_time + steps if steps else sys.maxint
    while self.running and self.logical_time < end_time:
      self.logical_time += 1
      self.trigger_events()
      msg.event("Round %d completed." % self.logical_time)

      if self.interactive:
        # TODO: print out the state of the network at each timestep? Take a
        # verbose flag..
        self.invariant_check_prompt()
        self.dataplane_trace_prompt()
        answer = msg.raw_input('Continue to next round? [Yn]').strip()
        if answer != '' and answer.lower() != 'y':
          self.stop()
          break
      else: # not self.interactive
        if (self.logical_time % self.check_interval) == 0:
          # Time to run correspondence!
          # spawn a thread for running correspondence. Make sure the controller doesn't 
          # think we've gone idle though: send OFP_ECHO_REQUESTS every few seconds
          # TODO: this is a HACK
          def do_correspondence():
            any_policy_violations = self.invariant_checker.check_correspondence(self.live_switches, self.live_links, self.access_links)
            if any_policy_violations:
              msg.fail("There were policy-violations!")
            else:
              msg.interactive("No policy-violations!")
          thread = threading.Thread(target=do_correspondence)
          thread.start()
          while thread.isAlive():
            for switch in self.live_switches:
              # connection -> deferred io worker -> io worker
              switch.send(of.ofp_echo_request().pack())
            thread.join(2.0)
     
        if self.dataplane_trace and (self.logical_time % self.trace_interval) == 0:
          self.inject_trace_event()
          
        time.sleep(self.delay)

  def stop(self):
    self.running = False
    
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
        result = self.invariant_checker.check_loops()
      elif answer.lower() == 'b':
        result = self.invariant_checker.check_blackholes()
      elif answer.lower() == 'r':
        result = self.invariant_checker.check_routing_consistency()
      elif answer.lower() == 'c':
        result = self.invariant_checker.check_connectivity()
      elif answer.lower() == 'o':
        result = self.invariant_checker.check_correspondence(self.live_switches,
                                                             self.live_links,
                                                             self.access_links)
      else:
        log.warn("Unknown input...")

      if result is None:
        return
      else:
        msg.interactive("Result: %s" % str(result))
        
  def dataplane_trace_prompt(self):
    if self.dataplane_trace:
      while True:
        answer = msg.raw_input('Feed in next dataplane event? [Ny]')
        if answer != '' and answer.lower() != 'n':
          self.inject_trace_event()
        else:
          break

  # ============================================ #
  #     Bookkeeping methods                      #
  # ============================================ #
  @property
  def live_switches(self):
    """ Return the switch_impls which are currently up """
    return self.switch_impls - self.failed_switches

  @property
  def live_links(self):
    return self.dataplane_links - self.cut_links

  # ============================================ #
  #      Methods to trigger events               #
  # ============================================ #
  def trigger_events(self):
    self.check_dataplane()
    self.check_controlplane()
    self.check_switch_crashes()
    self.check_timeouts()
    self.fuzz_traffic()

  def _trace_trigger_events(self):
    if self.booted:
      self.check_dataplane()
      self.check_controlplane()
      self.check_switch_crashes()
      self.check_timeouts()

  def check_dataplane(self):
    ''' Decide whether to delay, drop, or deliver packets '''
    for dp_event in set(self.panel.get_buffered_dp_events()):
      if self.random.random() < self.dataplane_delay_rate:
        msg.event("Delaying dataplane event")
        # (Monkey patch on a delay counter)
        if not hasattr(dp_event, "delayed_rounds"):
          dp_event.delayed_rounds = 0
        dp_event.delayed_rounds += 1
      elif self.random.random() < self.dataplane_drop_rate:
        msg.event("Dropping dataplane event")
        # Drop the message
        self.panel.drop_dp_event(dp_event)
        self.dropped_dp_events.append(dp_event)
      else:
        (next_hop, next_port) = self.panel.get_connected_port(dp_event.switch, dp_event.port)
        if type(dp_event.node) == Host or type(next_hop) == Host:
          # TODO: model access link failures:
          self.panel.permit_dp_event(dp_event)
        else:
          link = Link(dp_event.switch, dp_event.port, next_hop, next_port)
          if not link in self.cut_links:
            msg.event("Forwarding dataplane event")
            # Forward the message
            self.panel.permit_dp_event(dp_event)

  def check_controlplane(self):
    ''' Decide whether to delay or deliver packets '''
    def check_deliver(switch_impl, type, give_permission):
      if self.random.random() < self.controlplane_delay_rate:
        log.debug("Delaying control plane %s for %s" % (type, str(switch_impl)))
      else:
        log.debug("Giving permission for control plane %s for %s" % (type, str(switch_impl)))
        give_permission()

    for switch_impl in self.live_switches:
      # Check reads
      # TODO: shouldn't be sticking our hands into switch_impl._connection
      for c in switch_impl.connections:
        if c.io_worker.has_pending_receives():
          check_deliver(switch_impl, "receive", c.io_worker.permit_receive)

      # Check writes
      for c in switch_impl.connections:
        if c.io_worker.has_pending_sends():
          check_deliver(switch_impl, "send", c.io_worker.permit_send)

  def check_switch_crashes(self):
    ''' Decide whether to crash or restart switches, links and controllers '''
    def crash_switches():
      crashed_this_round = set()
      for switch_impl in self.live_switches:
        if self.random.random() < self.switch_failure_rate:
          msg.event("Crashing switch_impl %s" % str(switch_impl))
          switch_impl.fail()
          crashed_this_round.add(switch_impl)
          self.failed_switches.add(switch_impl)
      return crashed_this_round

    def restart_switches(crashed_this_round):
      for switch_impl in set(self.failed_switches):
        if switch_impl in crashed_this_round:
          continue
        if self.random.random() < self.switch_recovery_rate:
          msg.event("Rebooting switch_impl %s" % str(switch_impl))
          switch_impl.recover()
          self.failed_switches.remove(switch_impl)

    def sever_links():
      # TODO: model administratively down links? (OFPPC_PORT_DOWN)
      cut_this_round = set()
      for link in self.live_links:
        if self.random.random() < self.link_failure_rate:
          msg.event("Cutting link %s" % str(link))
          self.cut_links.add(link)
          link.start_switch_impl.take_port_down(link.start_port)
          cut_this_round.add(link)
      return cut_this_round

    def repair_links(cut_this_round):
      for link in set(self.cut_links):
        if link in cut_this_round:
          continue
        if self.random.random() < self.link_recovery_rate:
          msg.event("Restoring link %s" % str(link))
          link.start_switch_impl.bring_port_up(link.start_port)
          self.cut_links.remove(link)

    crashed_this_round = crash_switches()
    restart_switches(crashed_this_round)
    cut_this_round = sever_links()
    repair_links(cut_this_round)

  def check_timeouts(self):
    # Interpose on timeouts
    pass
  
  def inject_trace_event(self):
    ''' Precondition: --trace is set '''
    if len(self.dataplane_trace) == 0:
      log.warn("No more trace inputs to inject!")
      return
    else:
      log.info("Injecting trace input")
      dp_event = self.dataplane_trace.pop(0)
      host = self.interface2host[dp_event.interface]
      if not host:
        log.warn("Host %s not present" % str(host))
        return
      host.send(dp_event.interface, dp_event.packet)

  def fuzz_traffic(self):
    if not self.dataplane_trace:
      # randomly generate messages from switches
      for switch_impl in self.live_switches:
        if self.random.random() < self.traffic_generation_rate:
          if len(switch_impl.ports) > 0:
            msg.event("injecting a random packet")
            traffic_type = "icmp_ping"
            # Generates a packet, and feeds it to the switch_impl
            self.traffic_generator.generate(traffic_type, switch_impl)
