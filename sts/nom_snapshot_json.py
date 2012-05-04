import json
from pox.openflow.libopenflow_01 import ofp_match, ofp_action_output
from pox.openflow.flow_table import TableEntry

class Match:
  def __init__(self, in_port):
    self.in_port = in_port
    self.dl_src=None
    self.dl_dst=None
    self.dl_vlan=None
    self.dl_vlan_pcp=None
    self.dl_type=None
    self.nw_tos=None
    self.nw_proto=None
    self.nw_src=None
    self.nw_dst=None
    self.tp_src=None
    self.tp_dst=None
    self.switch=None

  def to_match(self):
    return ofp_match(in_port=self.in_port)

  @staticmethod
  def from_json_map(m):
    return Match(in_port=m['inputPort'])

class Snapshot:
  def __init__(self, dpid, match, out_port):
    self.dpid=dpid
    self.match = match
    self.out_port=out_port

  @staticmethod
  def from_json_map(m):
    return Snapshot(dpid=m['dpid'], match=Match.from_json_map(m['match']),
                     out_port=m['action']['port'])

  def to_entry(self):
    return TableEntry(match = self.match.to_match(), actions = [  ofp_action_output(port=self.out_port) ])
