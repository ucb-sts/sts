'''
Created on Mar 7, 2012

@author: rcs
'''
from helper import *
from headerspace.headerspace.tf import *
from headerspace.headerspace.hs import *
from pox.openflow.libopenflow_01 import *

import re
from collections import namedtuple

global fields
# Taken from ofp_match in openflow 1.0 spec
# Note that these are ordered
fields = ["dl_src", "dl_dst", "dl_vlan", "dl_vlan_pcp", "dl_type", "nw_tos", "nw_proto", "nw_src", "nw_dst", "tp_src", "tp_dst"]

field_info = namedtuple('field_info', ['position', 'length'])
    
def HS_FORMAT():
  format = {}
  
  field_lengths = {
    "dl_src" : 6,
    "dl_dst" : 6,
    "dl_vlan" : 2,
    "dl_vlan_pcp" : 1,       
    "dl_type" : 2,
    "nw_tos" : 1,
    "nw_proto" : 1,
    "nw_src" : 4,
    "nw_dst" : 4,
    "tp_src" : 2,
    "tp_dst" : 2
  }
  
  position = 0
  for field in fields:
    field_length =  field_lengths[field]
    format[field] = field_info(position, field_length)
    position += field_length
    
  format["length"] = position
  return format

global hs_format
hs_format = HS_FORMAT()
  
def wc_to_parsed_string(byte_arr):
  out_string = ""
  for field in fields:
    offset = hs_format[field].position
    len = hs_format[field].length
    ba = bytearray()
    for i in range(0,len):
      ba.append(byte_arr[offset+i])
    out_string = "%s%s:%s, "%(out_string,field,byte_array_to_hs_string(ba))
  return out_string

def set_field(arr, field, value, right_mask=0):
  '''
  Sets the field in byte array arr to value.
  @arr: the bytearray to set the field bits to value.
  @field: 'eth_src','eth_dst','vlan','vlan_priority','eth_frame','ip_tos','ip_src','ip_dst','ip_proto','tcp_src','tcp_dst'
  @value: an integer number, of the width equal to field's width
  @right_mask: number of bits, from right that should be ignored when written to field.
  e.g. to have a /24 ip address, set mask to 8.
  '''
  b_array = int_to_byte_array(value,8*hs_format["%s_len"%field])
  start_pos = 2*hs_format["%s_pos"%field]
  for i in range(2*hs_format["%s_len"%field]):
    if right_mask <= 4*i:
      arr[start_pos + i] = b_array[i]
    elif (right_mask > 4*i and right_mask < 4*i + 4):
      shft = right_mask % 4;
      rm = (0xff << 2*shft) & 0xff
      lm = ~rm & 0xff
      arr[start_pos + i] = (b_array[i] & rm) | (arr[start_pos + i] & lm)
      
# XXX CURRENTLY NOT WORKING
def optimize_forwarding_table(self):
  print "=== Compressing forwarding table ==="
  print " * Originally has %d ip fwd entries * "%len(self.fwd_table)
  n = compress_ip_list(self.fwd_table)
  print " * After compression has %d ip fwd entries * "%len(n)
  self.fwd_table = n
  '''
  for elem in n:
      str = "%s/%d: action: %s compressing: "%(int_to_dotted_ip(elem[0]) , elem[1], elem[2])
      for e in elem[3]:
          str = str + int_to_dotted_ip(e[0]) + "/%d, "%e[1]
      print str
  '''
  print "=== DONE forwarding table compression ==="
  
def ofp_match_to_ports(ofp_match, all_port_nos):
  in_ports = []
  if (ofp_match.wildcards & OFPFW_IN_PORT) or (ofp_match.wildcards & OFPFW_ALL):
    in_ports = all_port_nos 
  else:
    in_ports = [ofp_match.in_port]
    
def ofp_match_to_hsa_match(ofp_match):
  hsa_match = byte_array_get_all_x(hs_format["length"]*2)
  if (ofp_match.wildcards & OFPFW_ALL):
    return hsa_match
  
  def set_hsa_field_match(ofp_match, hsa_match, field_name, flag):
    if (ofp_match.wildcards & flag):
      return # keep the bits wildcarded
    set_field(hsa_match, field_name, ofp_match.__dict__[field_name])
    
  for field_name in ofp_match_data.keys() - ['in_port']:
    flag = ofp_match_data[field_name][1]
    set_hsa_field_match(ofp_match, hsa_match, field_name, flag)  
    
def ofp_actions_to_hsa_rewrite(ofp_actions):
  hsa_match = byte_array_get_all_x(hs_format["length"]*2)
  
    def set_vlan_id(action, packet):
      if not isinstance(packet, vlan): packet = vlan(packet)
      packet.id = action.vlan_id
    def set_vlan_pcp(action, packet):
      if not isinstance(packet, vlan): packet = vlan(packet)
      packet.pcp = action.vlan_pcp
    def strip_vlan(action, packet):
      if not isinstance(packet, vlan): packet = vlan(packet)
      packet.pcp = action.vlan_pcp
    def set_dl_src(action, packet):
      packet.src = action.dl_addr
    def set_dl_dst(action, packet):
      packet.dst = action.dl_addr
    def set_nw_src(action, packet):
      if(isinstance(packet, ipv4)):
        packet.nw_src = action.nw_addr
    def set_nw_dst(action, packet):
      if(isinstance(packet, ipv4)):
        packet.nw_dst = action.nw_addr
    def set_nw_tos(action, packet):
      if(isinstance(packet, ipv4)):
        packet.tos = action.nw_tos
    def set_tp_src(action, packet):
      if(isinstance(packet, udp) or isinstance(packet, tcp)):
        packet.srcport = action.tp_port
    def set_tp_dst(action, packet):
      if(isinstance(packet, udp) or isinstance(packet, tcp)):
        packet.dstport = action.tp_port

    handler_map = {
        OFPAT_SET_VLAN_VID: set_vlan_id,
        OFPAT_SET_VLAN_PCP: set_vlan_pcp,
        OFPAT_STRIP_VLAN: strip_vlan,
        OFPAT_SET_DL_SRC: set_dl_src,
        OFPAT_SET_DL_DST: set_dl_dst,
        OFPAT_SET_NW_SRC: set_nw_src,
        OFPAT_SET_NW_DST: set_nw_dst,
        OFPAT_SET_NW_TOS: set_nw_tos,
        OFPAT_SET_TP_SRC: set_tp_src,
        OFPAT_SET_TP_DST: set_tp_dst,
    }
    for action in actions:
      if(action.type not in handler_map):
        raise NotImplementedError("Unknown action type: %x " % type)
      handler_map[action.type](action, packet)
  
def generate_transfer_function(tf, software_switch):
  '''
  The rules will be added to transfer function tf passed to the function.
  '''
  print "=== Generating Transfer Function ==="
  # generate the forwarding part of transfer fucntion, from the fwd_prt, to pre-output ports
  table = software_switch.table
  all_port_nos = software_switch.ports.keys()
  for flow_entry in table.entries:
    # TODO: For now, we're assuming completely non-overlapping entries. Need to 
    #       deal with priorities properly!
    ofp_match = flow_entry.match
    hsa_match = ofp_match_to_hsa_match(ofp_match)
    port_nos = ofp_match_to_ports(ofp_match, all_port_nos)
    
    # DROP RULE: self_rule = TF.create_standard_rule(in_port,match,[],None,None,file_name,lines)
 
    # TODO: finish me
         
  print "=== Successfully Generated Transfer function ==="
  #print tf
  return 0
