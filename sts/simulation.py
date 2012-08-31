#!/usr/bin/env python
# Nom nom nom nom

'''
Encapsulates the state of the simulation, including:
  - The controllers
  - The topology
  - Dataplane forwarding
  - (Optionally) the dataplane trace
  - Metadata (e.g. # of failures)
'''

from entities import Link, Host

import logging
import pickle

from sts.console import msg

log = logging.getLogger("simulation")

class Simulation (object):
  """
  Maintains the current state of:
    - The controllers
    - The topology
    - Dataplane forwarding
    - (Optionally) the dataplane trace
    - Metadata (e.g. # of failures)

  Also provides functionality for triggering failures,
  causing packet delays, etc.
  """
  def __init__(self, controllers, topology, patch_panel_class,
               dataplane_trace=None):
    self.controllers = controllers
    self.topology = topology
    self.patch_panel = patch_panel_class(topology.switches, topology.hosts,
                                         topology.get_connected_port)

    # Format of trace file is a pickled array of DataplaneEvent objects
    self.dataplane_trace = None
    if dataplane_trace:
      self.dataplane_trace = pickle.load(file(dataplane_trace))

    # Hashmap used to inject packets from the dataplane_trace
    self.interface2host = {}
    for host in self.topology.hosts:
      for interface in host.interfaces:
        self.interface2host[interface] = host
    self._type_check_dataplane_trace()

    # Metatdata for simulated failures
    # TODO(cs): move these into topology
    # sts.entities.Link objects
    self.cut_links = set()
    # SwitchImpl objects
    self.failed_switches = set()
    # topology.Controller objects
    self.failed_controllers = set()

    # SwitchOutDpEvent objects
    self.dropped_dp_events = []

    # Statistics to print on exit
    self.packets_sent = 0

  def _type_check_dataplane_trace(self):
    if self.dataplane_trace is not None:
      for dp_event in self.dataplane_trace:
        if dp_event.interface not in self.interface2host:
          raise RuntimeError("Dataplane trace does not type check (%s)" %
                              str(dp_event.interface))

  # ============================================ #
  #     `Getter' methods                         #
  # ============================================ #
  @property
  def live_switches(self):
    """ Return the switch_impls which are currently up """
    return set(self.topology.switches) - self.failed_switches

  @property
  def cp_connections_with_pending_receives(self):
    for switch_impl in self.live_switches:
      for c in switch_impl.connections:
        if c.io_worker.has_pending_receives():
          yield c

  @property
  def cp_connections_with_pending_sends(self):
    for switch_impl in self.live_switches:
      for c in switch_impl.connections:
        if c.io_worker.has_pending_sends():
          yield c

  @property
  def live_links(self):
    return self.topology.network_links - self.cut_links

  @property
  def queued_dataplane_events(self):
    return set(self.patch_panel.get_buffered_dp_events())

  # ============================================ #
  #     Event Injection methods                  #
  # ============================================ #
  def kill_controller(self, controller):
    pass

  def reboot_controller(self, controller):
    pass

  def send_policy_request(self, controller, api_call):
    pass

  def delay_dp_event(self, dp_event):
    msg.event("Delaying dataplane event")
    # (Monkey patch on a delay counter)
    if not hasattr(dp_event, "delayed_rounds"):
      dp_event.delayed_rounds = 0
    dp_event.delayed_rounds += 1

  def drop_dp_event(self, dp_event):
    msg.event("Dropping dataplane event")
    # Drop the message
    self.patch_panel.drop_dp_event(dp_event)
    self.dropped_dp_events.append(dp_event)

  def forward_dp_event(self, dp_event):
   (next_hop, next_port) = self.patch_panel.get_connected_port(dp_event.switch,
                                                               dp_event.port)
   if type(dp_event.node) == Host or type(next_hop) == Host:
     # TODO(cs): model access link failures:
     self.patch_panel.permit_dp_event(dp_event)
   else:
     link = Link(dp_event.switch, dp_event.port, next_hop, next_port)
     if not link in self.cut_links:
       msg.event("Forwarding dataplane event")
       # Forward the message
       self.patch_panel.permit_dp_event(dp_event)

  def permit_cp_send(self, connection):
    # pre: switch_impl.io_worker.has_pending_sends()
    msg.event("Giving permission for control plane send for %s" % connection)
    connection.io_worker.permit_send()

  def delay_cp_send(self, connection):
    msg.event("Delaying control plane send for %s" % connection)
    # update # delayed rounds?

  def permit_cp_receive(self, connection):
    # pre: switch_impl.io_worker.has_pending_sends()
    msg.event("Giving permission for control plane receive for %s" % connection)
    connection.io_worker.permit_receive()

  def delay_cp_receive(self, connection):
    msg.event("Delaying control plane receive for %s" % connection)
    # update # delayed rounds?

  def crash_switch(self, switch_impl):
    msg.event("Crashing switch_impl %s" % str(switch_impl))
    switch_impl.fail()
    self.failed_switches.add(switch_impl)

  def recover_switch(self, switch_impl):
    msg.event("Rebooting switch_impl %s" % str(switch_impl))
    switch_impl.recover()
    self.failed_switches.remove(switch_impl)

  def sever_link(self, link):
    msg.event("Cutting link %s" % str(link))
    self.cut_links.add(link)
    link.start_switch_impl.take_port_down(link.start_port)

  def repair_link(self, link):
    msg.event("Restoring link %s" % str(link))
    link.start_switch_impl.bring_port_up(link.start_port)
    self.cut_links.remove(link)

  def inject_trace_event(self):
    if not self.dataplane_trace or len(self.dataplane_trace) == 0:
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
