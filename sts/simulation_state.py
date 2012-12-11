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

from sts.util.io_master import IOMaster
from sts.dataplane_traces.trace import Trace
from entities import Link, Controller, DeferredOFConnection
from sts.topology import *
from sts.controller_manager import ControllerManager
from sts.util.deferred_io import DeferredIOWorker
from sts.god_scheduler import GodScheduler
from sts.syncproto.sts_syncer import STSSyncConnectionManager
import sts.snapshot as snapshot
from pox.lib.util import connect_socket_with_backoff

import logging
import time

log = logging.getLogger("simulation")

class SimulationConfig(object):
  """
  Maintains the configuration for:
    - The controllers: a list of ControllerConfig objects
    - The topology
    - Patch panel (dataplane forwarding)
    - (Optionally) the dataplane trace
    - Initialization parameters (switch_init_sleep_seconds)
  """
  def __init__(self, controller_configs=None,
               topology_class=FatTree,
               topology_params="",
               patch_panel_class=BufferedPatchPanel,
               dataplane_trace=None,
               snapshot_service=None,
               switch_init_sleep_seconds=False):
    ''' Constructor parameters:
         topology_class    => a sts.topology.Topology class (not object!)
                              defining the switches and links
         topology_params   => Comma-delimited list of arguments to pass into the FatTree
                              constructor, specified just as you would type them within
                              the parens.
         patch_panel_class => a sts.topology.PatchPanel class (not object!)
         dataplane_trace   => a path to a dataplane trace file
                              (e.g. dataplane_traces/ping_pong_same_subnet.trace)
         switch_init_sleep_seconds => number of seconds to wait for switches to
                                      connect to controllers before starting the
                                      simulation. Defaults to False (no wait).
    '''
    if controller_configs is None:
      controller_configs = []
    self.controller_configs = controller_configs
    # keep around topology_class and topology_params so we can construct
    # clean topology objects for (multiple invocations of) bootstrapping later
    self._topology_class = topology_class
    self._topology_params = topology_params
    self._patch_panel_class = patch_panel_class
    self._dataplane_trace_path = dataplane_trace
    # TODO(cs): is the snapshot service stateful?
    if snapshot_service is None:
      # For snapshotting the controller's view of the network configuration
      snapshot_service = snapshot.get_snapshotservice(controller_configs)

    self.snapshot_service = snapshot_service
    self.current_simulation = None
    self.switch_init_sleep_seconds = switch_init_sleep_seconds

  def bootstrap(self, sync_callback):
    '''Return a simulation object encapsulating the state of
       the system in its initial starting point:
       - boots controllers
       - connects switches to controllers

       May be invoked multiple times!

       Optional parameter:
       - switch_init_sleep_seconds: an integer, sleep time in seconds, to wait
             for switches to initialize their TCP connections with the
             controller(s). Defaults to False
    '''
    def initialize_io_loop():
      ''' boot the IOLoop (needed for the controllers) '''
      _io_master = IOMaster()
      # monkey patch time.sleep for all our friends
      _io_master.monkey_time_sleep()
      # tell sts.console to use our io_master
      msg.set_io_master(_io_master)
      return _io_master

    def boot_controllers(sync_connection_manager):
      # Boot the controllers
      controllers = []
      for c in self.controller_configs:
        controller = Controller(c, sync_connection_manager,
                                self.snapshot_service)
        controller.start()
        log.info("Launched controller c%s: %s [PID %d]" %
                 (str(c.uuid), " ".join(c.expanded_cmdline), controller.pid))
        controllers.append(controller)
      return ControllerManager(controllers)

    def instantiate_topology():
      '''construct a clean topology object from topology_class and
      topology_params'''
      # If you want to shoot yourself in the foot, feel free :)
      topology = eval("%s(%s)" %
                      (self._topology_class.__name__,
                       self._topology_params))
      return topology

    # Instantiate the pieces needed for Simulation's constructor
    io_master = initialize_io_loop()
    sync_connection_manager = STSSyncConnectionManager(io_master,
                                                       sync_callback)
    controller_manager = boot_controllers(sync_connection_manager)
    topology = instantiate_topology()
    patch_panel = self._patch_panel_class(topology.switches, topology.hosts,
                                          topology.get_connected_port)
    god_scheduler = GodScheduler()
    dataplane_trace = None
    if self._dataplane_trace_path is not None:
      dataplane_trace = Trace(self._dataplane_trace_path, topology)

    simulation = Simulation(topology, controller_manager, dataplane_trace,
                            god_scheduler, io_master, patch_panel,
                            sync_callback)
    self.current_simulation = simulation

    # Connect to controllers
    # TODO(cs): somewhat hacky that we do this after instantiating Simulation
    def create_connection(controller_info, switch):
      ''' Connect switches to controllers. May raise a TimeoutError '''
      # TODO(cs): move this into a ConnectionFactory class
      socket = connect_socket_with_backoff(controller_info.address,
                                           controller_info.port,
                                           max_backoff_seconds=16)
      # Set non-blocking
      socket.setblocking(0)
      io_worker = DeferredIOWorker(io_master.create_worker_for_socket(socket))
      return DeferredOFConnection(io_worker, switch.dpid, god_scheduler)

    if self.switch_init_sleep_seconds:
      simulation.set_pass_through()

    # TODO(cs): this should block until all switches have finished
    # initializing with the controller
    topology.connect_to_controllers(self.controller_configs,
                                    create_connection=create_connection)

    if self.switch_init_sleep_seconds:
      log.debug("Waiting %f seconds for switch initialization" %
                self.switch_init_sleep_seconds)
      time.sleep(self.switch_init_sleep_seconds)

    # Now unset pass-through mode
    if self.switch_init_sleep_seconds:
      simulation.unset_pass_through()

    return simulation

  def __str__(self):
    return ('''SimulationConfig(controller_configs=%s,'''
            '''                 topology_class=%s,'''
            '''                 topology_params="%s",'''
            '''                 patch_panel_class=%s, '''
            '''                 dataplane_trace="%s", '''
            '''                 switch_init_sleep_seconds=%s)''' %
            (str(self.controller_configs),self._topology_class.__name__,
             self._topology_params, self._patch_panel_class.__name__,
             self._dataplane_trace_path, str(self.switch_init_sleep_seconds)))

class Simulation(object):
  '''
  Encapsulates the running state of a single simulation:
    - Topology (network state)
    - Controller processes
    - GodScheduler (OpenFlow messages)
    - PatchPanel (Dataplane messages)
    - RecordingSyncCallback (controller state changes)
    - Dataplane Trace (pending dataplane messages)
  '''
  def __init__(self, topology, controller_manager, dataplane_trace,
               god_scheduler, io_master, patch_panel, controller_sync_callback):
    self.topology = topology
    self.controller_manager = controller_manager
    self.dataplane_trace = dataplane_trace
    self.god_scheduler = god_scheduler
    self._io_master = io_master
    self.patch_panel = patch_panel
    self.controller_sync_callback = controller_sync_callback

  def set_pass_through(self):
    ''' Set to pass-through during bootstrap, so that switch initialization
    messages don't get buffered '''
    self.god_scheduler.set_pass_through()
    if hasattr(self.controller_sync_callback, "set_pass_through"):
      self.controller_sync_callback.set_pass_through()

  def unset_pass_through(self):
    ''' unset pass-through mode '''
    observed_events = []
    observed_events += self.god_scheduler.unset_pass_through()
    if hasattr(self.controller_sync_callback, "unset_pass_through"):
      observed_events += self.controller_sync_callback.unset_pass_through()
    return observed_events

  def clean_up(self):
    '''Ensure that state from previous runs (old controller processes,
    sockets, IOLoop object) are cleaned before the next time we
    bootstrap'''
    # kill controllers
    if self.controller_manager is not None:
      self.controller_manager.kill_all()

    # Garbage collect sockets
    if self.topology is not None:
      for switch in self.topology.switches:
        for connection in switch.connections:
          connection.close()

    # Just to make sure there isn't any state lying around, throw out
    # the old RecocoIOLoop
    if self._io_master is not None:
      self._io_master.close_all()
    msg.unset_io_master()

  @property
  def io_master(self):
    return self._io_master
