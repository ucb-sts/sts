#!/usr/bin/env python
# Nom nom nom nom

# TODO: future feature: colored cli prompts to make packets vs. crashes
#       vs. whatever easy to distinguish

# TODO: rather than just prompting "Continue to next round? [Yn]", allow
#       the user to examine the state of the network interactively (i.e.,
#       provide them with the normal POX cli + the simulated events

import pox.openflow.libopenflow_01 as of
from pox.lib.revent import EventMixin

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
  # TODO: future feature: split this into Manager superclass and
  # simulator, emulator subclasses. Use vector clocks to take
  # consistent snapshots of emulated network
  
  # TODO: do we need to define more event types? e.g., packet delivered,
  # controller crashed, etc...
  
  """
  This is part of a testing framework for controller applications. It
  acts as a replacement for pox.topology.

  Given a set of event handlers (registered by a controller application),
  it will inject intelligently chosen mock events (and observe
  their responses?)
  """
  def __init__(self, child_processes):
    self.child_processes = child_processes
    self.running = False
    self.panel = None
    self.switch_impls = []

    # TODO: make it easier for client to tweak these
    self.switch_failure_rate = 0.01
    self.switch_recovery_rate = 0.5
    self.control_channel_failure_rate = 0.0
    self.control_channel_recovery_rate = 0.0
    self.controlplane_delay_rate = 0.5
    self.dataplane_drop_rate = 0.5
    self.dataplane_delay_rate = 0.5
    self.traffic_generation_rate = 0.05

    # Logical time (round #) for the simulation execution
    self.logical_time = 0
    # TODO: take a timestep parameter for how long
    # each logical timestep should last?

    # events for this round
    self.sorted_events = []
    self.in_transit_messages = set()
    self.dropped_messages = set()
    self.failed_switches = set()
    self.failed_controllers = set()
    self.cancelled_timeouts = set() # ?

    # Statistics to print on exit
    self.packets_sent = 0

    # Make execution deterministic to allow the user to easily replay
    self.seed = 0.0
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

  def start(self, panel, switch_impls):
    """
    Start the fuzzer loop!
    """
    log.debug("Starting fuzz loop")
    self.panel = panel
    self.switch_impls = switch_impls
    self.loop()

  def loop(self):
    while True:
      self.logical_time += 1
      self.trigger_events()
      msg.event("Round %d completed." % self.logical_time)
      # TODO: print out the state of the network at each timestep? Take a
      # verbose flag..
      self.invariant_check_prompt()
      answer = msg.raw_input('Continue to next round? [Yn]').strip()
      if answer != '' and answer.lower() != 'y':
        self.stop()

  def stop(self):
    self.running = False
    msg.event("Fuzzer stopping...")
    msg.event("Killing controllers...")
    for child in self.child_processes:
      # SIGTERM for now
      child.terminate()
    msg.event("Total rounds completed: %d" % self.logical_time)
    msg.event("Total packets sent: %d" % self.packets_sent)
    os._exit(0)

  # ============================================ #
  #     Bookkeeping methods                      #
  # ============================================ #
  def all_switches(self):
    """ Return all switch_impls currently registered """
    return self.switch_impls

  def crashed_switches(self):
    """ Return the switch_impls which are currently down """
    return filter(lambda switch_impl : switch_impl.failed, self.all_switches())

  def live_switches(self):
    """ Return the switch_impls which are currently up """
    return filter(lambda switch_impl : not switch_impl.failed, self.all_switches())

  # ============================================ #
  #      Methods to trigger events               #
  # ============================================ #
  def trigger_events(self):
    self.check_dataplane()
    self.check_controlplane()
    self.check_switch_crashes()
    self.check_control_channel_crashes()
    self.check_timeouts()
    self.fuzz_traffic()

  def check_dataplane(self):
    ''' Decide whether to delay, drop, or deliver packets '''
    # TODO: interpose on panel 
    #for msg in self.in_transit_messages:
    #  if self.random.random() < self.dataplane_delay_rate:
    #    # Delay the message
    #    msg.delayed_rounds += 1
    #  elif self.random.random() < self.dataplane_drop_rate:
    #    # Drop the message
    #    self.dropped_messages.add(msg)
    #    self.in_transit_messages.remove(msg)
    #  else:
    #    # TODO: deliver the message
    #    pass
    pass
    
  def check_controlplane(self):
    ''' Decide whether to delay or deliver packets '''
    def check_deliver(switch_impl, type, give_permission):
        if self.random.random() < self.controlplane_delay_rate:
          log.debug("Giving permission for control plane %s for %s" % (type, str(switch_impl)))
          give_permission()
        else:
          log.debug("Delaying control plane %s for %s" % (type, str(switch_impl)))
        
    for switch_impl in self.live_switches():
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
      crashed = set()
      for switch_impl in self.live_switches():
        if self.random.random() < self.switch_failure_rate:
          msg.event("Crashing switch_impl %s" % str(switch_impl))
          switch_impl.fail()
          crashed.add(switch_impl)
      return crashed

    def restart_switches(crashed_this_round):
      for switch_impl in self.crashed_switches():
        if switch_impl in crashed_this_round:
          continue
        if self.random.random() < self.switch_recovery_rate:
          msg.event("Rebooting switch_impl %s" % str(switch_impl))
          switch_impl.recover()

    def cut_links():
      pass

    def repair_links():
      pass

    crashed = crash_switches()
    restart_switches(crashed)
    cut_links()
    repair_links()
  
  def check_control_channel_crashes(self):
    pass

  def check_timeouts(self):
    # Interpose on timeouts
    pass

  def fuzz_traffic(self):
    # randomly generate messages from switches
    # TODO: future feature: trace-driven packet generation
    for switch_impl in self.live_switches():
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

