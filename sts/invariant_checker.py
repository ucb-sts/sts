import json
import urllib2

from pox.openflow.libopenflow_01 import *
from entities import *
import sts.headerspace.topology_loader.topology_loader as hsa_topo
import sts.headerspace.headerspace.applications as hsa
import sts.headerspace.config_parser.openflow_parser as get_uniq_port_id
import pickle
import logging
import collections
from sts.util.console import msg

log = logging.getLogger("invariant_checker")

class InvariantChecker(object):
  # --------------------------------------------------------------#
  #                    Invariant checks                           #
  # --------------------------------------------------------------#
  @staticmethod
  def check_loops(simulation):
    # Warning! depends on python Hassell -- may be really slow!
    NTF = hsa_topo.generate_NTF(simulation.topology.live_switches)
    TTF = hsa_topo.generate_TTF(simulation.topology.live_links)
    loops = hsa.detect_loop(NTF, TTF, simulation.topology.access_links)
    return loops

  @staticmethod
  def check_connectivity(simulation):
    ''' Return any pairs that couldn't reach each other '''
    # Effectively, run compute physical omega, ignore concrete values of headers, and
    # check that all pairs can reach eachother
    physical_omega = InvariantChecker.compute_physical_omega(simulation.topology.live_switches,
                                                             simulation.topology.live_links,
                                                             simulation.topology.access_links)
    connected_pairs = set()
    # Omegas are { original port -> [(final hs1, final port1), (final hs2, final port2)...] }
    for start_port, final_location_list in physical_omega.iteritems():
      for _, final_port in final_location_list:
        connected_pairs.add((start_port, final_port))

    # TODO(cs): translate HSA port numbers to ofp_phy_ports in the
    # headerspace/ module instead of computing uniq_port_id here
    all_pairs = [ (get_uniq_port_id(l1.switch, l1.switch_port),get_uniq_port_id(l2.switch, l2.switch_port))
                  for l1 in simulation.topology.acccess_link
                  for l2 in simulation.topology.acccess_link if l1 != l2 ]
    all_pairs = set(all_pairs)
    remaining_pairs = all_pairs - connected_pairs
    # TODO(cs): don't print results here
    if len(remaining_pairs) > 0:
      msg.fail("Not all pairs are connected!")
    else:
      msg.success("Fully connected!")
    return remaining_pairs

  @staticmethod
  def check_correspondence(simulation):
    ''' Return if there were any policy-violations '''
    log.debug("Snapshotting controller...")
    diffs = []
    for controller in simulation.controller_manager.controllers:
      controller_snapshot = controller.snapshot_service.fetchSnapshot()
      log.debug("Computing physical omega...")
      physical_omega = InvariantChecker.compute_physical_omega(simulation.topology.live_switches,
                                                               simulation.topology.live_links,
                                                               simulation.topology.access_links)
      log.debug("Computing controller omega...")
      controller_omega = InvariantChecker.compute_controller_omega(controller_snapshot,
                                                                   simulation.topology.live_switches,
                                                                   simulation.topology.live_links,
                                                                   simulation.topology.access_links)
      diff = InvariantChecker.infer_policy_violations(physical_omega, controller_omega)
      diffs.append(diff)
    return diffs

  # --------------------------------------------------------------#
  #                    HSA utilities                              #
  # --------------------------------------------------------------#
  @staticmethod
  def compute_physical_omega(live_switches, live_links, edge_links):
    (name_tf_pairs, TTF) = InvariantChecker._get_transfer_functions(live_switches, live_links)
    physical_omega = hsa.compute_omega(name_tf_pairs, TTF, edge_links)
    return physical_omega

  @staticmethod
  def compute_controller_omega(controller_snapshot, live_switches, live_links, edge_links):
    name_tf_pairs = hsa_topo.tf_pairs_from_snapshot(controller_snapshot, live_switches)
    # Frenetic doesn't store any link or host information.
    # No virtualization though, so we can assume the same TTF. TODO(cs): for now...
    TTF = hsa_topo.generate_TTF(live_links)
    return hsa.compute_omega(name_tf_pairs, TTF, edge_links)

  @staticmethod
  def _get_transfer_functions(live_switches, live_links):
    name_tf_pairs = hsa_topo.generate_tf_pairs(live_switches)
    TTF = hsa_topo.generate_TTF(live_links)
    return (name_tf_pairs, TTF)

  @staticmethod
  def infer_policy_violations(physical_omega, controller_omega):
    ''' Return if there were any missing entries '''
    print "# entries in physical omega: %d" % len(physical_omega)
    print "# entries in controller omega: %d" % len(controller_omega)

    def get_simple_dict(omega):
      # TODO(cs): ignoring original hs means that we don't account for
      # field modifications, e.g. TTL decreases
      #
      # Omegas are { original port -> [(final hs1, final port1), (final hs2, final port2)...] }
      # Want to turn them into port -> [(final hs1, final port1), (final hs2, final port2)...]
      simple_dict = collections.defaultdict(lambda: set())
      for key, tuples in omega.iteritems():
        port = key
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
            print ": %s: %s" % (print_string,  str(final_location))
      if not any_missing_entries:
        print "No %s!" % print_string
      return any_missing_entries

    # (physical - controller) = missing routing policies
    missing_routing_entries = print_missing_entries("missing routing entries", physical_omega, controller_omega)
    # (controller - physical) = missing ACL policies.
    missing_acl_entries = print_missing_entries("missing acl entries", controller_omega, physical_omega)
    return missing_routing_entries or missing_acl_entries
