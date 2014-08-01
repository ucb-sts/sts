# Copyright 2014      Ahmed El-Hassany
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""
Parses the output of ovs-ofctl dump-flows -F openflow10 {Switch} into
POX FlowTable
"""


import re
from pox.lib.addresses import EthAddr, IPAddr
import pox.openflow.libopenflow_01 as of
from pox.openflow.flow_table import TableEntry
from pox.openflow.flow_table import SwitchFlowTable


# Fields match on, and the type conversion function.
match_fields = {
  'in_port': lambda x: int(x),
  'dl_src': lambda x: EthAddr(x),
  'dl_dst': lambda x: EthAddr(x),
  'dl_vlan': lambda x: int(x),
  'dl_vlan_pcp': lambda x: int(x),
  #'pad1' : (_PAD, 0),
  'dl_type': lambda x: int(x),
  'nw_tos': lambda x: int(x),
  'nw_proto': lambda x: int(x),
  #'pad2' : (_PAD2, 0),
  'nw_src': lambda x: IPAddr(x),
  'nw_dst': lambda x: IPAddr(x),
  'tp_src': lambda x: int(x),
  'tp_dst': lambda x: int(x),
#  'mpls_label': (0, OFPFW_MPLS_LABEL),
#  'mpls_tc': (0, OFPFW_MPLS_TC),
}


# L2 types
dl_types = {
  'ip': 0x0800,
  'icmp': 0x0800, #nw_proto=1.'
  'tcp': 0x0800, #nw_proto=6.'
  'udp': 0x0800, #nw_proto=17.'
  'arp': 0x0806,
  'rarp':0x8035,
}

# L3 types
nw_proto = {
  'icmp': 1,
  'tcp': 6,
  'udp': 17,
}


# Actions we parse
actions_dict = {
  'output'             : lambda x: of.ofp_action_output(port=int(x)),
  'mod_vlan_vid'       : lambda x: of.ofp_action_vlan_vid(vlan_id=int(x, 16)),
  'mod_vlan_pcp'       : lambda x: of.ofp_action_vlan_pcp(vlan_pcp=int(x, 16)),
  # TODO (AH) figure strip vlan id
  #'OFPAT_STRIP_VLAN'   : lambda x: of.ofp_action_,
  'mod_dl_src'         : lambda x: of.ofp_action_dl_addr.set_src(dl_addr=EthAddr(x)),
  'mod_dl_dst'         : lambda x: of.ofp_action_dl_addr.set_dst(dl_addr=EthAddr(x)),
  'mod_nw_src'         : lambda x: of.ofp_action_nw_addr.set_src(dl_addr=IPAddr(x)),
  'mod_nw_dst'         : lambda x: of.ofp_action_nw_addr.set_dst(dl_addr=IPAddr(x)),
  'nw_tos'             : lambda x: of.ofp_action_nw_tos(nw_tos=int(x)),
  'tp_src'             : lambda x: of.ofp_action_tp_port.set_src(tp_port=int(x)),
  'tp_dst'             : lambda x: of.ofp_action_tp_port.set_src(tp_port=int(x)),
  'enqueue'            : lambda x: of.ofp_action_enqueue(port=int(x.split(':')[0]), queue_id=int(x.split(':')[1])),
}

# TODO (AH): parse these actions
'''
  'OFPAT_SET_MPLS_LABEL' : 13,
  'OFPAT_SET_MPLS_TC'  :  14,
  'OFPAT_SET_MPLS_TTL' : 15,
  'OFPAT_DEC_MPLS_TTL' : 16,
  'OFPAT_PUSH_MPLS'    : 19,
  'OFPAT_POP_MPLS'     : 20,
  'OFPAT_RESUBMIT'     : 21,
  'OFPAT_VENDOR'       : 65535,
'''


# Table entry variables.
table_entry_dict = {
  'priority': lambda x: int(x),
  'cookie': lambda x: int(x, 16),
  'idle_timeout': lambda x: int(x),
  'hard_timeout': lambda x: int(x),
  'buffer_id': lambda x: int(x),
  'match': lambda x: x,
  'actions': lambda x: x,
}


def parse_actions(actions_str):
  actions = []
  for token in actions_str.split(','):
    if ':' in token:
      key, value = token.split(':', 1)
    elif '=' in token:
      key, value = token.split('=', 1)
    else:
      print "Unknown delimiter for actions:", token
      continue
    if key not in actions_dict:
      print "Unknown action", token
    action = actions_dict[key](value)
    actions.append(action)
  return actions


def parse_match(match_str):
  match_dict = {}
  priority = 0
  for tmp in match_str.split(','):
    if '=' in tmp:
      key, value = tmp.split('=')
      if key in match_fields:
        match_dict[key] = match_fields[key](value)
      elif key == 'priority':
        priority = int(value)
      else:
        print "Key doesn't exist in match_fields: ", key
    else:
      if tmp in dl_types:
        match_dict['dl_type'] = dl_types[tmp]
        if match_dict['dl_type'] in nw_proto:
          match_dict['nw_proto'] = nw_proto[match_dict['dl_type']]
      else:
        print "Unknown non equal match :", tmp
  return of.ofp_match(**match_dict), priority


def parse_line(line):
  line = line.strip()
  if line == '' or not line.startswith('cookie'):
    return None
  tokens = {}
  for tmp in re.split(r',\ |\ ', line):
    if tmp == '':
      continue
    key, value = tmp.split('=', 1)
    if key == 'priority' or key in match_fields.keys():
      tokens['match'] = tmp
    elif key == 'actions':
      tokens['actions'] = value
    else:
      tokens[key] = value
  if len(tokens) == 0:
    return None
  match, priority = parse_match(tokens['match'])
  actions = parse_actions(tokens['actions'])
  table_entry = {}
  for token in tokens:
    if token in table_entry_dict and token not in ['match', 'actions']:
      table_entry[token] = table_entry_dict[token](tokens[token])
  table_entry['match'] = match
  table_entry['actions'] = actions
  entry = TableEntry(**table_entry)
  return entry


def parse_table(dump):
  table = SwitchFlowTable()
  for line in dump.split("\n"):
    line = line.strip()
    if not line.startswith('cookie'):
      print "Skipping", line
      continue
    entry = parse_line(line)
    if entry is None: continue
    table.add_entry(entry)
  return table