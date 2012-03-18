'''
Created on Mar 15, 2012

@author: rcs
'''

from pox.lib.packet.ethernet import *
from pox.lib.packet.ipv4 import *
from pox.lib.packet.icmp import *
from pox.lib.util import assert_type
import topology_generator as topo_gen
from debugger_entities import HostInterface
import pickle

class DataplaneEvent (object):
  '''
  Encapsulates a packet injected at a (switch.dpid, port) pair in the network
  Used for trace generation or replay debugging
  '''
  def __init__ (self, hostname, interface, packet):
    assert_type("hostname", hostname, str, none_ok=False)
    assert_type("interface", interface, HostInterface, none_ok=False)
    assert_type("packet", packet, ethernet, none_ok=False)
    self.hostname = hostname
    self.interface = interface 
    self.packet = packet

def write_trace_log(dataplane_events, filename):
  '''
  Given a list of DataplaneEvents and a log filename, writes out a log.
  For manual trace generation rather than replay logging
  '''
  pickle.dump(dataplane_events, file(filename, "w"))
  
def generate_example_trace():
  trace = []
  
  (patch_panel, switches, network_links, hosts, access_links) = topo_gen.create_mesh(num_switches=2)
  
  packet_events = []
  ping_or_pong = "ping"
  for access_link in access_links:
    other_host = (set(hosts) - set([access_link.host])).pop()
    eth = ethernet(src=access_link.host.interfaces[0].mac,dst=access_link.switch_port.hw_addr,type=ethernet.IP_TYPE)
    dst_ip_addr = other_host.interfaces[0].ips[0]
    ipp = ipv4(protocol=ipv4.ICMP_PROTOCOL, srcip=access_link.host.interfaces[0].ips[0], dstip=dst_ip_addr)
    if ping_or_pong == "ping":
      ping = icmp(type=TYPE_ECHO_REQUEST, payload=ping_or_pong)
    else:
      ping = icmp(type=TYPE_ECHO_REPLY, payload=ping_or_pong)
    ipp.payload = ping 
    eth.payload = ipp
    packet_events.append(DataplaneEvent(access_link.host.name, access_link.interface, eth))
    
  # ping ping (no responses) between fake hosts
  for _ in range(40):
    trace.append(packet_events[0])
    trace.append(packet_events[1])
    
  write_trace_log(trace, "traces/ping_pong.trace")
  
def generate_example_trace_same_subnet():
  # TODO: highly redundant
  trace = []
  
  (patch_panel, switches, network_links, hosts, access_links) = topo_gen.create_mesh(num_switches=2)
  
  packet_events = []
  ping_or_pong = "ping"
  for access_link in access_links:
    other_host = (set(hosts) - set([access_link.host])).pop()
    eth = ethernet(src=access_link.host.interfaces[0].mac,dst=other_host.interfaces[0].mac,type=ethernet.IP_TYPE)
    dst_ip_addr = other_host.interfaces[0].ips[0]
    ipp = ipv4(protocol=ipv4.ICMP_PROTOCOL, srcip=access_link.host.interfaces[0].ips[0], dstip=dst_ip_addr)
    if ping_or_pong == "ping":
      ping = icmp(type=TYPE_ECHO_REQUEST, payload=ping_or_pong)
    else:
      ping = icmp(type=TYPE_ECHO_REPLY, payload=ping_or_pong)
    ipp.payload = ping 
    eth.payload = ipp
    packet_events.append(DataplaneEvent(access_link.host.name, access_link.interface, eth))
    
  # ping ping (no responses) between fake hosts
  for _ in range(40):
    trace.append(packet_events[0])
    trace.append(packet_events[1])
    
  write_trace_log(trace, "traces/ping_pong_same_subnet.trace")
  
if __name__ == '__main__':
  generate_example_trace()