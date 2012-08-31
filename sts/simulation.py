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

  # TODO(sw): put me in the Controller class
  def send_policy_request(self, controller, api_call):
    pass
