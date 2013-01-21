
from sts.fingerprints.base import Fingerprint
from pox.openflow.libopenflow_01 import *
from pox.lib.packet.ethernet import *
from pox.lib.packet.lldp import *
from pox.lib.packet.arp import *
from pox.lib.packet.ipv4 import *
import sts.headerspace.config_parser.openflow_parser as hsa

def process_data(msg):
  if msg.data == b'':
    return ()
  else:
    dp_packet = ethernet(msg.data)
    return DPFingerprint.from_pkt(dp_packet)

def process_actions(msg):
  return tuple("output(%d)" % a.port if isinstance(a, ofp_action_output) else str(type(action)) for a in msg.actions)

class OFFingerprint(Fingerprint):
  ''' Fingerprints for openflow messages '''
  #  ofp_type -> fields to include in fingerprint
  # TODO(cs): I'm erring on the side of sparseness rather than completeness. We
  # may need to include more fields here to get an unambiguous fingerprint
  pkt_type_to_fields = {
    "ofp_features_reply" : ["datapath_id"],
    "ofp_switch_config" : ["flags"],
    "ofp_flow_mod" : ["match", "idle_timeout", "hard_timeout", "priority",
                     "out_port", "flags", "actions"],
    "ofp_port_mod" : ["port_no", "hw_addr", "config", "mask", "advertise"],
    "ofp_queue_get_config_request" : [],
    "ofp_queue_get_config_reply" : [],
    "ofp_stats_request" : ["type", "flags"],
    "ofp_stats_reply" : ["type", "flags"],
    "ofp_desc_stats" : [],
    "ofp_flow_stats_request" : [],
    "ofp_flow_stats" : [],
    "ofp_aggregate_stats_request" : [],
    "ofp_aggregate_stats" : [],
    "ofp_port_stats_request" : [],
    "ofp_port_stats" : [],
    "ofp_queue_stats_request" : [],
    "ofp_queue_stats" : [],
    "ofp_packet_out" : ["data", "in_port", "actions"],
    "ofp_barrier_reply" : [],
    "ofp_barrier_request" : [],
    "ofp_packet_in" : ["in_port", "data"],
    "ofp_flow_removed" : ["match", "reason", "priority"],
    "ofp_port_status" : ["reason", "desc"],
    "ofp_error" : ["type", "code"],
    "ofp_hello" : [],
    "ofp_echo_request" : [],
    "ofp_echo_reply" : [],
    "ofp_vendor_header" : [],
    "ofp_vendor" : [], # (body of ofp_vendor_header)
    "ofp_features_request" : [],
    "ofp_get_config_request" : [],
    "ofp_get_config_reply" : [],
    "ofp_set_config" : []
  }
  special_fields = {
    # data needs a nested fingerprint
    'data' : process_data,
    # desc is a ofp_phy_port object
    'desc' : lambda pkt: (pkt.desc.port_no, pkt.desc.hw_addr.toStr()),
    # actions is an ordered list
    # for now, store it as a tuple of just the names of the action types
    'actions' : process_actions,
    # match has a bunch of crazy fields
    # Trick: convert it to an hsa match, and extract the human readable string
    # for the hsa match
    'match' : lambda pkt: hsa.hs_format["display"](hsa.ofp_match_to_hsa_match(pkt.match))
  }

  def __init__(self, field2value):
    if type(field2value) == OFFingerprint:
      field2value = field2value._field2value
    # Convert matches to DPFingerprint objects
    for field, value in field2value.iteritems():
      if type(value) == dict:
        field2value[field] = DPFingerprint(value)
    super(OFFingerprint, self).__init__(field2value)

  @staticmethod
  def from_pkt(pkt):
    pkt_type = type(pkt).__name__
    if pkt_type not in OFFingerprint.pkt_type_to_fields:
      raise ValueError("Unknown pkt_type %s" % pkt_type)
    field2value = {}
    field2value["class"] = pkt_type
    fields = OFFingerprint.pkt_type_to_fields[pkt_type]
    for field in fields:
      if field in OFFingerprint.special_fields:
        value = OFFingerprint.special_fields[field](pkt)
      else:
        value = getattr(pkt, field)
      field2value[field] = value
    return OFFingerprint(field2value)

  def human_str(self):
    return "%s: " % self._field2value["class"] + \
        ", ".join("%s=%s" % (k, v) for (k,v) in self._field2value.iteritems() if k != "class" )


  def __hash__(self):
    hash = 0
    class_name = self._field2value["class"]
    hash += class_name.__hash__()
    # Note that the order is important
    for field in self.pkt_type_to_fields[class_name]:
      hash += self._field2value[field].__hash__()
    return hash

  def __eq__(self, other):
    if type(other) != OFFingerprint:
      return False
    if self._field2value["class"] != other._field2value["class"]:
      return False
    klass = self._field2value["class"]
    for field in self.pkt_type_to_fields[klass]:
      ###### NOTE: do /not/ use the '!=' operator here, this doesn't invoke an override __eq__ method
      if not (self._field2value[field] == other._field2value[field]):
        return False
    return True

class DPFingerprint(Fingerprint):
  ''' Fingerprints for dataplane messages '''
  fields = ['dl_src', 'dl_dst', 'nw_src', 'nw_dst']

  def __init__(self, field2value):
    if type(field2value) == DPFingerprint:
      field2value = field2value._field2value
    super(DPFingerprint, self).__init__(field2value)

  @staticmethod
  def from_pkt(pkt):
    # For now, just take (src MAC, dst MAC, src IP, dst IP) as the fingerprint for
    # dataplane packets
    # TODO(cs): might finer granularity later
    eth = pkt
    ip = pkt.next
    if type(ip) == lldp:
      return DPFingerprint({'class': 'lldp'})
    elif type(ip) == ipv4:
      field2value = {'dl_src': eth.src.toStr(), 'dl_dst': eth.dst.toStr(),
                     'nw_src': ip.srcip.toStr(), 'nw_dst': ip.dstip.toStr()}
      return DPFingerprint(field2value)
    elif type(ip) == arp:
      # TODO(cs): should include more context
      return DPFingerprint({'class': 'arp'})
    else:
      raise ValueError("Unknown dataplane packet type %s" % str(type(ip)))

  def __hash__(self):
    hash = 0
    if 'class' in self._field2value and len(self._field2value) == 1:
      # This is not an IP packet -- it could be, e.g., an LLDAP packet
      hash += self._field2value['class'].__hash__()
      return hash

    # Else it's an IP packet
    # Note that the order is important
    for field in self.fields:
      hash += self._field2value[field].__hash__()
    return hash

  def __eq__(self, other):
    if type(other) != DPFingerprint:
      return False
    if len(self._field2value) != len(other._field2value):
      return False
    if 'class' in self._field2value:
      return ('class' in other._field2value and
              self._field2value['class'] == other._field2value['class'])
    for field in self.fields:
      if self._field2value[field] != other._field2value[field]:
        return False
    return True
