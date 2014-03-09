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

from sts.entities.base import HostAbstractClass
from sts.entities.base import HostInterfaceAbstractClass
from sts.entities.base import SSHEntity


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


class SSHEntityTest(unittest.TestCase):

  @mock.patch("paramiko.client.SSHClient")
  def test_init(self, ssh_client_cls):
    # Arrange
    host = "localhost"
    port = 22
    username = None
    password = None
    key_filename = None
    # Act
    ssh = SSHEntity(host, port, username, password, key_filename)
    ssh._ssh_cls = ssh_client_cls
    client = ssh.ssh_client
    # Assert
    self.assertEquals(ssh.host, host)
    self.assertEquals(ssh.port, port)
    self.assertEquals(ssh.username, username)
    self.assertEquals(ssh.password, password)
    self.assertEquals(ssh.key_filename, key_filename)
    self.assertEquals(ssh.key_filename, key_filename)
    self.assertEquals(ssh.ssh_cls, ssh_client_cls)
    self.assertEquals(client.set_missing_host_key_policy.call_count, 1)
    client.connect.assert_called_once_with(hostname=host, port=port,
                                           username=username, password=password,
                                           key_filename=key_filename)

  @mock.patch("paramiko.client.SSHClient")
  def test_get_new_session(self, ssh_client_cls):
    # Arrange
    host = "localhost"
    ssh = SSHEntity(host)
    ssh._ssh_client = ssh_client_cls()
    # Act
    session = ssh.get_new_session()
    # Assert
    self.assertEquals(ssh._ssh_client.get_transport.call_count, 1)\

  @mock.patch("paramiko.client.SSHClient")
  def test_execute_remote_command(self, ssh_client_cls):
    # Arrange
    host = "localhost"
    cmd = "ls"
    ssh = SSHEntity(host)
    ssh._ssh_cls = ssh_client_cls
    session_mock = mock.Mock()
    session_mock.recv.return_value = "dummy"
    session_mock.recv.side_effect = lambda x: "dummy"
    ssh.get_new_session = lambda: session_mock
    # Act
    ssh.execute_remote_command(cmd)
    # Assert
    session_mock.exec_command.assert_called_once_with(cmd)
    self.assertTrue(session_mock.recv.call_count >= 1)


if __name__ == '__main__':
  unittest.main()
