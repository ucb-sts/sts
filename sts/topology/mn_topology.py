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


import re

from sts.topology.base import Topology
from sts.topology.base import PatchPanel

from sts.entities.mn_entities import MininetHost
from sts.entities.mn_entities import MininetHostInterface
from sts.entities.mn_entities import MininetAccessLink
from sts.entities.mn_entities import MininetLink
from sts.entities.mn_entities import MininetPort
from sts.entities.mn_entities import MininetOVSSwitch

from sts.util.console import msg


class MininetPatchPanel(PatchPanel):
  def __init__(self):
    super(MininetPatchPanel, self).__init__(link_cls=MininetLink,
                                            access_link_cls=MininetAccessLink,
                                            port_cls=MininetPort,
                                            host_interface_cls=MininetHostInterface,
                                            sts_console=msg)
  def sever_link(self, link):
    """
    Disconnect link
    """
    self.msg.event("Cutting link %s" % str(link))
    if link not in self.network_links:
      raise ValueError("unknown link %s" % str(link))
    if link in self.cut_links:
      raise RuntimeError("link %s already cut!" % str(link))
    self.cut_links.add(link)
    link.start_software_switch.take_port_down(link.start_port)
    # TODO(cs): the switch on the other end of the link should eventually
    # notice that the link has gone down!

  def repair_link(self, link):
    """Bring a link back online"""
    self.msg.event("Restoring link %s" % str(link))
    if link not in self.network_links:
      raise ValueError("Unknown link %s" % str(link))
    link.start_software_switch.bring_port_up(link.start_port)
    self.cut_links.remove(link)
    # TODO(cs): the switch on the other end of the link should eventually
    # notice that the link has come back up!

  def sever_access_link(self, link):
    """
    Disconnect host-switch link
    """
    self.msg.event("Cutting access link %s" % str(link))
    if link not in self.access_links:
      raise ValueError("unknown access link %s" % str(link))
    if link in self.cut_access_links:
      raise RuntimeError("Access link %s already cut!" % str(link))
    self.cut_access_links.add(link)
    link.switch.take_port_down(link.switch_port)
    # TODO(cs): the host on the other end of the link should eventually
    # notice that the link has gone down!

  def repair_access_link(self, link):
    """Bring a link back online"""

    self.msg.event("Restoring access link %s" % str(link))
    if link not in self.access_links:
      raise ValueError("Unknown access link %s" % str(link))
    link.switch.bring_port_up(link.switch_port)
    self.cut_access_links.remove(link)
    # TODO(cs): the host on the other end of the link should eventually
    # notice that the link has come back up!


class MininetTopology(Topology):
  def __init__(self, teston_mn):
    super(MininetTopology, self).__init__(patch_panel=MininetPatchPanel(),
                                          host_cls=MininetHost,
                                          interface_cls=MininetHostInterface,
                                          switch_cls=MininetOVSSwitch,
                                          access_link_cls=MininetAccessLink,
                                          link_cls=MininetLink
                                          )
    self.teston_mn = teston_mn
    self.read_nodes()
    self.read_links()

  def read_nodes(self):
    """
    Read nodes (switches and hosts) from Mininet.
    """
    # Regex patterns to parse dump output
    # Example host: <Host h1: h1-eth0:10.0.0.1 pid=5227>
    host_re = r"<Host\s(?P<name>[^:]+)\:\s(?P<ifname>[^:]+)\:(?P<ip>[^\s]+)"
    # Example Switch:
    # <OVSSwitch s1: lo:127.0.0.1,s1-eth1:None,s1-eth2:None,s1-eth3:None pid=5238>
    sw_re = r"<OVSSwitch\s(?P<name>[^:]+)\:\s(?P<ports>([^,]+,)*[^,\s]+)"
    # Get mininet dump
    dump = self.teston_mn.dump().split("\n")
    for line in dump:
      if line.startswith("<Host"):
        result = re.search(host_re, line)
        host_name = result.group('name')
        if_name = result.group('ifname')
        ip = self.teston_mn.getIPAddress(host_name)
        mac = self.teston_mn.getMacAddress(host_name)
        interface = MininetHostInterface(mac, ip, if_name)
        # TODO: read Host ID
        host = self.host_cls(interface, name=host_name)
        self.add_host(host)
      if line.startswith("<OVSSwitch"):
        result = re.search(sw_re, line, re.I)
        name = result.group('name')
        dpid = self.teston_mn.getSwitchDPID(name)
        str_ports = result.group('ports').split(',')
        ports = []
        for str_port in str_ports:
          port_name, port_ip = str_port.split(":")
          if port_ip == "None":
            port_ip = None
          else:
            continue
          port = MininetPort(
            hw_addr=self.teston_mn.getMacInterfaceAddress(name, port_name),
            name=port_name)
          ports.append(port)
        sw = self.switch_cls(dpid, name, ports)
        self.add_switch(sw)

  def has_node(self, node):
    """
    Check if node exists regardless of its type
    """
    return self.has_host(node) or self.has_switch(node)

  def get_node(self, node):
    """
    Get node regardless of its type
    """
    assert self.has_node(node)
    if self.has_host(node):
      return self.get_host(node)
    else:
     return self.get_switch(node)

  def read_links(self):
    """
    Read links in Mininet (assume nodes already be read before)
    """
    # used to valid link line
    link_re = r"([^\:\s]+)\s([^\:]+)\:([^\:\s]+)"
    net = self.teston_mn.net().split("\n")
    for line in net:
      line = line.strip()
      if re.search(link_re, line) is None:
        continue
      src_node = line[:line.index(" ")]
      if not self.has_node(src_node):
        raise RuntimeError("Unknown src node for link %s" % line)
      src_node = self.get_node(src_node)
      for port_pair in line[line.index(" ")+1:].split(" "):
        port_pair = port_pair.strip()
        # Skip loop back interfaces in switches
        if port_pair.startswith("lo:") or port_pair == '':
          continue
        src_port, dst_port = port_pair.split(":")
        dst_node = dst_port.split("-")[0]
        dst_node = self.get_node(dst_node)
        if isinstance(src_node, self.host_cls):
          src_port = [i for i in src_node.interfaces if i.name == src_port][0]
          dst_port = dst_port.strip()
          dst_port = [i for i in dst_node.ports if i.name == dst_port][0]
          if not self.patch_panel.is_port_connected(src_port):
            access_link = self.access_link_cls(host=src_node,
                                               interface=src_port,
                                               switch=dst_node,
                                               switch_port=dst_port)
            self.add_link(access_link)
        elif isinstance(src_node, self.switch_cls) and\
            isinstance(dst_node, self.switch_cls):
          src_port = [i for i in src_node.ports if i.name == src_port][0]
          dst_port = [i for i in dst_node.ports if i.name == dst_port][0]
          if not self.patch_panel.is_port_connected(src_port):
            link = self.link_cls(src_node, src_port, dst_node, dst_port)
            self.add_link(link)