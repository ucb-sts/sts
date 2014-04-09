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


import mock
import unittest

from pox.lib.addresses import EthAddr
from pox.lib.addresses import IPAddr
from pox.lib.packet.ethernet import ethernet
from pox.lib.packet.arp import arp

from sts.entities.hosts import HostAbstractClass
from sts.entities.hosts import HostInterfaceAbstractClass
from sts.entities.hosts import HostInterface
from sts.entities.hosts import Host
from sts.entities.hosts import NamespaceHost


class HostAbstractClassTest(unittest.TestCase):

  def get_concrete_class(self):
    """Simple mock for the abstract methods and properties"""
    class HostTestImpl(HostAbstractClass):
      def send(self, interface, packet):
        return True
      def receive(self, interface, packet):
        return True
    return HostTestImpl

  def test_init(self):
    interfaces = ["eth1"]
    name = 'Host1'
    hid = 1
    host_cls = self.get_concrete_class()
    h = host_cls(interfaces=interfaces, name=name, hid=hid)
    self.assertEquals(interfaces, h.interfaces)
    self.assertEquals(name, h.name)
    self.assertEquals(hid, h.hid)
    self.assertTrue(h.has_port(interfaces[0]))
    self.assertFalse(h.has_port("fake_interface"))


class HostInterfaceAbstractClassTest(unittest.TestCase):

  def get_concrete_class(self):
    """Simple mock for the abstract methods and properties"""
    class HostInterfaceTestImpl(HostInterfaceAbstractClass):
      @property
      def port_no(self):
        return 1

      @property
      def _hw_addr_hash(self):
        return self.hw_addr.__hash__()

      @property
      def _ips_hashes(self):
        return [ip.__hash__() for ip in self.ips]

    return HostInterfaceTestImpl

  def test_init(self):
    hw_addr = 'ff:ee:dd:cc:bb:aa'
    ip = '192.168.56.1'
    ips = [ip]
    name = "eth0"
    iface_cls = self.get_concrete_class()
    iface = iface_cls(hw_addr, ip, name)
    self.assertEquals(hw_addr, iface.hw_addr)
    self.assertEquals(ips, iface.ips)
    self.assertEquals(name, iface.name)
    self.assertTrue(iface.__hash__())


class HostInterfaceTest(unittest.TestCase):
  def test_init(self):
    # Arrange
    hw_addr_str = "11:22:33:44:55:66"
    hw_addr = EthAddr(hw_addr_str)
    ip_str = "127.0.0.1"
    ip = IPAddr(ip_str)
    name = "eth0"
    # Act
    interface = HostInterface(hw_addr, ip, name=name)
    # Assert
    self.assertEquals(interface.hw_addr, hw_addr)
    self.assertEquals(interface.ips, [ip])
    self.assertEquals(interface.name, name)

  def test_eq(self):
    # Arrange
    hw_addr_str = "11:22:33:44:55:66"
    hw_addr_str2 = "66:55:44:33:22:11"
    hw_addr = EthAddr(hw_addr_str)
    hw_addr2 = EthAddr(hw_addr_str2)
    ip_str = "127.0.0.1"
    ip = IPAddr(ip_str)
    name = "eth0"
    # Act
    interface1 = HostInterface(hw_addr, ip, name=name)
    interface2 = HostInterface(hw_addr, ip, name=name)
    interface3 = HostInterface(hw_addr2, ip, name=name)
    # Assert
    self.assertEquals(interface1, interface2)
    self.assertNotEquals(interface1, interface3)

  def test_to_json(self):
    # Arrange
    hw_addr_str = "11:22:33:44:55:66"
    hw_addr = EthAddr(hw_addr_str)
    ip_str = "127.0.0.1"
    ip = IPAddr(ip_str)
    name = "eth0"
    expected = {'__type__': 'sts.entities.hosts.HostInterface',
                'name': name,
                'ips': [ip],
                'hw_addr': hw_addr_str}
    # Act
    interface = HostInterface(hw_addr, ip, name=name)
    json_str = interface.to_json()
    # Assert
    self.assertEquals(json_str, expected)

  def test_from_json(self):
    # Arrange
    hw_addr_str = "11:22:33:44:55:66"
    hw_addr = EthAddr(hw_addr_str)
    ip_str = "127.0.0.1"
    ip = IPAddr(ip_str)
    name = "eth0"
    input_json = {'__type__': 'sts.entities.hosts.HostInterface',
                  'name': name,
                  'ips': [ip],
                  'hw_addr': hw_addr_str}
    # Act
    interface = HostInterface.from_json(input_json)
    # Assert
    self.assertEquals(interface.hw_addr, hw_addr)
    self.assertEquals(interface.ips, [ip])
    self.assertEquals(interface.name, name)


class HostTest(unittest.TestCase):

  def setUp(self):
    # IP and MAC of requester host 1
    self.H1_I1_IP = '1.1.1.1'
    self.H1_I1_ETH = '\x01\x01\x01\x01\x01\x01'

    # IP and MAC of receiver host 2, Interface 1
    self.H2_I1_IP1 = '2.2.1.1'
    self.H2_I1_ETH = '\x02\x02\x02\x02\x01\x01'
    # Additional IP on the Interface 1
    self.H2_I1_IP2 = '2.2.1.2'

    # IP and MAC of receiver host 2, Interface 2
    self.H2_I2_IP = '2.2.2.1'
    self.H2_I2_ETH = '\x02\x02\x02\x02\x02\x01'

    # IP and MAC of receiver host 3
    self.H3_I3_IP = '3.3.3.1'
    self.H3_I3_ETH = '\x03\x03\x03\x03\x03\x01'

  def test_init(self):
    # Arrange
    interfaces = [mock.Mock()]
    name = "test-host"
    hid = 123
    # Act
    host = Host(interfaces, name, hid)
    # Assert
    self.assertEquals(host.interfaces, interfaces)
    self.assertEquals(host.name, name)
    self.assertEquals(host.hid, hid)

  def test_send(self):
    # Arrange
    interfaces = [mock.Mock()]
    name = "test-host"
    hid = 123
    Host.raiseEvent = mock.Mock(name="mock_interface")
    pkt = ethernet()
    # Act
    host = Host(interfaces, name, hid)
    host.send(interfaces[0], pkt)
    # Assert
    self.assertEquals(Host.raiseEvent.call_count, 1)

  def test_none_arp(self):
    """Receive a non-ARP packet and ensure there is no reply"""
    # Arrange
    iface1 = HostInterface(EthAddr(self.H2_I1_ETH),
                           [IPAddr(self.H2_I1_IP1), IPAddr(self.H2_I1_IP2)])
    iface2 = HostInterface(EthAddr(self.H2_I2_ETH), [IPAddr(self.H2_I2_IP)])
    interfaces = [iface1, iface2]
    h = Host(interfaces)
    ether = ethernet()
    ether.type = ethernet.IP_TYPE
    ether.dst = EthAddr(self.H2_I1_ETH)
    ether.src = EthAddr(self.H1_I1_ETH)
    # Act
    # Get the action and reply packet
    reply_packet = h.receive(interfaces[0], ether)
    # Assert
    self.assertIsNone(reply_packet)

  def test_invalid_arp(self):
    """Receive a ARP packet that isn't desinated to it and ensure there is no reply"""
    # Arrange
    iface1 = HostInterface(EthAddr(self.H2_I1_ETH),
                           [IPAddr(self.H2_I1_IP1), IPAddr(self.H2_I1_IP2)])
    iface2 = HostInterface(EthAddr(self.H2_I2_ETH), [IPAddr(self.H2_I2_IP)])
    interfaces = [iface1, iface2]
    h = Host(interfaces)
    arp_req = arp()
    arp_req.hwsrc = EthAddr(self.H1_I1_ETH)
    arp_req.hwdst = EthAddr(b"\xff\xff\xff\xff\xff\xff")
    arp_req.opcode = arp.REQUEST
    arp_req.protosrc = IPAddr(self.H1_I1_IP)
    arp_req.protodst = IPAddr(self.H3_I3_IP)
    ether = ethernet()
    ether.type = ethernet.ARP_TYPE
    ether.dst = EthAddr(b"\xff\xff\xff\xff\xff\xff")
    ether.src = EthAddr(self.H1_I1_ETH)
    ether.payload = arp_req
    # Act
    # Get the action and reply packet
    reply_packet = h.receive(interfaces[0], ether)
    # Assert
    self.assertIsNone(reply_packet)

  def test_arp_reply(self):
    """Receive a valid ARP packet and ensure the correct reply"""
    # Arrange
    iface1 = HostInterface(EthAddr(self.H2_I1_ETH),
                           [IPAddr(self.H2_I1_IP1), IPAddr(self.H2_I1_IP2)])
    iface2 = HostInterface(EthAddr(self.H2_I2_ETH), [IPAddr(self.H2_I2_IP)])
    interfaces = [iface1, iface2]
    h = Host(interfaces)
    arp_req = arp()
    arp_req.hwsrc = EthAddr(self.H1_I1_ETH)
    arp_req.hwdst = EthAddr(b"\xff\xff\xff\xff\xff\xff")
    arp_req.opcode = arp.REQUEST
    arp_req.protosrc = IPAddr(self.H1_I1_IP)
    arp_req.protodst = IPAddr(self.H2_I1_IP1)
    ether = ethernet()
    ether.type = ethernet.ARP_TYPE
    ether.dst = EthAddr(b"\xff\xff\xff\xff\xff\xff")
    ether.src = EthAddr(self.H1_I1_ETH)
    ether.payload = arp_req
    # Act
    # Get the action and arp reply packet
    arp_reply = h.receive(interfaces[0], ether)
    # Assert
    self.assertIsNotNone(arp_reply)
    self.assertEquals(arp_reply.src, EthAddr(self.H2_I1_ETH))
    self.assertEquals(arp_reply.dst, EthAddr(self.H1_I1_ETH))
    self.assertEquals(arp_reply.type, ethernet.ARP_TYPE)
    reply_payload = arp_reply.payload
    self.assertEquals(reply_payload.opcode, arp.REPLY)
    self.assertEquals(reply_payload.hwsrc, EthAddr(self.H2_I1_ETH))
    self.assertEquals(reply_payload.hwdst, EthAddr(self.H1_I1_ETH))
    self.assertEquals(reply_payload.protosrc, self.H2_I1_IP1)
    self.assertEquals(reply_payload.protodst, self.H1_I1_IP)

  def test_to_json(self):
    # Arrange
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
    json_dict = host.to_json()
    # Assert
    self.assertEquals(json_dict['name'], hname)
    self.assertEquals(json_dict['hid'], hid)
    self.assertEquals(len(json_dict['interfaces']), 1)
    self.assertEquals(json_dict['interfaces'][0], interface.to_json())

  def test_from_json(self):
    # Arrange
    json_dict = {'hid': 1,
                 '__type__': 'sts.entities.hosts.Host',
                 'name': 'h1',
                 'interfaces': [
                   {'__type__': 'sts.entities.hosts.HostInterface',
                    'name': 'eth0',
                    'hw_addr': '11:22:33:44:55:66',
                    'ips': ['127.0.0.1'],
                    }],
                 }
    hw_addr_str = "11:22:33:44:55:66"
    hw_addr = EthAddr(hw_addr_str)
    ip_str = "127.0.0.1"
    ip = IPAddr(ip_str)
    ifname = "eth0"
    interface = HostInterface(hw_addr, ip, name=ifname)
    hname = "h1"
    hid = 1
    # Act
    host = Host.from_json(json_dict)
    # Assert
    self.assertEquals(host.name, hname)
    self.assertEquals(host.hid, hid)
    self.assertEquals(len(host.interfaces), 1)
    self.assertEquals(host.interfaces[0], interface)


class NamespaceHostTest(unittest.TestCase):
  # TODO (AH): test send and receive

  def test_init(self):
    # Arrange
    name = "test-host"
    hid = 123
    hw_addr_str = "11:22:33:44:55:66"
    ip = "192.168.56.1"
    interfaces = [HostInterface(hw_addr_str, ip)]
    # Mocking external dependencies
    import sts.util.network_namespace as ns
    ns.launch_namespace = mock.Mock(return_value=(None, hw_addr_str, None))
    ns.bind_raw_socket = mock.Mock(return_value=None)

    # Act
    host = NamespaceHost(interfaces, lambda x: mock.Mock(), name=name, hid=hid)

    # Assert
    self.assertEquals(host.interfaces, interfaces)

  def test_to_json(self):
    # Arrange
    io_master = mock.Mock()
    hw_addr_str = "0e:32:a4:91:e7:30"
    ip_str = "192.168.56.2"
    hw_addr = EthAddr(hw_addr_str)
    ip = IPAddr(ip_str)
    ifname = "test-host"
    interface = HostInterface(hw_addr, ip, name=ifname)
    hname = "h1"
    hid = 1
    cmd = '/bin/bash sleep'
    # Mocking external dependencies
    import sts.util.network_namespace as ns
    ns.launch_namespace = mock.Mock(return_value=(None, hw_addr_str, None))
    ns.bind_raw_socket = mock.Mock(return_value=None)
    host = NamespaceHost(interface, io_master.create_worker_for_socket,
                         name=hname, hid=hid, cmd=cmd)
    # Act
    json_dict = host.to_json()
    # Assert
    self.assertEquals(json_dict['name'], hname)
    self.assertEquals(json_dict['hid'], hid)
    self.assertEquals(json_dict['cmd'], cmd)
    self.assertEquals(len(json_dict['interfaces']), 1)
    self.assertEquals(json_dict['interfaces'][0], interface.to_json())

  def test_from_json(self):
    # Arrange
    json_dict = {'__type__': 'sts.entities.hosts.NamespaceHost',
                 'cmd': '/bin/bash sleep',
                 'name': 'h1',
                 'hid': 1,
                 'interfaces': [
                   {'__type__': 'sts.entities.hosts.HostInterface',
                    'hw_addr': '0e:32:a4:91:e7:30',
                    'ips': ['192.168.56.2'],
                    'name': 'test-host'}]}

    io_master = mock.Mock()
    hw_addr_str = "0e:32:a4:91:e7:30"
    ip_str = "192.168.56.2"
    hw_addr = EthAddr(hw_addr_str)
    ip = IPAddr(ip_str)
    ifname = "test-host"
    interface = HostInterface(hw_addr, ip, name=ifname)
    hname = "h1"
    hid = 1
    cmd = '/bin/bash sleep'
    # Mocking external dependencies
    import sts.util.network_namespace as ns
    ns.launch_namespace = mock.Mock(return_value=(None, hw_addr_str, None))
    ns.bind_raw_socket = mock.Mock(return_value=None)
    # Act
    host = NamespaceHost.from_json(json_dict, io_master.create_worker_for_socket)
    # Assert
    self.assertEquals(host.name, hname)
    self.assertEquals(host.hid, hid)
    self.assertEquals(host.cmd, cmd)
    self.assertEquals(len(host.interfaces), 1)
    self.assertEquals(host.interfaces[0].to_json(), interface.to_json())
