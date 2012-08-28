#!/usr/bin/env python
# Nom nom nom nom

'''
Encapsulates the state of the simulation (including the state of the
controllers, and the state of the topology).
'''

import pox.openflow.libopenflow_01 as of
from pox.lib.revent import EventMixin
from debugger_entities import Link, Host

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
import pickle

from sts.console import msg

log = logging.getLogger("simulation")

class FuzzTester (EventMixin):
  """
  This is part of a testing framework for controller applications. It
  acts as a replacement for pox.topology.

  Given a set of event handlers (registered by a controller application),
  it will inject intelligently chosen mock events (and observe
  their responses?)
  """
  def __init__(self, fuzzer_params="configs/fuzzer_params.cfg", interactive=True,
               check_interval=35, trace_interval=10, random_seed=0.0,
               delay=0.1, dataplane_trace=None, control_socket=None):
    self.topology.switches = []

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
    self.interface2host = {}
    for host in self.topology.hosts:
      for interface in host.interfaces:
        self.interface2host[interface] = host
    self.type_check_dataplane_trace()
    self.loop(steps)
          
  # ============================================ #
  #     Bookkeeping methods                      #
  # ============================================ #
  @property
  def live_switches(self):
    """ Return the switch_impls which are currently up """
    return self.topology.switches - self.failed_switches

  @property
  def live_links(self):
    return self.topology.network_links - self.cut_links

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
    for dp_event in set(self.topology.panel.get_buffered_dp_events()):
      if self.random.random() < self.params.dataplane_delay_rate:
        msg.event("Delaying dataplane event")
        # (Monkey patch on a delay counter)
        if not hasattr(dp_event, "delayed_rounds"):
          dp_event.delayed_rounds = 0
        dp_event.delayed_rounds += 1
      elif self.random.random() < self.params.dataplane_drop_rate:
        msg.event("Dropping dataplane event")
        # Drop the message
        self.topology.panel.drop_dp_event(dp_event)
        self.dropped_dp_events.append(dp_event)
      else:
        (next_hop, next_port) = self.topology.panel.get_connected_port(dp_event.switch, dp_event.port)
        if type(dp_event.node) == Host or type(next_hop) == Host:
          # TODO: model access link failures:
          self.topology.panel.permit_dp_event(dp_event)
        else:
          link = Link(dp_event.switch, dp_event.port, next_hop, next_port)
          if not link in self.cut_links:
            msg.event("Forwarding dataplane event")
            # Forward the message
            self.topology.panel.permit_dp_event(dp_event)

  def check_controlplane(self):
    ''' Decide whether to delay or deliver packets '''
    def check_deliver(switch_impl, type, give_permission):
      if self.random.random() < self.params.controlplane_delay_rate:
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
        if self.random.random() < self.params.switch_failure_rate:
          msg.event("Crashing switch_impl %s" % str(switch_impl))
          switch_impl.fail()
          crashed_this_round.add(switch_impl)
          self.failed_switches.add(switch_impl)
      return crashed_this_round

    def restart_switches(crashed_this_round):
      for switch_impl in set(self.failed_switches):
        if switch_impl in crashed_this_round:
          continue
        if self.random.random() < self.params.switch_recovery_rate:
          msg.event("Rebooting switch_impl %s" % str(switch_impl))
          switch_impl.recover()
          self.failed_switches.remove(switch_impl)

    def sever_links():
      # TODO: model administratively down links? (OFPPC_PORT_DOWN)
      cut_this_round = set()
      for link in self.live_links:
        if self.random.random() < self.params.link_failure_rate:
          msg.event("Cutting link %s" % str(link))
          self.cut_links.add(link)
          link.start_switch_impl.take_port_down(link.start_port)
          cut_this_round.add(link)
      return cut_this_round

    def repair_links(cut_this_round):
      for link in set(self.cut_links):
        if link in cut_this_round:
          continue
        if self.random.random() < self.params.link_recovery_rate:
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
        if self.random.random() < self.params.traffic_generation_rate:
          if len(switch_impl.ports) > 0:
            msg.event("injecting a random packet")
            traffic_type = "icmp_ping"
            # Generates a packet, and feeds it to the switch_impl
            self.traffic_generator.generate(traffic_type, switch_impl)
