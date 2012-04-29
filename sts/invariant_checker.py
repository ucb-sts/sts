
from pox.openflow.libopenflow_01 import *
from debugger_entities import *
import headerspace.topology_loader.pox_topology_loader as hsa_topo
import headerspace.headerspace.applications as hsa
import nom_snapshot_protobuf.nom_snapshot_pb2 as nom_snapshot

import pickle
import logging
log = logging.getLogger("invariant_checker")

class InvariantChecker(object):
  def __init__(self, control_socket):
    self.control_socket = control_socket
    
  def fetch_controller_snapshot(self):
    # TODO: we really need to be able to pause the controller, since correspondence
    # checking might take awhile...
    # TODO: should just use an RPC framework, e.g. Pyro, XML-RPC.
    log.debug("Sending Request")
    self.control_socket.send("FETCH", socket.MSG_WAITALL)
    log.debug("Receiving Results")
    bytes = []
    while True:
      data = self.control_socket.recv(1024)
      log.debug("%d byte packet received" % len(data))
      if not data: break
      bytes.append(data)
      # HACK. Doesn't handle case where data is exactly 1024 bytes
      # TODO: figure out the right way to avoid blocking. (Better: use RPC)
      if len(data) != 1024: break
        
    snapshot = nom_snapshot.Snapshot()
    snapshot.ParseFromString(''.join(bytes))
    return snapshot
  
  # --------------------------------------------------------------#
  #                    Invariant checks                           #
  # --------------------------------------------------------------#
  def check_loops(self):
    pass

  def check_blackholes(self):
    pass

  def check_connectivity(self):
    pass

  def check_routing_consistency(self):
    pass
  
  def check_correspondence(self, live_switches, live_links, edge_links):
    log.debug("Snapshotting controller...")
    controller_snapshot = self.fetch_controller_snapshot()
    log.debug("Computing physical omega...")
    physical_omega = self.compute_physical_omega(live_switches, live_links, edge_links)
    log.debug("Computing controller omega...")
    controller_omega = self.compute_controller_omega(controller_snapshot, live_switches, live_links, edge_links)
    # TODO: compare omegas
    
  # --------------------------------------------------------------#
  #                    HSA utilities                              #
  # --------------------------------------------------------------#
  def compute_physical_omega(self, live_switches, live_links, edge_links):
    (NTF, TTF) = self._get_transfer_functions(live_switches, live_links)
    physical_omega = hsa.compute_omega(NTF, TTF, edge_links)
    return physical_omega
  
  def compute_controller_omega(self, controller_snapshot, live_switches, live_links, edge_links):
    NTF = hsa_topo.NTF_from_snapshot(controller_snapshot, live_switches)
    # Frenetic doesn't store any link or host information.
    # No virtualization though, so we can assume the same TTF. TODO: for now...
    TTF = hsa_topo.generate_TTF(live_links)
    return hsa.compute_omega(NTF, TTF, edge_links)
  
  def compute_single_omega(self, start_link, live_switches, live_links, edge_links):
    (NTF, TTF) = self._get_transfer_functions(live_switches, live_links)
    return hsa.compute_single_omega(NTF, TTF, start_link, edge_links)
  
  def _get_transfer_functions(self, live_switches, live_links):
    NTF = hsa_topo.generate_NTF(live_switches)
    TTF = hsa_topo.generate_TTF(live_links)
    return (NTF, TTF)
