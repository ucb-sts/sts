# Copyright 2014 Ahmed El-Hassany
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
STS Specific PatchPanel.
"""


from sts.util.console import msg

from sts.entities.sts_entities import Link
from sts.entities.sts_entities import AccessLink

from sts.topology.patch_panel import PatchPanelPolicy
from sts.topology.patch_panel import PatchPanelBK


class STSPatchPanel(PatchPanelBK):
  """
  STS specific implementation of PatchPanel.
  """
  def __init__(self, policy=PatchPanelPolicy(), sts_console=msg):
    super(STSPatchPanel, self).__init__(network_link_factory=Link,
                                        access_link_factory=AccessLink,
                                        policy=policy)
    self.msg = sts_console

  def create_network_link(self, src_switch, src_port, dst_switch, dst_port,
                          bidir=False):
    assert bidir is False, "STS doesn't support bidirectional network links"
    return super(STSPatchPanel, self).create_network_link(src_switch, src_port,
                                                          dst_switch, dst_port,
                                                          bidir=False)

  def sever_network_link(self, link):
    """
    Disconnect link
    """
    self.msg.event("Cutting link %s" % str(link))
    if link not in self.network_links:
      raise ValueError("unknown link %s" % str(link))
    if link in self.cut_network_links:
      raise RuntimeError("link %s already cut!" % str(link))
    self.cut_network_links.add(link)
    link.start_software_switch.take_port_down(link.start_port)
    # TODO(cs): the switch on the other end of the link should eventually
    # notice that the link has gone down!

  def repair_network_link(self, link):
    """Bring a link back online"""
    self.msg.event("Restoring link %s" % str(link))
    if link not in self.network_links:
      raise ValueError("Unknown link %s" % str(link))
    if link not in self.cut_network_links:
      raise RuntimeError("link %s already repaired!" % str(link))
    link.start_software_switch.bring_port_up(link.start_port)
    self.cut_network_links.remove(link)
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
    if link not in self.cut_access_links:
      raise RuntimeError("Access link %s already repaired!" % str(link))
    link.switch.bring_port_up(link.switch_port)
    self.cut_access_links.remove(link)
    # TODO(cs): the host on the other end of the link should eventually
    # notice that the link has come back up!

