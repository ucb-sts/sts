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
TestON Specific PatchPanel.
"""

import re

from sts.util.console import msg

from sts.entities.teston_entities import TestONAccessLink
from sts.entities.teston_entities import TestONNetworkLink

from sts.topology.patch_panel import PatchPanelPolicy
from sts.topology.patch_panel import PatchPanelBK


class TestONPatchPanel(PatchPanelBK):
  """
  STS specific implementation of PatchPanel.
  """
  def __init__(self, teston_mn, hosts_manager, switches_manager):
    policy = PatchPanelPolicy(
      can_create_access_link=False, can_add_access_link=True,
      can_remove_access_link=False, can_create_network_link=False,
      can_add_network_link=True, can_remove_network_link=False)
    super(TestONPatchPanel, self).__init__(network_link_factory=None,
                                        access_link_factory=None,
                                        policy=policy)
    self.teston_mn = teston_mn
    self._switches_manager = switches_manager
    self._hosts_manager = hosts_manager
    self._read_links()
    self.msg = msg
    self.policy.can_add_access_links = False
    self.policy.can_add_network_links = False

  def _read_links(self):
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

      if (not self._hosts_manager.has_host(src_node) and
            not self._switches_manager.has_switch(src_node)):
        raise RuntimeError("Unknown src node for link %s" % line)
      src_node = self._hosts_manager.get_host(src_node) or\
                 self._switches_manager.get_switch(src_node)
      for port_pair in line[line.index(" ")+1:].split(" "):
        port_pair = port_pair.strip()
        # Skip loop back interfaces in switches
        if port_pair.startswith("lo:") or port_pair == '':
          continue
        src_port, dst_port = port_pair.split(":")
        dst_node = dst_port.split("-")[0]
        dst_node = self._hosts_manager.get_host(dst_node) or\
                   self._switches_manager.get_switch(dst_node)
        if self._hosts_manager.has_host(src_node):
          src_port = [i for i in src_node.interfaces if i.name == src_port][0]
          dst_port = dst_port.strip()
          dst_port = [i for i in dst_node.ports.values() if i.name == dst_port][0]
          if not self.is_port_connected(src_port):
            access_link = TestONAccessLink(host=src_node, interface=src_port,
                                            switch=dst_node,
                                            switch_port=dst_port)
            self.add_access_link(access_link)
        elif self._switches_manager.has_switch(src_node) and\
            self._switches_manager.has_switch(dst_node):
          src_port = [i for i in src_node.ports.values() if i.name == src_port][0]
          dst_port = [i for i in dst_node.ports.values() if i.name == dst_port][0]
          if not self.is_port_connected(src_port):
            link = TestONNetworkLink(src_node, src_port, dst_node, dst_port)
            self.add_network_link(link)

  def create_network_link(self, src_switch, src_port, dst_switch, dst_port,
                          bidir=False):
    assert self.policy.can_create_network_link
    raise NotImplementedError()

  def sever_network_link(self, link):
    """
    Disconnect link
    """
    assert self.policy.can_sever_network_link
    self.msg.event("Cutting link %s" % str(link))
    if link not in self.network_links:
      raise ValueError("unknown link %s" % str(link))
    if link in self.cut_network_links:
      raise RuntimeError("link %s already cut!" % str(link))
    self.cut_network_links.add(link)
    self.teston_mn.link(END1=link.node1, END2=link.node2, OPTION='down')

  def repair_network_link(self, link):
    """Bring a link back online"""
    assert self.policy.can_repair_network_link
    self.msg.event("Restoring link %s" % str(link))
    if link not in self.network_links:
      raise ValueError("Unknown link %s" % str(link))
    if link not in self.cut_network_links:
      raise RuntimeError("link %s already repaired!" % str(link))
    self.teston_mn.link(END1=link.node1, END2=link.node2, OPTION='up')
    self.cut_network_links.remove(link)

  def sever_access_link(self, link):
    """
    Disconnect host-switch link
    """
    assert self.policy.can_sever_access_link
    self.msg.event("Cutting access link %s" % str(link))
    if link not in self.access_links:
      raise ValueError("unknown access link %s" % str(link))
    if link in self.cut_access_links:
      raise RuntimeError("Access link %s already cut!" % str(link))
    self.cut_access_links.add(link)
    self.teston_mn.link(END1=link.node1, END2=link.node2, OPTION='down')

  def repair_access_link(self, link):
    """Bring a link back online"""
    assert self.policy.can_repair_access_link
    self.msg.event("Restoring access link %s" % str(link))
    if link not in self.access_links:
      raise ValueError("Unknown access link %s" % str(link))
    if link not in self.cut_access_links:
      raise RuntimeError("Access link %s already repaired!" % str(link))
    self.teston_mn.link(END1=link.node1, END2=link.node2, OPTION='up')
    self.cut_access_links.remove(link)
