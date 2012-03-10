#!/usr/bin/env python
# Nom nom nom nom

# TODO: future feature: colored cli prompts to make packets vs. crashes
#       vs. whatever easy to distinguish

# TODO: rather than just prompting "Continue to next round? [Yn]", allow
#       the user to examine the state of the network interactively (i.e.,
#       provide them with the normal POX cli + the simulated events

import pox.openflow.libopenflow_01 as of
from pox.lib.revent import EventMixin
from debugger_entities import Link

from traffic_generator import TrafficGenerator
from invariant_checker import InvariantChecker

import sys
import threading
import signal
import subprocess
import socket
import time
import random
import os
import logging

log = logging.getLogger("debugger")

class msg():
  BEGIN = '\033[1;'
  END = '\033[1;m'

  GRAY, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, CRIMSON = map(lambda num: str(num) + "m", range(30, 39))
  B_GRAY, B_RED, B_GREEN, B_YELLOW, B_BLUE, B_MAGENTA, B_CYAN, B_WHITE, B_CRIMSON =  map(lambda num: str(num) + "m", range(40, 49))

  @staticmethod
  def interactive(message):
    # todo: would be nice to simply give logger a color arg, but that doesn't exist...
    print msg.BEGIN + msg.WHITE + message + msg.END

  @staticmethod
  def event(message):
    print msg.BEGIN + msg.CYAN + message + msg.END

  @staticmethod
  def raw_input(message):
    prompt = msg.BEGIN + msg.WHITE + message + msg.END
    return raw_input(prompt)

  @staticmethod
  def success(message):
    print msg.BEGIN + msg.B_GREEN + msg.BEGIN + msg.WHITE + message + msg.END

  @staticmethod
  def fail(message):
    print msg.BEGIN + msg.B_RED + msg.BEGIN + msg.WHITE + message + msg.END

class FuzzTester (EventMixin):
  """
  This is part of a testing framework for controller applications. It
  acts as a replacement for pox.topology.

  Given a set of event handlers (registered by a controller application),
  it will inject intelligently chosen mock events (and observe
  their responses?)
  """
  def __init__(self, interactive=True, random_seed=0.0, delay=0.1):
    self.interactive = interactive
    self.running = False
    self.panel = None
    self.switch_impls = []

    self.delay = delay

    # TODO: make it easier for client to tweak these
    self.switch_failure_rate = 0.01
    self.switch_recovery_rate = 0.5
    self.control_channel_failure_rate = 0.0
    self.control_channel_recovery_rate = 0.0
    self.controlplane_delay_rate = 0.5
    self.dataplane_drop_rate = 0.01
    self.dataplane_delay_rate = 0.05
    self.link_failure_rate = 0.01
    self.link_recovery_rate = 0.25
    self.traffic_generation_rate = 0.05

    # Logical time (round #) for the simulation execution
    self.logical_time = 0

    # Metatdata for simulated failures
    # debugger.debugger_entities.Link objects
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
    self.invariant_checker = InvariantChecker(self)

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

  def simulate(self, panel, switch_impls, links, steps=None):
    """
    Start the fuzzer loop!
    """
    log.debug("Starting fuzz loop")
    self.panel = panel
    self.switch_impls = set(switch_impls)
    self.dataplane_links = set(links)
    self.loop(steps)

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
        answer = msg.raw_input('Continue to next round? [Yn]').strip()
        if answer != '' and answer.lower() != 'y':
          self.stop()
      else:
        time.sleep(self.delay)

  def stop(self):
    self.running = False

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
        link = Link(dp_event.switch, dp_event.port, next_hop, next_port) 
        if not link in self.cut_links:
          msg.event("Forwarding dataplane event")
          # Forward the message
          self.panel.permit_dp_event(dp_event)
    
  def check_controlplane(self):
    ''' Decide whether to delay or deliver packets '''
    def check_deliver(switch_impl, type, give_permission):
        if self.random.random() < self.controlplane_delay_rate:
          log.debug("Giving permission for control plane %s for %s" % (type, str(switch_impl)))
          give_permission()
        else:
          log.debug("Delaying control plane %s for %s" % (type, str(switch_impl)))
        
    for switch_impl in self.live_switches:
      # Check reads
      # TODO: shouldn't be sticking our hands into switch_impl._connection
      if switch_impl._connection.io_worker.has_pending_receives():
        check_deliver(switch_impl, "receive", switch_impl._connection.io_worker.permit_receive)
      
      # Check writes
      if switch_impl._connection.io_worker.has_pending_sends():
        check_deliver(switch_impl, "send", switch_impl._connection.io_worker.permit_send)

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
      cut_this_round = set()
      for link in self.live_links:
        if self.random.random() < self.link_failure_rate:
          msg.event("Cutting link %s" % str(link))
          self.cut_links.add(link)
          cut_this_round.add(link)
      return cut_this_round

    def repair_links(cut_this_round):
      for link in set(self.cut_links):
        if link in crashed_this_round:
          continue
        if self.random.random() < self.link_recovery_rate:
          msg.event("Restoring link %s" % str(link))
          self.cut_links.remove(link)

    crashed_this_round = crash_switches()
    restart_switches(crashed_this_round)
    cut_this_round = sever_links()
    repair_links(cut_this_round)
  
  def check_timeouts(self):
    # Interpose on timeouts
    pass

  def fuzz_traffic(self):
    # randomly generate messages from switches
    # TODO: future feature: trace-driven packet generation
    for switch_impl in self.live_switches:
      if self.random.random() < self.traffic_generation_rate:
        # FIXME do something smarter here than just generate packet ins
        msg.event("injecting a random packet")
        # event_type = self.random.choice(switch_impl._eventMixin_handlers.keys()) 
        traffic_type = "icmp_ping"
        # Generates a packet, and feeds it to the switch_impl
        self.traffic_generator.generate(traffic_type, switch_impl)

  def invariant_check_prompt(self):
    answer = msg.raw_input('Check Invariants? [Ny]')
    if answer != '' and answer.lower() != 'n':
      msg.interactive("Which one?")
      msg.interactive("  'l' - loops")
      msg.interactive("  'b' - blackholes")
      msg.interactive("  'r' - routing consistency")
      msg.interactive("  'c' - connectivity")
      answer = msg.raw_input("  ")
      result = None
      if answer.lower() == 'l':
        result = self.invariant_checker.check_loops()
      elif answer.lower() == 'b':
        result = self.invariant_checker.check_blackholes()
      elif answer.lower() == 'r':
        result = self.invariant_checker.check_routing_consistency()
      elif answer.lower() == 'c':
        result = self.invariant_checker.check_connectivity()
      else:
        log.warn("Unknown input...")

      if not result:
        return
      elif result == "sat":
        msg.success("Invariant holds!")
      else:
        msg.fail("Invariant violated!")

