import random
import unittest
import sys
import os.path

sys.path.append(os.path.dirname(__file__) + "/../../..")

from pox.openflow.libopenflow_01 import *
from sts.control_flow import Fuzzer, create_mock_connection
from sts.entities import FuzzSoftwareSwitch
from sts.simulation_state import SimulationConfig
from sts.topology import create_switch

import unittest
import Queue


class MonkeyRandom:
  """Monkey-patch random.random() for testing"""
  def __init__(self):
    self.idx = 0
    # The numbers self.random() will spit out in order
    self.numbers = [0.3,0.2,0.25,0.1,0.6,0.5,0.4]
  
  def random(self):
    ret_val = self.numbers[self.idx]
    self.idx += 1
    return ret_val

class DelayedFlowModTest(unittest.TestCase):

  class ControllerConfigs(object):
    """ Fake controller configuration to add to switch"""
    def __init__(self):
      self.cid = 3


  def setUp(self):
    self.old_random = random.Random
    random.Random = MonkeyRandom

    # Create Switch, add controller, and connect to it
    self.switch = create_switch(1,2)
    self.switch.use_delayed_commands()
    self.switch.randomize_flow_mods()
    self.configs = self.ControllerConfigs()
    self.switch.add_controller_info(self.configs)
    self.switch.connect(create_mock_connection)
    self.conn = self.switch.get_connection(self.configs.cid)

  def tearDown(self):
    # Restore legitimate random.Random class
    random.Random = self.old_random

  def create_flow_mod_group(self, num_flow_mods):
        li = []
        for i in range(num_flow_mods):
            li.append(ofp_flow_mod(match=ofp_match(in_port=i, nw_src="%s.%s.%s.%s" % (i,i,i,i)), action=ofp_action_output(port=i)))
        return li
  
  def read_to_switch(self, packet_list):
    for packet in packet_list:
        self.conn.read(packet)

  def process_delayed_commands(self, num_commands):
    for i in range(num_commands):
        self.assertTrue(self.switch.has_pending_commands())
        self.switch.process_delayed_command()


  def test_randomization(self):
    # Create packets to send
    (fm0, fm1, fm2, fm3) = self.create_flow_mod_group(4)
    other_packet = ofp_packet_out()

    # Read packets into switch
    self.read_to_switch([fm0, fm1, other_packet, fm2, fm3])

    # Tell switch to process commands the way Fuzzer would
    self.process_delayed_commands(4)

    # Make sure flow mods were processed according to the generated weights
    # IMPORTANT: Works off assumption switch's table stores entries in order they were processed
    self.assertEqual(self.switch.table.table[0].match.in_port, fm3.match.in_port)
    self.assertEqual(self.switch.table.table[1].match.in_port, fm1.match.in_port)
    self.assertEqual(self.switch.table.table[2].match.in_port, fm2.match.in_port)
    self.assertEqual(self.switch.table.table[3].match.in_port, fm0.match.in_port)

    # Make sure other_packet wasn't put into queue
    self.assertRaises(Queue.Empty, self.switch.process_delayed_command)
    # Make sure nothing else got in the table.
    self.assertRaises(IndexError, self.switch.table.table.__getitem__,4)

  def test_barriers(self):
    (fm0, fm1, fm2, fm3, fm4, fm5, fm6) = self.create_flow_mod_group(7)
    barrier_1 = ofp_barrier_request()
    barrier_2 = ofp_barrier_request()
    barrier_3 = ofp_barrier_request()
    barrier_4 = ofp_barrier_request()
    barrier_5 = ofp_barrier_request()

    self.read_to_switch([fm0, barrier_1, fm1])
    self.process_delayed_commands(2)
    # make sure that barrier enforces flush
    self.assertEqual(self.switch.table.table[0].match.in_port, fm0.match.in_port)
    self.assertEqual(self.switch.table.table[1].match.in_port, fm1.match.in_port)

    # command queue empty here, so this should cause instant reply
    self.read_to_switch([barrier_2])
    self.assertRaises(Queue.Empty, self.switch.process_delayed_command)

    # make sure interleaving and consecutive barriers work as expected
    self.read_to_switch([fm2, fm3, barrier_3, fm4, barrier_4, barrier_5])
    self.process_delayed_commands(1)
    self.read_to_switch([fm5, fm6])
    self.process_delayed_commands(4)

    self.assertEqual(self.switch.table.table[2].match.in_port, fm3.match.in_port)
    self.assertEqual(self.switch.table.table[3].match.in_port, fm2.match.in_port)
    self.assertEqual(self.switch.table.table[4].match.in_port, fm4.match.in_port)
    self.assertEqual(self.switch.table.table[5].match.in_port, fm6.match.in_port)
    self.assertEqual(self.switch.table.table[6].match.in_port, fm5.match.in_port)

    
if __name__ == '__main__':
  unittest.main()
