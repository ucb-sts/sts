# Copyright 2011-2013 Colin Scott
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

'''
Created on Jan 29, 2014

@author: jl
'''

from pox.lib.packet.ethernet import *
from pox.lib.packet.ipv4 import *
from pox.lib.packet.icmp import *
from pox.lib.packet.arp import *
from pox.lib.packet.tcp import *
import sts.topology as topo
from collections import defaultdict
import pickle
from sts.dataplane_traces.trace import DataplaneEvent

import itertools
def write_trace_log(dataplane_events, filename):
  '''
  Given a list of DataplaneEvents and a log filename, writes out a log.
  For manual trace generation rather than replay logging
  '''
  pickle.dump(dataplane_events, file(filename, "w"))

def generate_trace():
  trace = []
  mesh = topo.MeshTopology(num_switches=3)
  port_counter = itertools.count()
  src_host = mesh.hosts[2]
  access_link = mesh.access_links[0]
  assert(access_link.host == src_host)
  dst_host = mesh.hosts[0]
  for i in range(30):
    eth = ethernet(src=src_host.interfaces[0].hw_addr,dst=access_link.switch_port.hw_addr,type=ethernet.IP_TYPE)
    src_ip_addr = src_host.interfaces[0].ips[0]
    dst_ip_addr = dst_host.interfaces[0].ips[0]
    ipp = ipv4(protocol=ipv4.TCP_PROTOCOL, srcip=src_ip_addr, dstip=dst_ip_addr)
    syn = tcp()
    syn.SYN = True
    syn.off = 5
    syn.srcport = next(port_counter)
    syn.dstport = next(port_counter)
    ipp.payload = syn
    eth.payload = ipp
    trace.append(DataplaneEvent(access_link.interface, eth))

  write_trace_log(trace, "load_balancer.trace")

generate_trace()
