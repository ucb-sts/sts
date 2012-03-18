
from pox.openflow.libopenflow_01 import *
from debugger_entities import *
import headerspace.topology_loader.pox_topology_loader as hsa_topo
import headerspace.headerspace.applications as hsa

import logging
log = logging.getLogger("invariant_checker")

class InvariantChecker():
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
  
  def check_correspondence(self):
    pass
  
  def compute_omega(self, live_switches, live_links, edge_links):
    (NTF, TTF) = self._get_transfer_functions(live_switches, live_links)
    return hsa.compute_omega(NTF, TTF, edge_links)
  
  def _get_transfer_functions(self, live_switches, live_links):
    NTF = hsa_topo.generate_NTF(live_switches)
    TTF = hsa_topo.generate_TTF(live_links)
    return (NTF, TTF)
