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

'''
Created on Mar 15, 2012

@author: cs
'''

from pox.lib.packet.ethernet import *
from pox.lib.packet.ipv4 import *
from pox.lib.packet.icmp import *
from pox.lib.packet.arp import *
import sts.topology as topo
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
  hosts = mesh.hosts
  access_links = mesh.access_links

  packet_events = []
  ping_or_pong = "ping"

  for access_link in access_links:
    other_host = (set(hosts) - set([access_link.host])).pop()
    eth = ethernet(src=access_link.host.interfaces[0].hw_addr,dst=access_link.switch_port.hw_addr,type=ethernet.IP_TYPE)
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

  write_trace_log(trace, "dataplane_traces/ping_pong.trace")

def generate_example_trace_same_subnet(num_switches=2):
  # TODO(cs): highly redundant
  trace = []

  mesh = topo.MeshTopology(num_switches=num_switches)
  hosts = mesh.hosts
  access_links = mesh.access_links

  arp_events = []
  ping_events = []
  ping_or_pong = "ping"

  for access_link in access_links:
    def make_ping(other_host):
      eth = ethernet(src=access_link.host.interfaces[0].hw_addr,dst=other_host.interfaces[0].hw_addr,type=ethernet.IP_TYPE)
      dst_ip_addr = other_host.interfaces[0].ips[0]
      ipp = ipv4(protocol=ipv4.ICMP_PROTOCOL, srcip=access_link.host.interfaces[0].ips[0], dstip=dst_ip_addr)
      if ping_or_pong == "ping":
        ping = icmp(type=TYPE_ECHO_REQUEST, payload=ping_or_pong)
      else:
        ping = icmp(type=TYPE_ECHO_REPLY, payload=ping_or_pong)
      ipp.payload = ping
      eth.payload = ipp
      return eth

    def make_arp_request(other_host):
      src_addr = access_link.host.interfaces[0].hw_addr
      eth = ethernet(src=src_addr,
                     dst=EthAddr('ff:ff:ff:ff:ff:ff'),type=ethernet.ARP_TYPE)
      a = arp(opcode=arp.REQUEST,hwsrc=src_addr,
                hwdst=EthAddr('00:00:00:00:00:00'),
                protosrc=access_link.host.interfaces[0].ips[0],
                protodst=other_host.interfaces[0].ips[0])
      eth.payload = a
      return eth

    def make_arp_reply(other_host):
      dst_addr = access_link.host.interfaces[0].hw_addr
      src_addr = other_host.interfaces[0].hw_addr
      eth = ethernet(src=src_addr,
                     dst=dst_addr,type=ethernet.ARP_TYPE)
      a = arp(opcode=arp.REPLY,hwsrc=src_addr,
                hwdst=dst_addr,
                protosrc=other_host.interfaces[0].ips[0],
                protodst=access_link.host.interfaces[0].ips[0])
      eth.payload = a
      return eth

    other_host = (set(hosts) - set([access_link.host])).pop()
    eth = make_ping(other_host)
    ping_events.append(DataplaneEvent(access_link.interface, eth))
    arp_request = make_arp_request(other_host)
    arp_reply = make_arp_reply(other_host)
    arp_events.append(DataplaneEvent(access_link.interface, arp_request))
    arp_events.append(DataplaneEvent(other_host.interfaces[0], arp_reply))
    if ping_or_pong == "ping":
      ping_or_pong = "pong"
    else:
      ping_or_pong = "ping"

  # ping pong between fake hosts
  for _ in range(40):
    trace.append(arp_events[0])
    trace.append(arp_events[1])
    trace.append(ping_events[0])
    trace.append(ping_events[1])

  write_trace_log(trace,
                  "dataplane_traces/ping_pong_same_subnet_%d_switches.trace" % num_switches)

def generate_example_trace_fat_tree(num_pods=4):
  # TODO(cs): highly redundant

  fat_tree = topo.FatTree(num_pods)
  (_, _, hosts, access_links) = (fat_tree.switches,
          fat_tree.network_links, fat_tree.hosts, fat_tree.access_links)

  host2pings = defaultdict(lambda: [])
  payload = "ping"
  for access_link in access_links:
    host = access_link.host
    other_hosts = list((set(hosts) - set([access_link.host])))
    for other_host in other_hosts:
      eth = ethernet(src=access_link.host.interfaces[0].hw_addr,dst=other_host.interfaces[0].hw_addr,type=ethernet.IP_TYPE)
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

  write_trace_log(trace, "dataplane_traces/ping_pong_fat_tree.trace")

if __name__ == '__main__':
  generate_example_trace_same_subnet()
