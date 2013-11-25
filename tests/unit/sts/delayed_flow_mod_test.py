import random
import unittest
import sys
import os.path

sys.path.append(os.path.dirname(__file__) + "/../../..")

from pox.openflow.libopenflow_01 import *
from sts.control_flow import Fuzzer
from sts.controller_manager import create_mock_connection
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
    self.numbers = [0.3,0.2,0.1,0.25]
  
  def random(self):
    ret_val = self.numbers[self.idx]
    self.idx += 1
    return ret_val

class DelayedFlowModTest(unittest.TestCase):

  class ControllerConfigs(object):
    """ Fake controller configuration to add to switch"""
    def __init__(self):
      self.cid = 3

  def test_manual(self):
    # Store the actual random.Random class
    old_random = random.Random
    random.Random = MonkeyRandom

    # Create Switch, add controller, and connect to it
    switch = create_switch(1,2)
    switch.use_delayed_commands()
    switch.randomize_flow_mods()
    configs = self.ControllerConfigs()
    switch.add_controller_info(configs)
    switch.connect(create_mock_connection)
    conn = switch.get_connection(configs.cid)

    # Create packets to send
    flow_mod1 = ofp_flow_mod(match=ofp_match(in_port=1, nw_src="1.1.1.1"), action=ofp_action_output(port=1))
    flow_mod2 = ofp_flow_mod(match=ofp_match(in_port=2, nw_src="2.2.2.2"), action=ofp_action_output(port=1))
    flow_mod3 = ofp_flow_mod(match=ofp_match(in_port=3, nw_src="3.3.3.3"), action=ofp_action_output(port=1))
    flow_mod4 = ofp_flow_mod(match=ofp_match(in_port=4, nw_src="4.4.4.4"), action=ofp_action_output(port=1))
    other_packet = ofp_packet_out()

    # Read packets into switch
    conn.read(flow_mod1)
    conn.read(flow_mod2)
    conn.read(other_packet)
    conn.read(flow_mod3)
    conn.read(flow_mod4)

    # Tell switch to process commands the way Fuzzer would
    self.assertTrue(switch.has_pending_commands())
    switch.process_delayed_command()
    self.assertTrue(switch.has_pending_commands())
    switch.process_delayed_command()
    self.assertTrue(switch.has_pending_commands())
    switch.process_delayed_command()
    self.assertTrue(switch.has_pending_commands())
    switch.process_delayed_command()

    # Make sure flow mods were processed according to the generated weights
    # IMPORTANT: Works off assumption switch's table stores entries in order they were processed
    self.assertEqual(switch.table.table[0].match.in_port, flow_mod3.match.in_port)
    self.assertEqual(switch.table.table[1].match.in_port, flow_mod2.match.in_port)
    self.assertEqual(switch.table.table[2].match.in_port, flow_mod4.match.in_port)
    self.assertEqual(switch.table.table[3].match.in_port, flow_mod1.match.in_port)

    # Make sure other_packet wasn't put into queue
    self.assertRaises(Queue.Empty, switch.process_delayed_command)
    # Make sure nothing else got in the table.
    self.assertRaises(IndexError, switch.table.table.__getitem__,4)

    # Restore legitimate random.Random class
    random.Random = old_random


if __name__ == '__main__':
  unittest.main()
