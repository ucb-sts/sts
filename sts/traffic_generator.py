# Copyright 2011-2013 Colin Scott
# Copyright 2011-2013 Andreas Wundsam
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


from pox.lib.packet.ethernet import *
from pox.lib.packet.ipv4 import *
from pox.lib.packet.icmp import *
from util.convenience import random_eth_addr, random_ip_addr
from sts.dataplane_traces.trace import DataplaneEvent
import random

class TrafficGenerator (object):
  '''
  Generate sensible randomly generated (openflow) events
  '''
  def __init__(self, random=random.Random()):
    self.random = random
    self.topology = None
    self._packet_generators = {
      "icmp_ping" : self.icmp_ping
    }

  def set_topology(self, topology):
    self.topology = topology

  def icmp_ping(self, src_interface, dst_interface, payload_content=None):
    ''' Return an ICMP ping packet; if an interface is none, random addresses are used '''
    e = ethernet()
    e.src = self._choose_eth_addr(src_interface)
    e.dst = self._choose_eth_addr(dst_interface)
    e.type = ethernet.IP_TYPE
    i = ipv4()
    i.protocol = ipv4.ICMP_PROTOCOL
    i.srcip = self._choose_ip_addr(src_interface)
    i.dstip = self._choose_ip_addr(dst_interface)
    ping = icmp()
    ping.type = random.choice([TYPE_ECHO_REQUEST, TYPE_ECHO_REPLY])
    if payload_content == "" or payload_content is None:
      payload_content = "Ping" * 12
    ping.payload = payload_content
    i.payload = ping
    e.payload = i
    return e

  def generate_and_inject(self, packet_type, src_host=None, dst_host=None,
                          send_to_self=False, payload_content=None):
    ''' Generate a packet, have the source host send it, and return the corresponding event '''
    if packet_type not in self._packet_generators:
      raise AttributeError("Unknown event type %s" % str(packet_type))
    if self.topology is None:
      raise RuntimeError("TrafficGenerator needs access to topology")

    (src_host, src_interface) = self._choose_host(src_host, self.topology.hosts)    
    if send_to_self:
      (dst_host, dst_interface) = (src_host, src_interface)
    else:
      (dst_host, dst_interface) = self._choose_host(dst_host,
                                      [h for h in self.topology.hosts if h != src_host])
      
    packet = self._packet_generators[packet_type](src_interface, dst_interface,
                                                  payload_content=payload_content)
    src_host.send(src_interface, packet)
    return DataplaneEvent(src_interface, packet)

  def _choose_host(self, host, hosts):
    '''
    Validate the existence of a host and its interfaces;
    if host is None, choose randomly from hosts
    '''
    if host is None:
      if len(hosts) == 0:
        raise RuntimeError("No host to choose from!")  
      host = self.random.choice(hosts)
    if host in self.topology.hid2host.keys():
      host = self.topology.hid2host[host]
    if host not in self.topology.hosts:
      raise RuntimeError("Unknown host: %s" % (str(host)))
    if len(host.interfaces) == 0:
      raise RuntimeError("No interfaces to choose from on host %s!" % (str(host)))
    interface = self.random.choice(host.interfaces)
    return (host, interface)

  def _choose_eth_addr(self, interface):
    if interface is not None:
      return interface.hw_addr
    else:
      return random_eth_addr()

  def _choose_ip_addr(self, interface):
    if interface is not None and hasattr(interface, 'ips'):
      return self.random.choice(interface.ips)
    else:
      return random_ip_addr()
  