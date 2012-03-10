#!/usr/bin/env python

import unittest
import sys
import os.path
import itertools
from copy import copy
import types

sys.path.append(os.path.dirname(__file__) + "/../../..")

from debugger.topology_generator import *
from debugger.traffic_generator import *
from pox.lib.ioworker.io_worker import RecocoIOLoop
from pox.openflow.switch_impl import SwitchImpl

class topology_generator_test(unittest.TestCase):
  _io_loop = RecocoIOLoop()
  _io_ctor = _io_loop.create_worker_for_socket
  _io_dtor = _io_loop.remove_worker
  
  def test_create_switch(self):
    s = create_switch(1, 3, self._io_ctor, self._io_dtor)
    self.assertEqual(len(s.ports), 3)
    self.assertEqual(s.dpid, 1)
    s2 = create_switch(2, 3, self._io_ctor, self._io_dtor)
    self.assertNotEqual(s2.ports[1].hw_addr, s.ports[1].hw_addr)

  def test_create_meshes(self):
    """ Create meshes of several sizes and ensure they are fully connected """
    for i in (2,3, 5, 12):
      self._test_create_mesh(i)

  def _test_create_mesh(self, size):
    (panel, switches) = create_mesh(size, self._io_ctor, self._io_dtor)
    self.assertEqual(len(switches), size)
    self.assertEqual([sw for sw in switches if len(sw.ports) == size-1 ], switches)

    # check that all pairs of switches are connected
    sw_pairs = [pair for pair in itertools.permutations(switches, 2) if pair[0] != pair[1] ]
    # create a list of tuples of all (switches, ports)
    sw_ports = [ (sw, p) for sw in switches for _, p in sw.ports.iteritems() ]
    # collect the 'other' switches, ports. Should end up the same, modulo sorting
    other_sw_ports = []

    for switch in switches:
      for port_no, port in switch.ports.iteritems():
        # TODO: abuse of dynamic types... get_connected_port is a field
        (other_switch, other_port) = panel.get_connected_port(switch, port)
        self.assertTrue( (switch, other_switch) in sw_pairs, "Switches %s, %s connected twice" % (switch, other_switch))
        sw_pairs.remove( (switch, other_switch) )
        other_sw_ports.append( (other_switch, other_port) )

    self.assertEqual(len(sw_pairs), 0, "Non-connected switches: %s" % sw_pairs)
    # sort the other guy by (dpid, port_no)
    other_sw_ports.sort(key=lambda (sw,port): (sw.dpid, port.port_no))
    self.assertEqual(sw_ports, other_sw_ports)

class FullyMeshedLinkTest(unittest.TestCase):
  _io_loop = RecocoIOLoop()
  _io_ctor = _io_loop.create_worker_for_socket
  _io_dtor = _io_loop.remove_worker
  
  def setUp(self):
    self.switches = [ create_switch(switch_id, 2, self._io_ctor, self._io_dtor) for switch_id in range(1, 4) ]
    self.links = FullyMeshedLinks(self.switches)
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
    
class BufferedPanelTest(unittest.TestCase):
  _io_loop = RecocoIOLoop()
  _io_ctor = _io_loop.create_worker_for_socket
  _io_dtor = _io_loop.remove_worker
  
  def setUp(self):
    class MockSwitch(SwitchImpl):
      _eventMixin_events = set([SwitchDpPacketOut])

      def __init__(self, dpid, ports):
        self.has_forwarded = False
        self.dpid = 0
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
    self.m = BufferedPatchPanel(self.switches, FullyMeshedLinks(self.switches).get_connected_port)
    self.traffic_generator = TrafficGenerator()
    self.switch = self.switches[0]
    self.port = self.switch.ports.values()[0]
    self.icmp_packet = self.traffic_generator.icmp_ping(self.switch, self.port)
    self.dp_out_event = SwitchDpPacketOut(self.switch, self.icmp_packet, self.port)
    
  def test_buffering(self):
    self.switch.raiseEvent(self.dp_out_event)
    self.assertFalse(self.switch.has_forwarded, "should not have forwarded yet")
    self.assertFalse(len(self.m.get_buffered_dp_events()) == 0, "should have buffered packet")
    self.m.permit_dp_event(self.dp_out_event)
    self.assertTrue(len(self.m.get_buffered_dp_events()) == 0, "should have cleared buffer")
    self.assertTrue(self.switch.has_forwarded, "should have forwarded")
    
  def test_drop(self):
    global forwarded
    forwarded = False
    # raise the event 
    self.switch.raiseEvent(self.dp_out_event)
    self.assertFalse(self.switch.has_forwarded, "should not have forwarded yet")
    self.assertFalse(len(self.m.get_buffered_dp_events()) == 0, "should have buffered packet")
    self.m.drop_dp_event(self.dp_out_event)
    self.assertTrue(len(self.m.get_buffered_dp_events()) == 0, "should have cleared buffer")
    self.assertFalse(self.switch.has_forwarded, "should not have forwarded")
    

if __name__ == '__main__':
  unittest.main()
