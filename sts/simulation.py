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
    - The controllers: a map from the controller uuid to the Controller
      object. See ControllerConfig for more details.
    - The topology
    - Dataplane forwarding
    - (Optionally) the dataplane trace
    - Metadata (e.g. # of failures)

  Also provides functionality for triggering failures,
  causing packet delays, etc.
  """
  def __init__(self, controllers, topology, patch_panel_class,
               dataplane_trace=None):
    self.uuid2controller = {
      controller.uuid : controller
      for controller in controllers
      }
    self.topology = topology
    self.patch_panel = patch_panel_class(topology.switches, topology.hosts,
                                         topology.get_connected_port)

    self.dataplane_trace = dataplane_trace

  # ============================================ #
  #     `Getter' methods                         #
  # ============================================ #

  @property
  def cp_connections_with_pending_receives(self):
    for switch_impl in self.topology.live_switches:
      for c in switch_impl.connections:
        if c.io_worker.has_pending_receives():
          yield c

  @property
  def cp_connections_with_pending_sends(self):
    for switch_impl in self.topology.live_switches:
      for c in switch_impl.connections:
        if c.io_worker.has_pending_sends():
          yield c

  # ============================================ #
  #     Event Injection methods                  #
  # ============================================ #

  def send_policy_request(self, controller, api_call):
    pass

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
