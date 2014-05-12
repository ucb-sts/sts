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
from cStringIO import StringIO

from sts.entities.base import SSHEntity

paramiko_installed = False
try:
  import paramiko
  paramiko_installed = True
except ImportError:
  paramiko_installed = False

class SSHEntityTest(unittest.TestCase):

  @mock.patch("paramiko.client.SSHClient")
  @unittest.skipIf(not paramiko_installed, "paramiko not installed")
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
  @unittest.skipIf(not paramiko_installed, "paramiko not installed")
  def test_get_new_session(self, ssh_client_cls):
    # Arrange
    host = "localhost"
    ssh = SSHEntity(host)
    ssh._ssh_client = ssh_client_cls()
    # Act
    session = ssh.get_new_session()
    # Assert
    self.assertEquals(ssh._ssh_client.get_transport.call_count, 1)

  @mock.patch("paramiko.client.SSHClient")
  @unittest.skipIf(not paramiko_installed, "paramiko not installed")
  def test_execute_command(self, ssh_client_cls):
    # Arrange
    host = "localhost"
    cmd = "ls"
    ssh = SSHEntity(host)
    ssh._ssh_cls = ssh_client_cls

    session_mock = mock.Mock()
    session_mock.recv_ready.return_value = True
    session_mock.exit_status_ready.return_value = True
    session_mock.recv.return_value = "dummy"
    stream_mock = mock.Mock()
    stream_mock.channel = session_mock
    ssh.ssh_client.exec_command.return_value = None, stream_mock, None
    def change_status(y):
      session_mock.recv_ready.return_value = False
      return "dummy"
    session_mock.recv.side_effect = change_status
    ssh.get_new_session = lambda: session_mock
    # Act
    ssh.execute_command(cmd)
    # Assert
    ssh.ssh_client.exec_command.assert_called_once_with(cmd)
    self.assertTrue(session_mock.recv.call_count >= 1)

  @mock.patch("paramiko.client.SSHClient")
  @unittest.skipIf(not paramiko_installed, "paramiko not installed")
  def test_execute_command_with_redirect(self, ssh_client_cls):
    # Arrange
    host = "localhost"
    cmd = "ls"
    ssh = SSHEntity(host, redirect_output=True)
    ssh._ssh_cls = ssh_client_cls
    ssh.ssh_client.exec_command.return_value = (StringIO(), StringIO(),
                                                StringIO())
    # Act
    ssh.execute_command(cmd)
    # Assert
    ssh.ssh_client.exec_command.assert_called_once_with(cmd)


if __name__ == '__main__':
  unittest.main()
