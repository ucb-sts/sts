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

from sts.entities.base import HostAbstractClass
from sts.entities.base import HostInterfaceAbstractClass


class HostAbstractClassTest(unittest.TestCase):

  def get_concrete_impl(self):
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
    host_cls = self.get_concrete_impl()
    h = host_cls(interfaces=interfaces, name=name, hid=hid)
    self.assertEquals(interfaces, h.interfaces)
    self.assertEquals(name, h.name)
    self.assertEquals(hid, h.hid)
    self.assertTrue(h.has_port(interfaces[0]))
    self.assertFalse(h.has_port("fake_interface"))


class HostInterfaceAbstractClassTest(unittest.TestCase):

  def get_concrete_impl(self):
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
    iface_cls = self.get_concrete_impl()
    iface = iface_cls(hw_addr, ip, name)
    self.assertEquals(hw_addr, iface.hw_addr)
    self.assertEquals(ips, iface.ips)
    self.assertEquals(name, iface.name)
    self.assertTrue(iface.__hash__())


if __name__ == '__main__':
  unittest.main()
