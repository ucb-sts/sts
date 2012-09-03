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

from pox.lib.ioworker.io_worker import RecocoIOLoop
from sts.deferred_io import DeferredIOWorker
from dataplane_traces.trace import Trace
from entities import Link, Host, Controller
from sts.topology import *

import logging
import pickle

log = logging.getLogger("simulation")

class Simulation (object):
  """
  Maintains the current state of:
    - scheduler: a Recoco scheduler
    - The controllers: a list of ControllerConfig objects
    - The topology
    - Patch panel (dataplane forwarding)
    - (Optionally) the dataplane trace
  """
  def __init__(self, scheduler, controller_configs, topology_class,
               topology_params, patch_panel_class, dataplane_trace_path=None):
    self._scheduler = scheduler
    self._io_loop = None
    self.controller_configs = controller_configs
    # uuid -> instantiated entities.Controller objects
    self.uuid2controller = {}
    self.topology = None
    # keep around topology_class and topology_params so we can construct
    # clean topology objects for (multiple invocations of) bootstrapping later
    self._topology_class = topology_class
    self._topology_params = topology_params
    self._patch_panel_class = patch_panel_class
    self.dataplane_trace = None
    self._dataplane_trace_path = dataplane_trace_path

  # TODO(cs): the next three next methods should go in a separate
  #           ControllerContainer class
  @property
  def controllers(self):
    return self.uuid2controller.values()

  @property
  def live_controllers(self):
    alive = [controller for controller in self.controllers if controller.alive]
    return set(alive)

  @property
  def down_controllers(self):
    down = [controller for controller in self.controllers if not controller.alive]
    return set(down)

  def _instantiate_topology(self):
    '''construct a clean topology object from topology_class and
    topology_params'''
    # If you want to shoot yourself in the foot, feel free :)
    self.topology = eval("%s(%s)" %
                         (self._topology_class.__name__, self._topology_params))

  def clean_up(self):
    '''Ensure that state from previous runs (old controller processes,
    sockets, IOLoop object) are cleaned before the next time we
    bootstrap'''
    # kill controllers
    for c in self.controllers:
      c.kill()
    self.uuid2controller = {}

    # Garbage collect sockets
    if self.topology is not None:
      for switch in self.topology.switches:
        for connection in switch.connections:
          connection.close()

    # Just to make sure there isn't any state lying around, throw out the old
    # RecocoIOLoop
    if self._io_loop is not None:
      self._io_loop.stop()

  def bootstrap(self):
    '''Set up the state of the system to its initial starting point:
       - boots controllers
       - connects switches to controllers

       May be invoked multiple times!
    '''
    # Clean up state from any previous runs
    self.clean_up()

    # Boot the controllers
    controllers = []
    for c in self.controller_configs:
      controller = Controller(c)
      log.info("Launched controller c%s: %s [PID %d]" %
               (str(c.uuid), " ".join(c.cmdline), controller.pid))
      controllers.append(controller)

    self.uuid2controller = {
      controller.uuid : controller
      for controller in controllers
    }

    # Instantiate network
    self._instantiate_topology()
    self.patch_panel = self._patch_panel_class(self.topology.switches,
                                               self.topology.hosts,
                                               self.topology.get_connected_port)
    if self._dataplane_trace_path is not None:
      self.dataplane_trace = Trace(self._dataplane_trace_path, self.topology)

    # Connect switches to controllers
    self._io_loop = RecocoIOLoop()
    self._scheduler.schedule(self._io_loop)
    create_worker = lambda(socket): DeferredIOWorker(self._io_loop.create_worker_for_socket(socket),
                                                     self._scheduler.callLater)
    self.topology.connect_to_controllers(self.controller_configs, create_worker)
