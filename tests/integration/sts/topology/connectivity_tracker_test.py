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


import functools
import socket
import unittest


from pox.openflow.libopenflow_01 import ofp_phy_port
from pox.lib.util import connect_socket_with_backoff

from sts.topology.base import Topology, TopologyCapabilities

from sts.topology.controllers_manager import ControllersManager

from sts.entities.hosts import Host
from sts.entities.hosts import HostInterface
from sts.entities.sts_entities import AccessLink
from sts.entities.sts_entities import Link
from sts.entities.sts_entities import FuzzSoftwareSwitch

from sts.topology.sts_hosts_manager import STSHostsManager
from sts.topology.sts_switches_manager import STSSwitchesManager
from sts.topology.sts_patch_panel import STSPatchPanel

from sts.topology.dp_buffer import BufferedPatchPanel

from sts.entities.sts_entities import DeferredOFConnection
from sts.openflow_buffer import OpenFlowBuffer
from sts.util.io_master import IOMaster
from sts.util.deferred_io import DeferredIOWorker


from sts.topology.connectivity_tracker import ConnectivityTracker


class ConnectivityTrackerTest(unittest.TestCase):
  def initialize_io_loop(self):
    io_master = IOMaster()
    return io_master

  def create_connection(self, controller_info, switch):
    """Connect switches to controllers. May raise a TimeoutError"""
    max_backoff_seconds = 1024
    socket_ctor = socket.socket
    sock = connect_socket_with_backoff(controller_info.config.address,
                                       controller_info.config.port,
                                       max_backoff_seconds=max_backoff_seconds,
                                       socket_ctor=socket_ctor)
    # Set non-blocking
    sock.setblocking(0)
    io_worker = DeferredIOWorker(self.io_master.create_worker_for_socket(sock))
    connection = DeferredOFConnection(io_worker, controller_info.cid,
                                      switch.dpid, self.openflow_buffer)
    return connection

  def sts_topology_type_factory(self, is_host=None, is_switch=None,
                                is_network_link=None, is_access_link=None,
                                is_host_interface=None, is_port=None):
    """
    Fills in the parameters needed for default behavior as STS topology.
    Returns Topology class init with some of the fields already filled in.
    """
    is_host_lambda = lambda x: isinstance(x, Host)
    is_switch_lambda = lambda x: hasattr(x, 'dpid')
    is_network_link_lambda =lambda x: isinstance(x, Link)
    is_access_link_lambda = lambda x: isinstance(x, AccessLink)
    is_host_interface_lambda = lambda x: isinstance(x, HostInterface)
    is_port_lambda = lambda x: isinstance(x, ofp_phy_port)
    is_host = is_host or is_host_lambda
    is_switch = is_switch or is_switch_lambda
    is_network_link = is_network_link or is_network_link_lambda
    is_access_link = is_access_link or is_access_link_lambda
    is_host_interface = is_host_interface or is_host_interface_lambda
    is_port = is_port or is_port_lambda
    return functools.partial(
      Topology, hosts_manager=STSHostsManager(),
      switches_manager=STSSwitchesManager(self.create_connection),
      controllers_manager=ControllersManager(),
      dp_buffer=BufferedPatchPanel(),
      is_host=is_host, is_switch=is_switch,
      is_network_link=is_network_link,
      is_access_link=is_access_link,
      is_host_interface=is_host_interface,
      is_port=is_port)

  def get_topology(self):
    topo_cls = self.sts_topology_type_factory()
    topo = topo_cls(patch_panel=STSPatchPanel(),
                    capabilities=TopologyCapabilities())
    s1 = FuzzSoftwareSwitch(1, 's1', ports=2)
    s2 = FuzzSoftwareSwitch(2, 's2', ports=2)
    topo.add_switch(s1)
    topo.add_switch(s2)

    h1_eth1 = HostInterface(hw_addr='11:22:33:44:55:66', ip_or_ips='10.0.0.1')
    h1 = Host([h1_eth1], name='h1', hid=1)
    h2_eth1 = HostInterface(hw_addr='11:22:33:44:55:77', ip_or_ips='10.0.0.2')
    h2 = Host([h2_eth1], name='h2', hid=2)
    topo.add_host(h1)
    topo.add_host(h2)

    topo.create_access_link(h1, h1_eth1, s1, s1.ports[1])
    topo.create_access_link(h2, h2_eth1, s2, s1.ports[1])
    topo.create_network_link(s1, s1.ports[2], s2, s2.ports[2])
    return topo

  def setUp(self):
    self.io_master = self.initialize_io_loop()
    self.openflow_buffer = OpenFlowBuffer()

  def test_default_behaviour(self):
    # Arrange
    topo = self.get_topology()
    h1 = topo.hosts_manager.get_host('h1')
    h2 = topo.hosts_manager.get_host('h2')
    # Act
    tracker1 = ConnectivityTracker(default_connected=False)
    tracker2 = ConnectivityTracker(default_connected=True)
    default_disconnected = tracker1.is_connected(h1, h2)
    default_connected = tracker2.is_connected(h1, h2)
    # Assert
    self.assertTrue(default_connected)
    self.assertFalse(default_disconnected)

  def test_add_connected(self):
    """Add connectivity policies"""
    # Arrange
    topo = self.get_topology()
    h1 = topo.hosts_manager.get_host('h1')
    h2 = topo.hosts_manager.get_host('h2')
    h1_eth1 = h1.interfaces[0]
    h2_eth1 = h2.interfaces[0]
    # Act
    tracker1 = ConnectivityTracker(default_connected=False)
    tracker2 = ConnectivityTracker(default_connected=True)
    tracker1.add_connected_hosts(h1, h1_eth1, h2, h2_eth1, 1)
    tracker2.add_connected_hosts(h1, h1_eth1, h2, h2_eth1, 1)
    connected1 = tracker1.is_connected(h1, h2)
    connected2 = tracker2.is_connected(h1, h2)
    # Assert
    self.assertTrue(connected1)
    self.assertTrue(connected2)

  def test_remove_connected_policies(self):
    """Remove connectivity policies"""
    # Arrange
    topo = self.get_topology()
    h1 = topo.hosts_manager.get_host('h1')
    h2 = topo.hosts_manager.get_host('h2')
    h1_eth1 = h1.interfaces[0]
    h2_eth1 = h2.interfaces[0]
    tracker1 = ConnectivityTracker(default_connected=False)
    tracker2 = ConnectivityTracker(default_connected=True)
    tracker1.add_connected_hosts(h1, h1_eth1, h2, h2_eth1, 1)
    tracker2.add_connected_hosts(h1, h1_eth1, h2, h2_eth1, 1)
    # Act
    tracker1.remove_policy(1)
    tracker2.remove_policy(1)
    connected_removed1 = tracker1.is_connected(h1, h2)
    connected_removed2 = tracker2.is_connected(h1, h2)
    # Assert
    self.assertFalse(connected_removed1)
    self.assertTrue(connected_removed2)

  def test_add_disconnected(self):
    """Add dis-connectivity policies"""
    # Arrange
    topo = self.get_topology()
    h1 = topo.hosts_manager.get_host('h1')
    h2 = topo.hosts_manager.get_host('h2')
    h1_eth1 = h1.interfaces[0]
    h2_eth1 = h2.interfaces[0]
    # Act
    tracker1 = ConnectivityTracker(default_connected=False)
    tracker2 = ConnectivityTracker(default_connected=True)
    tracker1.add_disconnected_hosts(h1, h1_eth1, h2, h2_eth1, 1)
    tracker2.add_disconnected_hosts(h1, h1_eth1, h2, h2_eth1, 1)
    disconnected1 = tracker1.is_connected(h1, h2)
    disconnected2 = tracker2.is_connected(h1, h2)
    # Assert
    self.assertFalse(disconnected1)
    self.assertFalse(disconnected2)

  def test_remove_disconnected_policies(self):
    """Remove connectivity policies"""
    # Arrange
    topo = self.get_topology()
    h1 = topo.hosts_manager.get_host('h1')
    h2 = topo.hosts_manager.get_host('h2')
    h1_eth1 = h1.interfaces[0]
    h2_eth1 = h2.interfaces[0]
    tracker1 = ConnectivityTracker(default_connected=False)
    tracker2 = ConnectivityTracker(default_connected=True)
    tracker1.add_disconnected_hosts(h1, h1_eth1, h2, h2_eth1, 1)
    tracker2.add_disconnected_hosts(h1, h1_eth1, h2, h2_eth1, 1)
    # Act
    tracker1.remove_policy(1)
    tracker2.remove_policy(1)
    disconnected_removed1 = tracker1.is_connected(h1, h2)
    disconnected_removed2 = tracker2.is_connected(h1, h2)
    # Assert
    self.assertFalse(disconnected_removed1)
    self.assertTrue(disconnected_removed2)
