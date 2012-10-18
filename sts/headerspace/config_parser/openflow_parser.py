'''
Created on Mar 7, 2012

@author: rcs
'''
from helper import *
from sts.headerspace.headerspace.tf import *
from sts.headerspace.headerspace.hs import *
from pox.openflow.libopenflow_01 import *
from pox.openflow.flow_table import SwitchFlowTable, TableEntry
from pox.openflow.software_switch import SoftwareSwitch

import re
from collections import namedtuple

global header_length
header_length = 31
# These should really be frozen (immutable), but python doesn't have language support for that..
global all_one
all_one = byte_array_get_all_one(header_length*2)
global all_zero
all_zero = byte_array_get_all_zero(header_length*2)
global all_x
all_x = byte_array_get_all_x(header_length*2)

global fields
# Taken from ofp_match in openflow 1.0 spec
# Note that these are ordered
fields = ["dl_src", "dl_dst", "dl_vlan", "dl_vlan_pcp", "dl_type", "nw_tos", "nw_proto", "nw_src", "nw_dst", "tp_src", "tp_dst"]

field_info = namedtuple('field_info', ['position', 'length'])

def ethernet_display(bytes):
  if bytes_all_x(bytes):
    return "x"
  else:
    # OpenFlow 1.0 doesn't support prefix matching over ethernet addrs
    # So assume it's raw (no wildcards)
    #print "Int unpacked is:", bytes_to_int(bytes)
    #print "Eth String is:" + str(EthAddr(bytes_to_int(bytes)))
    return str(EthAddr(bytes_to_int(bytes)))

def ip_display(bytes):
  if bytes_all_x(bytes):
    # Optimization
    return "x"
  else:
    if len(bytes) != 4*2:
      raise RuntimeError(len(bytes))

    # Have to get a bit at a time, since an HSA byte contains 4 real bits,
    # and mask length may not be a multiple of 4
    # 0th byte, 0th bit is least significant
    val = 0
    current_idx = 0
    mask_length_bits = 32
    # twice as many bytes as normal IP addr
    for byte_idx in range(8):
      # Half as many bits per byte
      for bit_idx in range(4):
        bit_val = byte_array_get_bit(bytes,byte_idx,bit_idx)
        if bit_val == 0x03:
          # wildcard.
          # Assumes that all wildcard bits are consecutive (no non-wildcard exists after a wildcard)
          mask_length_bits -= 1
        else:
          normal_bit = hsa_bit_to_normal_bit(bit_val)
          val += (normal_bit << current_idx)
        current_idx += 1

    # I'm misunderstanding something about IPAddr's network order
    # arg... the val is in network order (has been sanity checked), but
    # seeting network_order=True makes the byte order backwards...
    return IPAddr(val).__str__() + "/" + str(mask_length_bits)

def default_display(bytes):
  if bytes_all_x(bytes):
    return "x"
  else:
    return str(bytes_to_int(bytes))

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

  # 31 bytes
  format["length"] = position

  display_handler_map = {
    "dl_src" : ethernet_display,
    "dl_dst" : ethernet_display,
    "dl_vlan" : default_display,
    "dl_vlan_pcp" : default_display,
    "dl_type" :  default_display,
    "nw_tos" : default_display,
    "nw_proto" : default_display,
    "nw_src" : ip_display,
    "nw_dst" : ip_display,
    "tp_src" : default_display,
    "tp_dst" : default_display
  }

  def display(byte_array):
    # Note that byte array is twice the length of our format (to encode x, y)
    # so, s/b 62 bytes long
    if len(byte_array) != format["length"]*2:
      raise "Unknown byte array length. Got %d, s/b %d" % (len(byte_array),format["length"]*2)

    if byte_array_equal(byte_array, all_one):
      return "1^L"
    if byte_array_equal(byte_array, all_zero):
      return "0^L"
    if byte_array_equal(byte_array, all_x):
      return "x^L"

    field_strs = []
    for field in fields:
      strings = []
      strings.append(field)
      strings.append(":")
      # Twice as many HSA bytes to normal bytes
      last_byte_index = format[field].length * 2
      bytes = byte_array[0:last_byte_index]
      byte_array = byte_array[last_byte_index:]
      display = display_handler_map[field](bytes)
      if display == "x":
        continue
      strings.append(display)
      field_strs.append("".join(strings))
    return ",".join(field_strs)

  format["display"] = display
  return format

global hs_format
hs_format = HS_FORMAT()

# TODOC: wtf does wc stand for?
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
  b_array = int_to_byte_array(value,8*hs_format[field].length)
  start_pos = 2*hs_format[field].position
  for i in range(2*hs_format[field].length):
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

def ofp_match_to_input_ports(ofp_match, switch, all_port_ids):
  in_ports = []
  if (ofp_match.wildcards & OFPFW_IN_PORT):
    in_ports = all_port_ids
  else:
    in_ports = [get_uniq_port_id(switch, ofp_match.in_port)]
  return in_ports

def ofp_match_to_hsa_match(ofp_match):
  hsa_match = byte_array_get_all_x(hs_format["length"]*2)

  def field_wardcarded(ofp_match, flag):
    if (ofp_match.wildcards & flag):
      return True
    return False

  for field_name in set(ofp_match_data.keys()) - set(['in_port','dl_src','dl_dst','nw_src','nw_dst']):
    flag = ofp_match_data[field_name][1]
    if not field_wardcarded(ofp_match, flag):
      set_field(hsa_match, field_name, getattr(ofp_match, field_name))

  for field_name in ['dl_src', 'dl_dst']:
    addr = getattr(ofp_match, field_name)
    if addr is not None: # None addr implies wildcard
      if type(addr) != EthAddr:
        addr = EthAddr(addr).toInt()
      else:
        addr = addr.toInt()
      #print "addr is: ", addr
      set_field(hsa_match, field_name, addr)

  for field_name in ['nw_src', 'nw_dst']:
    (addr, mask_bits_from_left) = getattr(ofp_match, "get_%s"%field_name)()
    if addr is not None: # None addr implies wildcard
      # TODO: signed or unsigned?
      if type(addr) == IPAddr:
        addr = socket.htonl(addr.toUnsignedN())
      # if addr, not all wildcard bits set
      set_field(hsa_match, field_name, addr, right_mask=32-mask_bits_from_left)
  return hsa_match

# Returns (mask, rewrite)
def ofp_actions_to_hsa_rewrite(ofp_actions):
  # TODO: this should include the previous match by default? Is that already implemented by TF?
  # Bits set to one are not touched
  mask = byte_array_get_all_one(hs_format["length"]*2)
  # Bits set to one are rewritten
  rewrite = byte_array_get_all_zero(hs_format["length"]*2)

  def set_vlan_id(action):
    set_field(mask, "vlan", 0)
    set_field(rewrite, "vlan", action.vlan_id)
  def set_vlan_pcp(action):
    set_field(mask, "vlan_pcp", 0)
    set_field(rewrite, "vlan_pcp", action.vlan_pcp)
  def strip_vlan(action):
    # TODO: Is this a bug in software_switch? Two pcps...
    set_field(mask, "vlan", 0)
    set_field(rewrite, "vlan", 0)
  def set_dl_src(action):
    set_field(mask, "dl_src", 0)
    set_field(rewrite, "dl_src", action.dl_addr)
  def set_dl_dst(action):
    set_field(mask, "dl_dst", 0)
    set_field(rewrite, "dl_dst", action.dl_addr)
  def set_nw_src(action):
    set_field(mask, "nw_src", 0)
    set_field(rewrite, "nw_src", action.nw_addr)
  def set_nw_dst(action):
    set_field(mask, "nw_dst", 0)
    set_field(rewrite, "nw_dst", action.nw_addr)
  def set_nw_tos(action):
    set_field(mask, "nw_tos", 0)
    set_field(rewrite, "nw_tos", action.nw_tos)
  def set_tp_src(action):
    set_field(mask, "tp_src", 0)
    set_field(rewrite, "tp_src", action.tp_port)
  def set_tp_dst(action):
    set_field(mask, "tp_dst", 0)
    set_field(rewrite, "tp_dst", action.tp_port)

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

  for action in ofp_actions:
    if action.type in handler_map:
      handler_map[action.type](action)

  return (mask, rewrite)

def ofp_actions_to_output_ports(ofp_actions, switch, all_port_ids, in_port_id):
  global out_port_nos
  output_port_nos = []

  def output_packet(action):
    out_port = action.port
    out_port_id = get_uniq_port_id(switch, out_port)
    if out_port < OFPP_MAX:
      output_port_nos.append(out_port_id)
    elif out_port == OFPP_IN_PORT:
      output_port_nos.append(in_port_id)
    elif out_port == OFPP_FLOOD or out_port == OFPP_ALL:
      for port_id in all_port_ids:
        if port_id != in_port_id:
          output_port_nos.append(port_id)
    elif out_port == OFPP_CONTROLLER:
      return
    else:
      raise("Unsupported virtual output port: %x" % out_port)

  handler_map = {
    OFPAT_OUTPUT: output_packet,
    OFPAT_ENQUEUE: output_packet,
  }

  for action in ofp_actions:
    if action.type in handler_map:
      handler_map[action.type](action)

  return output_port_nos

def generate_transfer_function(tf, software_switch):
  '''
  The rules will be added to transfer function tf passed to the function.
  '''
  log.debug("=== Generating Transfer Function for switch %d ===" % software_switch.dpid)
  # generate the forwarding part of transfer fucntion, from the fwd_prt, to pre-output ports
  table = software_switch.table
  all_port_ids = map(lambda port: get_uniq_port_id(software_switch, port), software_switch.ports.values())
  for flow_entry in table.entries:
    # TODO: For now, we're assuming completely non-overlapping entries. Need to
    #       deal with priorities properly!
    ofp_match = flow_entry.match
    ofp_actions = flow_entry.actions

    hsa_match = ofp_match_to_hsa_match(ofp_match)
    input_port_ids = set(ofp_match_to_input_ports(ofp_match, software_switch, all_port_ids))
    (mask, rewrite) = ofp_actions_to_hsa_rewrite(ofp_actions)
    output_port_nos = set()
    for input_port_id in input_port_ids:
      output_port_nos = output_port_nos.union(ofp_actions_to_output_ports(ofp_actions, software_switch, all_port_ids, input_port_id))

    # No self-loops. TODO: this is the wrong place to handle this
    input_port_ids -= output_port_nos

    if len(output_port_nos) == 0:
      # No output ports means a dropped packet in OpenFlow
      self_rule = TF.create_standard_rule(input_port_ids,hsa_match,[],None,None)
      tf.add_fwd_rule(self_rule)
    else:
      tf_rule = TF.create_standard_rule(input_port_ids, hsa_match, output_port_nos, mask, rewrite)
      if byte_array_equal(mask, all_one) and byte_array_equal(rewrite, all_zero):
        tf.add_fwd_rule(tf_rule)
      else:
        tf.add_rewrite_rule(tf_rule)

  log.debug("=== Successfully Generated Transfer function ===")
  return 0

def get_kw_for_field_match(field_match):
  # TODO(cs): nom_snapshot is not defined
  type_to_name = {
    nom_snapshot.Match.dl_src:"dl_src",
    nom_snapshot.Match.dl_dst:"dl_dst",
    nom_snapshot.Match.dl_vlan:"dl_vlan",
    nom_snapshot.Match.dl_vlan_pcp:"dl_vlan_pcp",
    nom_snapshot.Match.dl_type:"dl_type",
    nom_snapshot.Match.nw_tos:"nw_tos",
    nom_snapshot.Match.nw_proto:"nw_proto",
    nom_snapshot.Match.nw_src:"nw_src",
    nom_snapshot.Match.nw_dst:"nw_dst",
    nom_snapshot.Match.tp_src:"tp_src",
    nom_snapshot.Match.tp_dst:"tp_dst",
    nom_snapshot.Match.in_port:"in_port",
    nom_snapshot.Match.switch:"switch"
  }

  value = field_match.value
  field_name = type_to_name[field_match.field]
  if field_name == "dl_dst" or field_name == "dl_src":
    value = "EthAddr(\"%s\")" % value
  if field_name == "nw_dst" or field_name == "nw_src":
    # Odd that ofp_match takes EthAddrs, but just strings for IpAddrs...
    value = "\"%s\"" % value

  return "%s=%s" % (field_name, value)

def tf_from_switch(ntf, switch, real_switch):
  # clone the real switch, insert flow entries from policy, run
  # generate_transfer_function()
  dummy_switch = SoftwareSwitch(real_switch.dpid, ports=real_switch.ports.values())
  for entry in switch.flow_table.entries:
    dummy_switch.table.add_entry(entry)
  return generate_transfer_function(ntf, dummy_switch)

def get_uniq_port_id(switch, port):
  ''' HSA assumes uniquely labeled ports '''
  if type(switch) == int:
    dpid = switch
  else:
    dpid = switch.dpid

  if type(port) == int or type(port) == long:
    port_no = port
  else:
    port_no = port.port_no

  # The cisco config parser multiplies the dpid by 100000 and adds the port
  # number. (The hassel-c code assumes this encoding)
  return (dpid * 100000) + port_no
