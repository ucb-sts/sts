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

from sts.entities.hosts import HostInterface
from sts.entities.hosts import NamespaceHost
from sts.util.io_master import IOMaster


class NamespaceHostTest(unittest.TestCase):
  # TODO (AH): test send and receive
  def initialize_io_loop(self):
    io_master = IOMaster()
    return io_master

  @unittest.skipIf(os.geteuid() != 0, "Not running tests as root")
  def test_init(self):
    # Arrange
    name = "test-host"
    hid = 123
    hw_addr_str = "0e:32:a4:91:e7:20"
    ip = "192.168.56.1"
    interfaces = [HostInterface(hw_addr_str, ip)]
    io_master = self.initialize_io_loop()
    # Act
    host = NamespaceHost(interfaces, io_master.create_worker_for_socket,
                         name=name, hid=hid)
    # Assert
    self.assertEquals(host.interfaces, interfaces)

  def test_send(self):
    # TODO (AH): test send, better done when I figure out what to do with topo
    pass

  def test_receive(self):
    # TODO (AH): test receive, better done when I figure out what to do with
    #            topology.py
    pass
