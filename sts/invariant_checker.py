import json
import urllib2

from pox.openflow.libopenflow_01 import *
from debugger_entities import *
import headerspace.topology_loader.pox_topology_loader as hsa_topo
import headerspace.headerspace.applications as hsa
import nom_snapshot_json as nom_snapshot
import pickle
import logging
import collections

log = logging.getLogger("invariant_checker")

class InvariantChecker(object):
  def fetch_controller_snapshot(self, simulation):
    # TODO(cs): grab url from simulation.controller_info_list rather than
    # hard-code
    req = urllib2.Request('http://localhost:8080/wm/core/proact')
    response = urllib2.urlopen(req)
    json_data = response.read()
    l = json.loads(json_data)
    res = []
    for m in l:
      res.append(nom_snapshot.Snapshot.from_json_map(m))
    return res

  # --------------------------------------------------------------#
  #                    Invariant checks                           #
  # --------------------------------------------------------------#
  def check_loops(self, simulation):
    pass

  def check_blackholes(self, simulation):
    pass

  def check_connectivity(self, simulation):
    pass

  def check_routing_consistency(self, simulation):
    pass

  def check_correspondence(self, simulation):
    ''' Return if there were any policy-violations '''
    log.debug("Snapshotting controller...")
    controller_snapshot = self.fetch_controller_snapshot(simulation)
    log.debug("Computing physical omega...")
    physical_omega = self.compute_physical_omega(simulation.live_switches,
                                                 simulation.live_links,
                                                 simulation.edge_links)
    log.debug("Computing controller omega...")
    controller_omega = self.compute_controller_omega(controller_snapshot,
                                                     simulation.live_switches,
                                                     simulation.live_links,
                                                     simulation.edge_links)
    return self.infer_policy_violations(physical_omega, controller_omega)

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
    # No virtualization though, so we can assume the same TTF. TODO(cs): for now...
    TTF = hsa_topo.generate_TTF(live_links)
    return hsa.compute_omega(NTF, TTF, edge_links)

  def compute_single_omega(self, start_link, live_switches, live_links, edge_links):
    (NTF, TTF) = self._get_transfer_functions(live_switches, live_links)
    return hsa.compute_single_omega(NTF, TTF, start_link, edge_links)

  def _get_transfer_functions(self, live_switches, live_links):
    NTF = hsa_topo.generate_NTF(live_switches)
    TTF = hsa_topo.generate_TTF(live_links)
    return (NTF, TTF)

  def infer_policy_violations(self, physical_omega, controller_omega):
    ''' Return if there were any missing entries '''
    print "# entries in physical omega: %d" % len(physical_omega)
    print "# entries in controller omega: %d" % len(controller_omega)

    def get_simple_dict(omega):
      # TODO(cs): ignoring original hs means that we don't account for
      # field modifications, e.g. TTL decreases
      #
      # Omegas are { (original hs, original port) -> [(final hs1, final port1), (final hs2, final port2)...] }
      # Want to turn them into port -> [(final hs1, final port1), (final hs2, final port2)...]
      simple_dict = collections.defaultdict(lambda: set())
      for key, tuples in omega.iteritems():
        (hs, port) = key
        for tup in tuples:
          printable_tup = (str(tup[0]), tup[1])
          simple_dict[port].add(printable_tup)
      return simple_dict

    physical_omega = get_simple_dict(physical_omega)
    controller_omega = get_simple_dict(controller_omega)

    def print_missing_entries(print_string, omega1, omega2):
      any_missing_entries = False
      for origin_port, final_locations in omega1.iteritems():
        for final_location in final_locations:
          if origin_port not in omega2 or final_location not in omega2[origin_port]:
            any_missing_entries = True
            print ": %s: %s" % (print_string, str(final_location))
      if not any_missing_entries:
        print "No %s!" % print_string
      return any_missing_entries

    # (physical - controller) = missing routing policies
    missing_routing_entries = print_missing_entries("missing routing entries", physical_omega, controller_omega)
    # (controller - physical) = missing ACL policies.
    missing_acl_entries = print_missing_entries("missing acl entries", controller_omega, physical_omega)
    return missing_routing_entries or missing_acl_entries
