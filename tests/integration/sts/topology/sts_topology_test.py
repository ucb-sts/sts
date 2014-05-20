# Copyright 2011-2013 Colin Scott
# Copyright 2011-2013 Andreas Wundsam
# Copyright 2012-2013 Sam Whitlock
# Copyright 2014      Ahmed El-Hassany
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

from pox.lib.ioworker.io_worker import RecocoIOLoop

from sts.topology.sts_topology import Topology


class TopologyTest(unittest.TestCase):
  _io_loop = RecocoIOLoop()
  _io_ctor = _io_loop.create_worker_for_socket

  def test_create_switch(self):
    # Arrange
    topo = Topology()
    s1_dpid = 1
    s2_dpid = 2
    s1_ports = 3
    s2_ports = 3
    # Act
    s1 = topo.create_switch(s1_dpid, s1_ports)
    s2 = topo.create_switch(s2_dpid, s2_ports)
    # Assert
    self.assertEqual(len(s1.ports), s1_ports)
    self.assertEqual(s1.dpid, s1_dpid)
    self.assertEqual(len(s2.ports), s2_ports)
    self.assertEqual(s2.dpid, s2_dpid)
    self.assertItemsEqual([s1, s2], topo.switches)
    self.assertNotEqual(s2.ports[1].hw_addr, s1.ports[1].hw_addr)