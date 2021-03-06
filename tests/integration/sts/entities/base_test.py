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


import os
import unittest
import sys

from sts.entities.base import SSHEntity
from sts.entities.base import LocalEntity

paramiko_installed = False
try:
  import paramiko
  paramiko_installed = True
except ImportError:
  paramiko_installed = False


def get_ssh_config():
  """
  Loads the login information for SSH server
  """
  host = "localhost"
  port = 22
  username = None
  password = None
  return host, port, username, password


def can_connect(host, port, username, password):
  """
  Returns True if the the login information can be used to connect to a remote
  ssh server.
  """
  if not paramiko_installed:
    return False
  try:
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, port, username, password)
    client.close()
    return True
  except Exception as exp:
    print >> sys.stderr, exp
    return False


class SSHEntityTest(unittest.TestCase):
  @unittest.skipIf(not paramiko_installed, "paramiko not installed")
  @unittest.skipIf(not can_connect(*get_ssh_config()),
                   "Couldn't connect to SSH server")
  def test_connect(self):
    # Arrange
    host, port, username, password = get_ssh_config()
    # Act
    ssh = SSHEntity(host, port, username, password)
    ssh_client = ssh.ssh_client
    # Assert
    self.assertIsNotNone(ssh_client)
    # clean up
    ssh_client.close()

  @unittest.skipIf(not paramiko_installed, "paramiko not installed")
  @unittest.skipIf(not can_connect(*get_ssh_config()),
                   "Couldn't connect to SSH server")
  def test_session(self):
    # Arrange
    host, port, username, password = get_ssh_config()
    # Act
    ssh = SSHEntity(host, port, username, password)
    session = ssh.get_new_session()
    # Assert
    self.assertIsNotNone(session)

  @unittest.skipIf(not paramiko_installed, "paramiko not installed")
  @unittest.skipIf(not can_connect(*get_ssh_config()),
                   "Couldn't connect to SSH server")
  def test_execute_command(self):
    # Arrange
    host, port, username, password = get_ssh_config()
    home_dir = os.getcwd()
    # Act
    ssh = SSHEntity(host, port, username, password)
    ret = ssh.execute_command("ls -a " + home_dir)
    # Assert
    self.assertIsInstance(ret, basestring)
    ret_list = ret.split()
    ret_list.sort()
    # ls -a returns . and .. but os.listdir doesn't
    ret_list.remove('.')
    ret_list.remove('..')
    current_list = os.listdir('.')
    current_list.sort()
    self.assertEquals(ret_list, current_list)

  @unittest.skipIf(not paramiko_installed, "paramiko not installed")
  @unittest.skipIf(not can_connect(*get_ssh_config()),
                   "Couldn't connect to SSH server")
  def test_execute_command_with_redirect(self):
    # Arrange
    host, port, username, password = get_ssh_config()
    home_dir = os.getcwd()
    # Act
    ssh = SSHEntity(host, port, username, password, redirect_output=True)
    ret = ssh.execute_command("ls " + home_dir)
    # Assert
    self.assertIsInstance(ret, basestring)
    self.assertEquals(ret, "")


class LocalEntityTest(unittest.TestCase):
  def test_execute_command(self):
    # Arrange
    entity = LocalEntity()
    home_dir = os.getcwd()
    # Act
    ret = entity.execute_command("ls -a " + home_dir)
    # Assert
    self.assertIsInstance(ret, basestring)
    ret_list = ret.split()
    # ls -a returns . and .. but os.listdir doesn't
    ret_list.remove(".")
    ret_list.remove("..")
    ret_list.sort()
    current_list = os.listdir(home_dir)
    current_list.sort()
    self.assertEquals(ret_list, current_list)

  def test_execute_command_with_redirect(self):
    # Arrange
    entity = LocalEntity('/', redirect_output=True)
    home_dir = "/"
    # Act
    ret = entity.execute_command("ls " + home_dir)
    # Assert
    self.assertIsInstance(ret, basestring)
    self.assertEquals(ret, "")