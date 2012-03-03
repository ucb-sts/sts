#!/usr/bin/env python

import unittest
import sys
import os.path
import itertools
from copy import copy

sys.path.append(os.path.dirname(__file__) + "/../../..")

from debugger.topology_generator import *

class topology_generator_test(unittest.TestCase):
  def test_create_switch(self):
    s = create_switch(switch_id=1, num_ports=3)
    self.assertEqual(len(s.ports), 3)
    self.assertEqual(s.dpid, 1)
    s2 = create_switch(switch_id=2, num_ports=3)
    self.assertNotEqual(s2.ports[1].hw_addr, s.ports[1].hw_addr)

  def test_create_meshes(self):
    """ Create meshes of several sizes and ensure they are fully connected """
    for i in (2,3, 5, 12):
      self._test_create_mesh(i)

  def _test_create_mesh(self, size):
    (panel, switches) = create_mesh(size)
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
        (other_switch, other_port) = panel.connected_port(switch, port)
        self.assertTrue( (switch, other_switch) in sw_pairs, "Switches %s, %s connected twice" % (switch, other_switch))
        sw_pairs.remove( (switch, other_switch) )
        other_sw_ports.append( (other_switch, other_port) )

    self.assertEqual(len(sw_pairs), 0, "Non-connected switches: %s" % sw_pairs)
    # sort the other guy by (dpid, port_no)
    other_sw_ports.sort(key=lambda (sw,port): (sw.dpid, port.port_no))
    self.assertEqual(sw_ports, other_sw_ports)

class FullyMeshedPanelTest(unittest.TestCase):
  def setUp(self):
    self.switches = [ create_switch(switch_id, 2) for switch_id in range(1, 4) ]
    self.m = FullyMeshedPanel(self.switches)

  def test_connected_ports(self):
    m = self.m

    def check_pair(a, b):
      a_switch = self.switches[a[0]-1]
      a_port = a_switch.ports[a[1]]
      b_switch = self.switches[b[0]-1]
      b_port = b_switch.ports[b[1]]
      self.assertEqual(m.connected_port(a_switch, a_port), (b_switch, b_port))
      self.assertEqual(m.connected_port(b_switch, b_port), (a_switch, a_port))

    check_pair( (1,1), (2,1))
    check_pair( (1,2), (3,1))
    check_pair( (3,2), (2,2))

if __name__ == '__main__':
  unittest.main()
