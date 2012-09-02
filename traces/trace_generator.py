'''
Created on Mar 15, 2012

@author: cs
'''

from pox.lib.packet.ethernet import *
from pox.lib.packet.ipv4 import *
from pox.lib.packet.icmp import *
import sts.topology as topo
from sts.entities import HostInterface
from collections import defaultdict
import pickle
from trace import DataplaneEvent

def write_trace_log(dataplane_events, filename):
  '''
  Given a list of DataplaneEvents and a log filename, writes out a log.
  For manual trace generation rather than replay logging
  '''
  pickle.dump(dataplane_events, file(filename, "w"))

def generate_example_trace():
  trace = []

  mesh = topo.MeshTopology(num_switches=2)
  switches = mesh.switches
  network_links = mesh.network_links
  hosts = mesh.hosts
  access_links = mesh.access_links

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
    packet_events.append(DataplaneEvent(access_link.interface, eth))

  # ping ping (no responses) between fake hosts
  for _ in range(40):
    trace.append(packet_events[0])
    trace.append(packet_events[1])

  write_trace_log(trace, "traces/ping_pong.trace")

def generate_example_trace_same_subnet():
  # TODO(cs): highly redundant
  trace = []

  mesh = topo.MeshTopology(num_switches=2)
  switches = mesh.switches
  network_links = mesh.network_links
  hosts = mesh.hosts
  access_links = mesh.access_links

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
    packet_events.append(DataplaneEvent(access_link.interface, eth))

  # ping ping (no responses) between fake hosts
  for _ in range(40):
    trace.append(packet_events[0])
    trace.append(packet_events[1])

  write_trace_log(trace, "traces/ping_pong_same_subnet.trace")

def generate_example_trace_fat_tree(num_pods=4):
  # TODO(cs): highly redundant

  fat_tree = topo.FatTree(num_pods)
  patch_panel = topo.BufferedPatchPanel(fat_tree.switches, fat_tree.hosts, fat_tree.get_connected_port)
  (switches, network_links, hosts, access_links) = (fat_tree.switches,
          fat_tree.network_links, fat_tree.hosts, fat_tree.access_links)

  host2pings = defaultdict(lambda: [])
  payload = "ping"
  for access_link in access_links:
    host = access_link.host
    other_hosts = list((set(hosts) - set([access_link.host])))
    for other_host in other_hosts:
      eth = ethernet(src=access_link.host.interfaces[0].mac,dst=other_host.interfaces[0].mac,type=ethernet.IP_TYPE)
      dst_ip_addr = other_host.interfaces[0].ips[0]
      ipp = ipv4(protocol=ipv4.ICMP_PROTOCOL, srcip=access_link.host.interfaces[0].ips[0], dstip=dst_ip_addr)
      ping = icmp(type=TYPE_ECHO_REQUEST, payload=payload)
      ipp.payload = ping
      eth.payload = ipp
      host2pings[host].append(DataplaneEvent(access_link.interface, eth))

  # ping pong (no responses) between fake hosts
  # (Some large number: TODO(cs): serialize a generator to disk)
  # Trace is [one ping from every host to a random other host] * 50000
  trace = []
  for _ in range(50000):
    for host, pings in host2pings.iteritems():
      trace.append(random.choice(pings))

  write_trace_log(trace, "traces/ping_pong_fat_tree.trace")

if __name__ == '__main__':
  generate_example_trace_same_subnet()
