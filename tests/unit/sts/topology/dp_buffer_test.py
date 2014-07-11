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

from pox.lib.addresses import EthAddr
from pox.lib.ioworker.io_worker import RecocoIOLoop
from pox.openflow.libopenflow_01 import ofp_phy_port
from pox.openflow.software_switch import DpPacketOut
from pox.openflow.software_switch import SoftwareSwitch

from sts.traffic_generator import TrafficGenerator
from sts.topology.sts_topology import STSTopology
from sts.topology.topology_factory import create_mesh_topology

from sts.topology.dp_buffer import BufferedPatchPanel
from sts.topology.dp_buffer import DataPathBufferCapabilities

from tests.unit.sts.util.capability_test import CapabilitiesGenericTest


class DataPathBufferCapabilitiesTest(CapabilitiesGenericTest):
  def setUp(self):
    self._capabilities_cls = DataPathBufferCapabilities


class BufferedPanelTest(unittest.TestCase):
  _io_loop = RecocoIOLoop()
  _io_ctor = _io_loop.create_worker_for_socket

  def setUp(self):
    class MockSwitch(SoftwareSwitch):
      _eventMixin_events = set([DpPacketOut])

      def __init__(self, dpid, ports):
        self.has_forwarded = False
        self.dpid = dpid
        self.ports = {}
        for port in ports:
          self.ports[port.port_no] = port

      def process_packet(self, packet, in_port):
        self.has_forwarded = True

    def create_mock_switch(switch_id, num_ports, can_connect_to_endhosts=False):
      ports = []
      for port_no in range(1, num_ports + 1):
        port = ofp_phy_port(port_no=port_no,
                            hw_addr=EthAddr("00:00:00:00:%02x:%02x" % (
                              switch_id, port_no)))
        # monkey patch an IP address onto the port for anteater purposes
        port.ip_addr = "1.1.%d.%d" % (switch_id, port_no)
        ports.append(port)
      return MockSwitch(switch_id, ports)

    topo = STSTopology(None)
    topo.switches_manager.create_switch = create_mock_switch
    create_mesh_topology(topo, 3)
    self.switches = list(topo.switches_manager.switches)
    self.m = BufferedPatchPanel(self.switches, [],
                                topo.patch_panel.get_other_side)
    self.traffic_generator = TrafficGenerator()
    self.switch1 = self.switches[0]
    self.switch2 = self.switches[1]
    self.port = self.switch1.ports.values()[1]
    self.icmp_packet = self.traffic_generator.icmp_ping(self.port, None)
    self.dp_out_event = DpPacketOut(self.switch1, self.icmp_packet, self.port)

  def test_buffering(self):
    self.switch1.raiseEvent(self.dp_out_event)
    self.assertFalse(self.switch2.has_forwarded,
                     "should not have forwarded yet")
    self.assertFalse(len(self.m.queued_dataplane_events) == 0,
                     "should have buffered packet")
    self.m.permit_dp_event(self.dp_out_event)
    self.assertTrue(len(self.m.queued_dataplane_events) == 0,
                    "should have cleared buffer")
    self.assertTrue(self.switch2.has_forwarded,
                    "should have forwarded")

  def test_drop(self):
    # raise the event
    self.switch1.raiseEvent(self.dp_out_event)
    self.assertFalse(self.switch2.has_forwarded,
                     "should not have forwarded yet")
    self.assertFalse(len(self.m.queued_dataplane_events) == 0,
                     "should have buffered packet")
    self.m.drop_dp_event(self.dp_out_event)
    self.assertTrue(len(self.m.queued_dataplane_events) == 0,
                    "should have cleared buffer")
    self.assertFalse(self.switch2.has_forwarded,
                     "should not have forwarded")
