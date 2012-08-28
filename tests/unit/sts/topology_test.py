#!/usr/bin/env python

import unittest
import sys
import os.path
import itertools
from copy import copy
import types

sys.path.append(os.path.dirname(__file__) + "/../../..")

from sts.topology import *
from sts.traffic_generator import *
from pox.lib.ioworker.io_worker import RecocoIOLoop
from pox.openflow.switch_impl import SwitchImpl
from pox.lib.graph.graph import Graph
from sts.debugger_entities import Host, HostInterface

class topology_test(unittest.TestCase):
  _io_loop = RecocoIOLoop()
  _io_ctor = _io_loop.create_worker_for_socket

  def test_create_switch(self):
    s = create_switch(1, 3)
    self.assertEqual(len(s.ports), 3)
    self.assertEqual(s.dpid, 1)
    s2 = create_switch(2, 3)
    self.assertNotEqual(s2.ports[1].hw_addr, s.ports[1].hw_addr)

  def test_create_meshes(self):
    """ Create meshes of several sizes and ensure they are fully connected """
    for i in (2,3, 5, 12):
      self._test_create_mesh(i)

  def _test_create_mesh(self, size):
    mesh = MeshTopology(size)
    self.assertEqual(len(mesh.switches), size)
    self.assertEqual([sw for sw in mesh.switches if len(sw.ports) == size ],
                     mesh.switches)

    # check that all pairs of switches are connected to each other
    non_connected_sw_pairs = [pair for pair in itertools.permutations(mesh.switches, 2) if pair[0] != pair[1] ]
    # create a list of all (switch, port) pairs
    sw_port_pairs = [ (sw, p) for sw in mesh.switches for _, p in sw.ports.iteritems() ]
    # check the all hosts are connected once
    non_connected_hosts = set(mesh.hosts)
    # create a list of all (host, interface) pairs
    host_interface_pairs = [ (host, interface) for host in mesh.hosts for interface in host.interfaces ]
    # collect the 'other' (switch, port) pairs. This + (hosts, interface) pairs should
    # end up the same as sw_port_pairs + host_interface_pairs
    other_sw_port_pairs = []
    # List of (host, interface) edge tail pairs
    other_host_interface_pairs = []
    # list of (switch, port) access ports
    access_sw_port_pairs = []

    for switch in mesh.switches:
      for port_no, port in switch.ports.iteritems():
        # TODO: abuse of dynamic types... get_connected_port is a field
        (other_node, other_port) = mesh.get_connected_port(switch, port)
        if type(other_node) == Host:
          self.assertTrue( other_node in non_connected_hosts, "%s" % str(other_node) )
          non_connected_hosts.remove(other_node)
          access_sw_port_pairs.append( (switch, port) )
          other_host_interface_pairs.append( (other_node, other_port) )
        else:
          self.assertTrue( (switch, other_node) in non_connected_sw_pairs, "Switches %s, %s connected twice" % (switch, other_node))
          non_connected_sw_pairs.remove( (switch, other_node) )
          other_sw_port_pairs.append( (other_node, other_port) )

    self.assertEqual(len(non_connected_sw_pairs), 0, "Non-connected switches: %s" % non_connected_sw_pairs)
    self.assertEqual(len(non_connected_hosts), 0, "Non-connected hosts: %s" % non_connected_hosts)

    # Ensure the list was already unique
    self.assertEqual(len(set(sw_port_pairs)), len(sw_port_pairs))
    self.assertEqual(len(set(other_sw_port_pairs)), len(other_sw_port_pairs))
    self.assertEqual(len(set(access_sw_port_pairs)), len(access_sw_port_pairs))
    # Test all switches connected
    self.assertEqual(set(sw_port_pairs), set(other_sw_port_pairs).union(set(access_sw_port_pairs)))
    # Ensure the list was already unique
    self.assertEqual(len(set(host_interface_pairs)), len(host_interface_pairs))
    self.assertEqual(len(set(other_host_interface_pairs)), len(other_host_interface_pairs))
    self.assertEqual(set(host_interface_pairs), set(other_host_interface_pairs))

    # Make sure that all access links are accounted for
    self.assertTrue(len(mesh.access_links) == len(mesh.hosts))
    for access_link in mesh.access_links:
      self.assertTrue((access_link.host, access_link.interface) in host_interface_pairs)
      self.assertTrue((access_link.switch, access_link.switch_port) in access_sw_port_pairs)

    # Make sure that all network links are accounted for
    self.assertTrue(len(mesh.network_links) == len(mesh.switches) * (len(mesh.switches) - 1))
    for link in mesh.network_links:
      self.assertTrue((link.start_switch_impl, link.start_port) in sw_port_pairs)
      self.assertTrue((link.end_switch_impl, link.end_port) in sw_port_pairs)

class FullyMeshedLinkTest(unittest.TestCase):
  _io_loop = RecocoIOLoop()
  _io_ctor = _io_loop.create_worker_for_socket

  def setUp(self):
    self.switches = [ create_switch(switch_id, 2) for switch_id in range(1, 4) ]
    self.links = MeshTopology.FullyMeshedLinks(self.switches)
    self.get_connected_port = self.links.get_connected_port

  def test_connected_ports(self):
    def check_pair(a, b):
      a_switch = self.switches[a[0]-1]
      a_port = a_switch.ports[a[1]]
      b_switch = self.switches[b[0]-1]
      b_port = b_switch.ports[b[1]]
      self.assertEqual(self.get_connected_port(a_switch, a_port), (b_switch, b_port))
      self.assertEqual(self.get_connected_port(b_switch, b_port), (a_switch, a_port))

    check_pair( (1,1), (2,1))
    check_pair( (1,2), (3,1))
    check_pair( (3,2), (2,2))

class TopologyUnitTest(unittest.TestCase):
  _io_loop = RecocoIOLoop()
  _io_ctor = _io_loop.create_worker_for_socket

  def setUp(self):
    class MockSwitch(SwitchImpl):
      _eventMixin_events = set([DpPacketOut])

      def __init__(self, dpid, ports):
        self.has_forwarded = False
        self.dpid = dpid
        self.ports = {}
        for port in ports:
          self.ports[port.port_no] = port
      def process_packet(self, packet, in_port):
        self.has_forwarded = True
    def create_mock_switch(num_ports, switch_id):
      ports = []
      for port_no in range(1, num_ports+1):
        port = ofp_phy_port( port_no=port_no,
                             hw_addr=EthAddr("00:00:00:00:%02x:%02x" % (switch_id, port_no)) )
        # monkey patch an IP address onto the port for anteater purposes
        port.ip_addr = "1.1.%d.%d" % (switch_id, port_no)
        ports.append(port)
      return MockSwitch(switch_id, ports)
    self.g = Graph()
    self.switches = [create_mock_switch(2, 1), create_mock_switch(2, 2)]
    self.hosts = [Host([HostInterface(EthAddr("00:00:00:00:00:01"))], name="host1"),
                  Host([HostInterface(EthAddr("00:00:00:00:00:02"))], name="host2")]
    for switch in self.switches:
      self.g.add(switch)
    for host in self.hosts:
      self.g.add(host)
    self.g.link((self.switches[0], self.switches[0].ports[2]), (self.switches[1], self.switches[1].ports[2]))
    self.g.link((self.hosts[0], self.hosts[0].interfaces[0]), (self.switches[0], self.switches[0].ports[1]))
    self.g.link((self.hosts[1], self.hosts[1].interfaces[0]), (self.switches[1], self.switches[1].ports[1]))
    topology = Topology.populate_from_topology(self.g)
    self.patch = BufferedPatchPanelForTopology(self.g)
    self.switches_calc = topology.switches
    self.hosts_calc = topology.hosts
    self.access_links = topology.access_links

  def test_generated_topology(self):
    self.assertEqual(len(self.access_links), len(self.hosts))
    self.assertEqual(len(self.hosts_calc), len(self.hosts))
    self.assertEqual(len(self.switches_calc), len(self.switches))

class BufferedPanelTest(unittest.TestCase):
  _io_loop = RecocoIOLoop()
  _io_ctor = _io_loop.create_worker_for_socket

  def setUp(self):
    class MockSwitch(SwitchImpl):
      _eventMixin_events = set([DpPacketOut])

      def __init__(self, dpid, ports):
        self.has_forwarded = False
        self.dpid = dpid
        self.ports = {}
        for port in ports:
          self.ports[port.port_no] = port

      def process_packet(self, packet, in_port):
        self.has_forwarded = True

    def create_mock_switch(num_ports, switch_id):
      ports = []
      for port_no in range(1, num_ports+1):
        port = ofp_phy_port( port_no=port_no,
                             hw_addr=EthAddr("00:00:00:00:%02x:%02x" % (switch_id, port_no)) )
        # monkey patch an IP address onto the port for anteater purposes
        port.ip_addr = "1.1.%d.%d" % (switch_id, port_no)
        ports.append(port)
      return MockSwitch(switch_id, ports)

    self.switches = [create_mock_switch(1,1), create_mock_switch(1,2)]
    self.m = BufferedPatchPanel(self.switches, [], MeshTopology.FullyMeshedLinks(self.switches).get_connected_port)
    self.traffic_generator = TrafficGenerator()
    self.switch1 = self.switches[0]
    self.switch2 = self.switches[1]
    self.port = self.switch1.ports.values()[0]
    self.icmp_packet = self.traffic_generator.icmp_ping(self.switch1, self.port)
    self.dp_out_event = DpPacketOut(self.switch1, self.icmp_packet, self.port)

  def test_buffering(self):
    self.switch1.raiseEvent(self.dp_out_event)
    self.assertFalse(self.switch2.has_forwarded, "should not have forwarded yet")
    self.assertFalse(len(self.m.get_buffered_dp_events()) == 0, "should have buffered packet")
    self.m.permit_dp_event(self.dp_out_event)
    self.assertTrue(len(self.m.get_buffered_dp_events()) == 0, "should have cleared buffer")
    self.assertTrue(self.switch2.has_forwarded, "should have forwarded")

  def test_drop(self):
    # raise the event
    self.switch1.raiseEvent(self.dp_out_event)
    self.assertFalse(self.switch2.has_forwarded, "should not have forwarded yet")
    self.assertFalse(len(self.m.get_buffered_dp_events()) == 0, "should have buffered packet")
    self.m.drop_dp_event(self.dp_out_event)
    self.assertTrue(len(self.m.get_buffered_dp_events()) == 0, "should have cleared buffer")
    self.assertFalse(self.switch2.has_forwarded, "should not have forwarded")


if __name__ == '__main__':
  unittest.main()
