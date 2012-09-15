
import abc
from pox.openflow.libopenflow_01 import *
from pox.lib.packet.ethernet import *
import headerspace.config_parser.openflow_parser as hsa

class Fingerprint(object):
  __metaclass__ = abc.ABCMeta

  # This should really be a protected constructor
  def __init__(self, field2value):
    self._field2value = field2value

  def to_dict(self):
    return self._field2value

  @abc.abstractmethod
  def __hash__(self):
    pass

  @abc.abstractmethod
  def __eq__(self, other):
    pass

  def __str__(self):
    return str(self._field2value)

def process_data(msg):
  if msg.data == b'':
    return []
  else:
    dp_packet = ethernet(msg.data)
    return DPFingerprint.from_pkt(dp_packet).to_dict()

class OFFingerprint(Fingerprint):
  ''' Fingerprints for openflow messages '''
  #  ofp_type -> fields to include in fingerprint
  # TODO(cs): I'm erring on the side of sparseness rather than completeness. We
  # may need to include more fields here to get an unambiguous fingerprint
  pkt_type_to_fields = {
    ofp_features_reply : ["datapath_id"],
    ofp_switch_config : ["flags"],
    ofp_flow_mod : ["match", "idle_timeout", "hard_timeout", "priority",
                    "out_port", "flags", "actions"],
    ofp_port_mod : ["port_no", "hw_addr", "config", "mask", "advertise"],
    ofp_queue_get_config_request : [],
    ofp_queue_get_config_reply : [],
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
    #ofp_vendor (body of ofp_vendor_header)
    ofp_features_request : [],
    ofp_get_config_request : [],
    ofp_get_config_reply : [],
    ofp_set_config : []
  }
  special_fields = {
    # data needs a nested fingerprint
    'data' : process_data,
    # desc is a ofp_phy_port object
    'desc' : lambda pkt: (pkt.desc.port_no, pkt.desc.hw_addr.toStr()),
    # actions is an ordered list
    # for now, store it as a tuple of just the names of the action types
    'actions' : lambda pkt: tuple(map(str, map(type, pkt.actions))),
    # match has a bunch of crazy fields
    # Trick: convert it to an hsa match, and extract the human readable string
    # for the hsa match
    'match' : lambda pkt: hsa.hs_format["display"](hsa.ofp_match_to_hsa_match(pkt.match))
  }

  @staticmethod
  def from_pkt(pkt):
    pkt_type = type(pkt)
    if pkt_type not in OFFingerprint.pkt_type_to_fields:
      raise ValueError("Unknown pkt_type %s" % pkt_type)
    field2value = {}
    field2value["class"] = pkt_type.__name__
    fields = OFFingerprint.pkt_type_to_fields[pkt_type]
    for field in fields:
      if field in OFFingerprint.special_fields:
        value = OFFingerprint.special_fields[field](pkt)
      else:
        value = getattr(pkt, field)
      field2value[field] = value
    return OFFingerprint(field2value)

  def __hash__(self):
    hash = 0
    class_name = self.field2value["class"]
    hash += class_name.__hash__()
    # Note that the order is important
    for field in self.pkt_type_to_fields[class_name]:
      hash += self._field2value[field].__hash__()
    return hash

  def __eq__(self, other):
    if type(other) != OFFingerprint:
      return False
    if self.field2value["class"] != other.field2value["class"]:
      return False
    for field in self.pkt_type_to_fields:
      if self._field2value[field] != other._field2value[field]:
        return False
    return True

class DPFingerprint(Fingerprint):
  ''' Fingerprints for dataplane messages '''
  fields = ['dl_src', 'dl_dst', 'nw_src', 'nw_dst']

  @staticmethod
  def from_pkt(pkt):
    # For now, just take (src MAC, dst MAC, src IP, dst IP) as the fingerprint for
    # dataplane packets
    # TODO(cs): might finer granularity later
    eth = pkt
    ip = pkt.next
    field2value = {'dl_src': eth.src.toStr(), 'dl_dst': eth.dst.toStr(),
                   'nw_src': ip.srcip.toStr(), 'nw_dst': ip.dstip.toStr()}
    return DPFingerprint(field2value)

  def __hash__(self):
    hash = 0
    # Note that the order is important
    for field in self.fields:
      hash += self._field2value[field].__hash__()
    return hash

  def __eq__(self, other):
    if type(other) != DPFingerprint:
      return False
    for field in self.fields:
      if self._field2value[field] != other._field2value[field]:
        return False
    return True
