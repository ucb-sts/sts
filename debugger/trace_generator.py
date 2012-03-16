'''
Created on Mar 15, 2012

@author: rcs
'''

from pox.lib.packet.ethernet import *
from pox.lib.packet.ipv4 import *
from pox.lib.packet.icmp import *
from pox.lib.util import assert_type
import topology_generator as topo_gen
import pickle

class DataplaneEvent (object):
  '''
  Encapsulates a packet injected at a (switch.dpid, port) pair in the network
  Used for trace generation or replay debugging
  '''
  def __init__ (self, switch_dpid, port_no, packet):
    assert_type("switch", switch_dpid, int, none_ok=False)
    assert_type("port", port_no, int, none_ok=False)
    assert_type("packet", packet, ethernet, none_ok=False)
    self.switch_dpid = switch_dpid
    self.port_no = port_no
    self.packet = packet
    
def write_trace_log(dataplane_events, filename):
  '''
  Given a list of DataplaneEvents and a log filename, writes out a log.
  For manual trace generation rather than replay logging
  '''
  pickle.dump(dataplane_events, file(filename, "w"))
  
def generate_example_trace():
  trace = []
  
  (patch_panel, switches, links) = topo_gen.create_mesh(num_switches=2)
  host_a_eth = ethernet(src=EthAddr("AA:00:00:00:00:00"),dst=switches[0].ports[1].hw_addr,type=ethernet.IP_TYPE)
  host_b_eth = ethernet(src=EthAddr("BB:00:00:00:00:00"),dst=switches[1].ports[1].hw_addr,type=ethernet.IP_TYPE)
  host_a_ip_addr = IPAddr(0xAA000000)
  host_b_ip_addr = IPAddr(0xBB000000)
  
  host_a_ipp = ipv4(protocol=ipv4.ICMP_PROTOCOL, srcip=host_a_ip_addr, dstip=host_b_ip_addr)
  host_b_ipp = ipv4(protocol=ipv4.ICMP_PROTOCOL, srcip=host_b_ip_addr, dstip=host_a_ip_addr)
  host_a_echo_request = icmp(type=TYPE_ECHO_REQUEST, payload="ping")
  host_b_echo_reply = icmp(type=TYPE_ECHO_REPLY, payload="pong")
  
  host_a_ipp.payload = host_a_echo_request
  host_a_eth.payload = host_a_ipp
  host_b_ipp.payload = host_b_echo_reply
  host_b_eth.payload = host_b_ipp
    
  # ping ping (no responses) between fake hosts
  for _ in range(0,40):
    trace.append(DataplaneEvent(switches[0].dpid, 1, host_a_eth))
    trace.append(DataplaneEvent(switches[1].dpid, 1, host_b_eth))
    
  write_trace_log(trace, "traces/ping_pong.trace")
  

if __name__ == '__main__':
  generate_example_trace()