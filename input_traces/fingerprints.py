
from pox.openflow.libopenflow import *

#  ofp_type -> fields to include in fingerprint

# TODO(cs): I'm erring on the side of sparseness rather than completeness. We
# may need to include more fields here to get an unambiguous fingerprint

control_plane_pkts = {
  ofp_features_reply : ["datapath_id"],
  ofp_switch_config : ["flags"],
  ofp_flow_mod : ["match", "idle_timeout", "hard_timeout", "priority",
                  "out_port", "flags", "actions"],
  ofp_port_mod : ["port_no", "hw_addr", "config", "mask", "advertise"],
  ofp_queue_get_config_request : []
  ofp_queue_get_config_reply : []
  ofp_stats_request : ["type", "flags"],
  ofp_stats_reply : ["type", "flags"],
  ofp_desc_stats : [],
  ofp_flow_stats_request : [],
  ofp_flow_stats : [],
  ofp_aggregate_stats_request : [],
  ofp_aggregate_stats : [],
  ofp_port_stats_request : [],
  ofp_port_stats : [],
  ofp_queue_stats_request : [],
  ofp_queue_stats : [],
  ofp_packet_out : ["data", "in_port", "actions"],
  ofp_barrier_reply : [],
  ofp_barrier_request : [],
  ofp_packet_in : ["in_port", "data"],
  ofp_flow_removed : ["match", "reason", "priority"],
  ofp_port_status : ["reason", "desc"],
  ofp_error : ["type", "code"],
  ofp_hello : [],
  ofp_echo_request : [],
  ofp_echo_reply : [],
  ofp_vendor_header : [],
  #ofp_vendor
  ofp_features_request : [],
  ofp_get_config_request : [],
  ofp_get_config_reply : [],
  ofp_set_config : [],
}


def extract_fingerprint_from_cp_pkt(cp_pkt):
  # TODO figure out how to encode matches (actions are unordered; data needs a nested
  # fingerprint; desc is a ofp_phy_port object)
  # look at the openflow over json code
  pass

# For now, just take (src MAC, dst MAC, src IP, dst IP) as the fingerprint for
# dataplane packets
# TODO(cs): might finer granularity later
def extract_fingerprint_from_dp_pkt(dp_pkt):
  pass
