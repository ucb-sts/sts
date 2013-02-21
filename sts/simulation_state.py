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
from sts.util.socket_mux.base import MultiplexedSelect
from sts.util.socket_mux.sts_socket_multiplexer import STSSocketDemultiplexer, STSMockSocket
from pox.lib.util import connect_socket_with_backoff

import logging
import time
import select
import socket

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
               multiplex_sockets=False):
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
         monkey_patch_select => whether to use STS's custom deterministic
                                select. Requires that the controller is
                                monkey-patched too
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
    self.multiplex_sockets = multiplex_sockets

  def bootstrap(self, sync_callback):
    '''Return a simulation object encapsulating the state of
       the system in its initial starting point:
       - boots controllers
       - connects switches to controllers

       May be invoked multiple times!
    '''
    def remove_monkey_patch():
      if hasattr(select, "_old_select"):
        # Revert the previous monkeypatch to allow the new true_sockets to
        # connect
        select.select = select._old_select
        socket.socket = socket._old_socket

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
                 (str(c.cid), " ".join(c.expanded_cmdline), controller.pid))
        controllers.append(controller)
      return ControllerManager(controllers)

    def instantiate_topology(create_io_worker):
      '''construct a clean topology object from topology_class and
      topology_params'''
      # If you want to shoot yourself in the foot, feel free :)
      comma = "" if self._topology_params == "" else ","
      topology = eval("%s(%s%screate_io_worker=create_io_worker)" %
                      (self._topology_class.__name__,
                       self._topology_params, comma))
      return topology

    # Instantiate the pieces needed for Simulation's constructor
    remove_monkey_patch()
    io_master = initialize_io_loop()
    sync_connection_manager = STSSyncConnectionManager(io_master,
                                                       sync_callback)
    controller_manager = boot_controllers(sync_connection_manager)
    topology = instantiate_topology(io_master.create_worker_for_socket)
    patch_panel = self._patch_panel_class(topology.switches, topology.hosts,
                                          topology.get_connected_port)
    god_scheduler = GodScheduler()
    dataplane_trace = None
    if self._dataplane_trace_path is not None:
      dataplane_trace = Trace(self._dataplane_trace_path, topology)

    simulation = Simulation(topology, controller_manager, dataplane_trace,
                            god_scheduler, io_master, patch_panel,
                            sync_callback, self.multiplex_sockets)
    self.current_simulation = simulation
    return simulation

  def set_dataplane_trace_path(self, path):
    if self._dataplane_trace_path is None:
      self._dataplane_trace_path = path

  def __str__(self):
    return ('''SimulationConfig(controller_configs=%s,\n'''
            '''                 topology_class=%s,\n'''
            '''                 topology_params="%s",\n'''
            '''                 patch_panel_class=%s,\n'''
            '''                 dataplane_trace="%s",\n'''
            '''                 multiplex_sockets=%s)''' %
            (str(self.controller_configs),self._topology_class.__name__,
             self._topology_params, self._patch_panel_class.__name__,
             self._dataplane_trace_path,
             str(self.multiplex_sockets)))

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
               god_scheduler, io_master, patch_panel,
               controller_sync_callback, multiplex_sockets):
    self.topology = topology
    self.controller_manager = controller_manager
    self.dataplane_trace = dataplane_trace
    self.god_scheduler = god_scheduler
    self._io_master = io_master
    self.patch_panel = patch_panel
    self.controller_sync_callback = controller_sync_callback
    self.multiplex_sockets = multiplex_sockets
    self.exit_code = 0

  def set_exit_code(self, code):
    self.exit_code = code

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
    msg.unset_io_master()
    if self._io_master is not None:
      self._io_master.close_all()

  @property
  def io_master(self):
    return self._io_master

  def connect_to_controllers(self):
    ''' Connect all switches to all controllers '''
    def monkeypatch_select():
      log.debug("Monkeypatching STS select")
      mux_select = None
      demuxers = []
      if self.multiplex_sockets:
        if hasattr(select, "_old_select"):
          # Revert the previous monkeypatch to allow the new true_sockets to
          # connect
          select.select = select._old_select
          socket.socket = socket._old_socket

        # Monkey patch select to use our deterministic version
        mux_select = MultiplexedSelect()
        for c in self.controller_manager.controller_configs:
          # Connect the true sockets
          true_socket = connect_socket_with_backoff(address=c.address, port=c.port)
          io_worker = mux_select.create_worker_for_socket(true_socket)
          mux_select.set_true_io_worker(io_worker)
          demux = STSSocketDemultiplexer(io_worker, c.server_info)
          demuxers.append(demux)

        # Monkey patch select.select
        select._old_select = select.select
        select.select = mux_select.select
        # Monkey patch socket.socket
        socket._old_socket = socket.socket
        def socket_patch(protocol, sock_type):
          if sock_type == socket.SOCK_STREAM:
            return STSMockSocket(protocol, sock_type)
          else:
            socket._old_socket(protocol, sock_type)
        socket.socket = socket_patch

      return (mux_select, demuxers)

    def create_connection(controller_info, switch):
      ''' Connect switches to controllers. May raise a TimeoutError '''
      # TODO(cs): move this into a ConnectionFactory class
      socket = connect_socket_with_backoff(controller_info.address,
                                           controller_info.port,
                                           max_backoff_seconds=8)
      # Set non-blocking
      socket.setblocking(0)
      io_worker = DeferredIOWorker(self.io_master.create_worker_for_socket(socket))
      connection = DeferredOFConnection(io_worker, controller_info.cid, switch.dpid, self.god_scheduler)
      return connection

    (self.mux_select, self.demuxers) = monkeypatch_select()

    # TODO(cs): this should block until all switches have finished
    # initializing with the controller
    self.topology.connect_to_controllers(self.controller_manager.controller_configs,
                                         create_connection=create_connection)
