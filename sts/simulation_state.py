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

from sts.util.console import msg
from sts.io_master import IOMaster
from sts.dataplane_traces.trace import Trace
from entities import Link, Host, Controller, DeferredOFConnection
from sts.topology import *
from sts.controller_manager import ControllerManager
from sts.util.deferred_io import DeferredIOWorker
from sts.control_flow import Replayer
from sts.god_scheduler import GodScheduler
from sts.syncproto.base import SyncTime
from sts.syncproto.sts_syncer import STSSyncConnectionManager

import logging
import pickle

log = logging.getLogger("simulation")

class Simulation (object):
  """
  Maintains the current state of:
    - The controllers: a list of ControllerConfig objects
    - The topology
    - Patch panel (dataplane forwarding)
    - (Optionally) the dataplane trace
  """
  def __init__(self, controller_configs, topology_class,
               topology_params, patch_panel_class, dataplane_trace_path=None,
               controller_sync_callback=None):
    self.controller_configs = controller_configs
    self.controller_manager = None
    self.topology = None
    # keep around topology_class and topology_params so we can construct
    # clean topology objects for (multiple invocations of) bootstrapping later
    self._topology_class = topology_class
    self._topology_params = topology_params
    self._patch_panel_class = patch_panel_class
    self.dataplane_trace = None
    self._dataplane_trace_path = dataplane_trace_path
    self._io_master = None
    self.god_scheduler = None
    # TODO(cs): controller_sync_callback is currently stateful -> need to fix
    # for correct bootstrap()'ing
    self.controller_sync_callback = controller_sync_callback

  # TODO(cs): the next three next methods should go in a separate
  #           ControllerContainer class
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
    if self.controller_manager is not None:
      self.controller_manager.kill_all()

    # Garbage collect sockets
    if self.topology is not None:
      for switch in self.topology.switches:
        for connection in switch.connections:
          connection.close()

    # Just to make sure there isn't any state lying around, throw out the old
    # RecocoIOLoop
    if self._io_master is not None:
      self._io_master.close_all()
    msg.unset_io_master()

  def bootstrap(self):
    '''Set up the state of the system to its initial starting point:
       - boots controllers
       - connects switches to controllers

       May be invoked multiple times!
    '''
    # Clean up state from any previous runs
    self.clean_up()

    # boot the IOLoop (needed for the controllers)
    self._io_master = IOMaster()

    # monkey patch time.sleep for all our friends
    self._io_master.monkey_time_sleep()
    # tell sts.console to use our io_master
    msg.set_io_master(self._io_master)

    self.sync_connection_manager = STSSyncConnectionManager(self._io_master,
                                                            self.controller_sync_callback)

    # Boot the controllers
    controllers = []
    for c in self.controller_configs:
      controller = Controller(c, self.sync_connection_manager)
      controller.start()
      log.info("Launched controller c%s: %s [PID %d]" %
               (str(c.uuid), " ".join(c.expanded_cmdline), controller.pid))
      controllers.append(controller)

    self.controller_manager = ControllerManager(controllers)

    # Instantiate network
    self._instantiate_topology()
    self.patch_panel = self._patch_panel_class(self.topology.switches,
                                               self.topology.hosts,
                                               self.topology.get_connected_port)
    self.god_scheduler = GodScheduler()

    if self._dataplane_trace_path is not None:
      self.dataplane_trace = Trace(self._dataplane_trace_path, self.topology)

    # Connect switches to controllers
    # TODO(cs): move this into a ConnectionFactory class
    def create_connection(controller_info, switch):
        socket = connect_socket_with_backoff(controller_info.address,
                                             controller_info.port)
        # Set non-blocking
        socket.setblocking(0)
        io_worker = DeferredIOWorker(self._io_master.create_worker_for_socket(socket))
        return DeferredOFConnection(io_worker, switch.dpid, self.god_scheduler)

    self.topology.connect_to_controllers(self.controller_configs,
                                         create_connection=create_connection)
