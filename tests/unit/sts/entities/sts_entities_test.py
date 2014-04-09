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

from pox.lib.addresses import EthAddr
from pox.lib.addresses import IPAddr
from pox.openflow.libopenflow_01 import ofp_phy_port

from sts.entities.sts_entities import AccessLink
from sts.entities.sts_entities import Link
from sts.entities.hosts import Host
from sts.entities.hosts import HostInterface


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

  def test_to_json(self):
    # Arrange
    sw1 = mock.Mock()
    sw1.dpid = 1
    sw1.to_json.return_value = 1
    sw2 = mock.Mock()
    sw2.dpid = 2
    sw2.to_json.return_value = 2
    # It's really hard to mock this, because of using assert_type
    p1 = ofp_phy_port(port_no=1)
    p2 = ofp_phy_port(port_no=2)
    sw1.ports = [p1]
    sw2.ports = [p2]
    link = Link(sw1, p1, sw2, p2)
    # Act
    json_dict = link.to_json()
    # Assert
    self.assertEquals(json_dict['start_node'], 1)
    self.assertEquals(json_dict['start_port']['port_no'], 1)
    self.assertEquals(json_dict['end_node'], 2)
    self.assertEquals(json_dict['end_port']['port_no'], 2)


  def test_from_json(self):
    # Arrange
    sw1 = mock.Mock()
    sw1.dpid = 1
    sw1.to_json.return_value = 1
    sw2 = mock.Mock()
    sw2.dpid = 2
    sw2.to_json.return_value = 2
    # It's really hard to mock this, because of using assert_type
    p1 = ofp_phy_port(port_no=1)
    p2 = ofp_phy_port(port_no=2)
    sw1.ports = [p1]
    sw2.ports = [p2]
    json_dict = {'start_port': {'hw_addr': '00:00:00:00:00:00',
                                'curr': 0, 'name': '',
                                'supported': 0,
                                '__type__': 'pox.openflow.libopenflow_01.ofp_phy_port',
                                'state': 0, 'advertised': 0, 'peer': 0,
                                'config': 0, 'port_no': 1},
                 'start_node': 1,
                 'end_port': {'hw_addr': '00:00:00:00:00:00', 'curr': 0,
                              'name': '', 'supported': 0,
                              '__type__': 'pox.openflow.libopenflow_01.ofp_phy_port',
                              'state': 0, 'advertised': 0, 'peer': 0,
                              'config': 0, 'port_no': 2},
                 '__type__': 'sts.entities.sts_entities.Link',
                 'end_node': 2}
    # Act
    link = Link.from_json(json_dict)
    # Assert
    self.assertEquals(link.start_node, json_dict['start_node'])
    self.assertEquals(link.start_port.port_no, json_dict['start_port']['port_no'])
    self.assertEquals(link.end_node, json_dict['end_node'])
    self.assertEquals(link.end_port.port_no, json_dict['end_port']['port_no'])


class AccessLinkTest(unittest.TestCase):
  @mock.patch('sts.entities.sts_entities.FuzzSoftwareSwitch')
  def test_init(self, SwitchCls):
    # Arrange
    sw1 = SwitchCls()
    sw1.dpid = 1
    # It's really hard to mock this, because of using assert_type
    p1 = ofp_phy_port(port_no=1)
    hw_addr_str = "11:22:33:44:55:66"
    hw_addr = EthAddr(hw_addr_str)
    ip_str = "127.0.0.1"
    ip = IPAddr(ip_str)
    ifname = "eth0"
    interface = HostInterface(hw_addr, ip, name=ifname)
    hname = "h1"
    hid = 1
    host = Host(interface, name=hname, hid=hid)
    # Act
    link = AccessLink(host, interface, sw1, p1)
    # Assert
    self.assertEquals(link.host, host)
    self.assertEquals(link.interface, interface)

  @mock.patch('sts.entities.sts_entities.FuzzSoftwareSwitch')
  def test_to_jsont(self, SwitchCls):
    # Arrange
    sw1 = SwitchCls()
    sw1.dpid = 1
    sw1.to_json.return_value = 1
    # It's really hard to mock this, because of using assert_type
    p1 = ofp_phy_port(port_no=1)
    hw_addr_str = "11:22:33:44:55:66"
    hw_addr = EthAddr(hw_addr_str)
    ip_str = "127.0.0.1"
    ip = IPAddr(ip_str)
    ifname = "eth0"
    interface = HostInterface(hw_addr, ip, name=ifname)
    hname = "h1"
    hid = 1
    host = Host(interface, name=hname, hid=hid)
    link = AccessLink(host, interface, sw1, p1)
    # Act
    json_dict = link.to_json()
    # Assert
    self.assertEquals(json_dict['node1'], host.to_json())
    self.assertEquals(json_dict['port1'], interface.to_json())
    self.assertEquals(json_dict['node2'], 1)
    self.assertEquals(json_dict['port2'], p1.to_json())

  @mock.patch('sts.entities.sts_entities.FuzzSoftwareSwitch')
  def test_to_jsont(self, SwitchCls):
    # Arrange
    json_dict = {
      "node1": {
        "hid": 1,
        "interfaces": [
          {
            "hw_addr": "11:22:33:44:55:66",
            "ips": [
              "127.0.0.1"
            ],
            "__type__": "sts.entities.hosts.HostInterface",
            "name": "eth0"
          }
        ],
        "__type__": "sts.entities.hosts.Host",
        "name": "h1"
      },
      "port2": {
        "hw_addr": "00:00:00:00:00:00",
        "curr": 0,
        "name": "",
        "supported": 0,
        "__type__": "pox.openflow.libopenflow_01.ofp_phy_port",
        "state": 0,
        "advertised": 0,
        "peer": 0,
        "config": 0,
        "port_no": 1
      },
      "node2": 1,
      "__type__": "sts.entities.sts_entities.AccessLink",
      "port1": {
        "hw_addr": "11:22:33:44:55:66",
        "ips": [
          "127.0.0.1"
        ],
        "__type__": "sts.entities.hosts.HostInterface",
        "name": "eth0"
      }
    }

    sw1 = SwitchCls()
    sw1.dpid = 1
    sw1.to_json.return_value = 1
    # It's really hard to mock this, because of using assert_type
    p1 = ofp_phy_port(port_no=1)
    hw_addr_str = "11:22:33:44:55:66"
    hw_addr = EthAddr(hw_addr_str)
    ip_str = "127.0.0.1"
    ip = IPAddr(ip_str)
    ifname = "eth0"
    interface = HostInterface(hw_addr, ip, name=ifname)
    hname = "h1"
    hid = 1
    host = Host(interface, name=hname, hid=hid)
    # Act
    link = AccessLink.from_json(json_dict)
    # Assert
    self.assertEquals(link.host.to_json(), host.to_json())
    self.assertEquals(link.interface.to_json(), interface.to_json())
    self.assertEquals(link.switch, 1)
    self.assertEquals(link.switch_port.to_json(), p1.to_json())
