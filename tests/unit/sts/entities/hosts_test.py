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
    expected = {'name': name,
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
    input_json = {'name': name,
                'ips': [ip],
                'hw_addr': hw_addr_str}
    # Act
    interface = HostInterface.from_json(input_json)
    # Assert
    self.assertEquals(interface.hw_addr, hw_addr)
    self.assertEquals(interface.ips, [ip])
    self.assertEquals(interface.name, name)


class HostTest(unittest.TestCase):
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

  def test_receive(self):
    pass
    # TODO (AH): I'm still not sure about how receive works


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
