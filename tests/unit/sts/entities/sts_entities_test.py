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


import unittest
import mock
from pox.openflow.libopenflow_01 import ofp_phy_port

from sts.entities.sts_entities import Link

class LinkTest(unittest.TestCase):
  @mock.patch('sts.entities.sts_entities.FuzzSoftwareSwitch')
  def test_init(self, SwitchCls):
    sw1 = mock.MagicMock()
    sw1.dpid = 1
    sw2 = SwitchCls()
    sw2.dpid = 2
    # It's really hard to mock this, because of using assert_type
    p1 = ofp_phy_port(port_no=1)
    p2 = ofp_phy_port(port_no=2)
    sw1.ports = [p1]
    sw2.ports = [p2]
    link = Link(sw1, p1, sw2, p2)

    self.assertEquals(sw1.dpid, link.start_software_switch.dpid)
    self.assertEquals(sw2.dpid, link.end_software_switch.dpid)
    self.assertEquals(p1, link.start_port)
    self.assertEquals(p2, link.end_port)

  @mock.patch('sts.entities.sts_entities.FuzzSoftwareSwitch')
  def test_eq(self, SwitchCls):
    sw1 = mock.MagicMock()
    sw1.dpid = 1
    sw2 = SwitchCls()
    sw2.dpid = 2
    # It's really hard to mock this, because of using assert_type
    p1 = ofp_phy_port(port_no=1)
    p2 = ofp_phy_port(port_no=2)
    sw1.ports = [p1]
    sw2.ports = [p2]
    link1 = Link(sw1, p1, sw2, p2)
    link2 = Link(sw2, p2, sw1, p1)

    self.assertEquals(link1, link1)
    self.assertNotEquals(link1, link2)

  @mock.patch('sts.entities.sts_entities.FuzzSoftwareSwitch')
  def test_reversed_link(self, SwitchCls):
    sw1 = mock.MagicMock()
    sw1.dpid = 1
    sw2 = SwitchCls()
    sw2.dpid = 2
    # It's really hard to mock this, because of using assert_type
    p1 = ofp_phy_port(port_no=1)
    p2 = ofp_phy_port(port_no=2)
    sw1.ports = [p1]
    sw2.ports = [p2]
    link1 = Link(sw1, p1, sw2, p2)
    link2 = link1.reversed_link()

    self.assertNotEquals(link1, link2)
    self.assertEquals(sw2.dpid, link2.start_software_switch.dpid)
    self.assertEquals(sw1.dpid, link2.end_software_switch.dpid)
    self.assertEquals(p2, link2.start_port)
    self.assertEquals(p1, link2.end_port)
