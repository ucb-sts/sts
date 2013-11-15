# Copyright 2011-2013 Colin Scott
# Copyright 2013-2014 Zhi Liu
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
import sys
import os.path

sys.path.append(os.path.dirname(__file__) + "/../../..")

from sts.entities import Host, HostInterface
from pox.openflow.software_switch import DpPacketOut, SoftwareSwitch
from pox.lib.addresses import EthAddr, IPAddr
from pox.lib.packet import *

'''IP and MAC of requester host 1 '''
H1_I1_IP = '1.1.1.1'
H1_I1_ETH = '\x01\x01\x01\x01\x01\x01'

'''IP and MAC of receiver host 2, Interface 1'''
H2_I1_IP1 = '2.2.1.1'
H2_I1_ETH = '\x02\x02\x02\x02\x01\x01'
'''Additional IP on the Interface 1'''
H2_I1_IP2 = '2.2.1.2'

'''IP and MAC of receiver host 2, Interface 2 '''
H2_I2_IP = '2.2.2.1'
H2_I2_ETH = '\x02\x02\x02\x02\x02\x01'

'''IP and MAC of receiver host 3 '''
H3_I3_IP = '3.3.3.1'
H3_I3_ETH = '\x03\x03\x03\x03\x03\x01'

class ArpReplyTest(unittest.TestCase):

  def test_none_arp(self):
    '''Receive a none ARP packet and ensure there is no reply'''
    interfaces = [HostInterface(EthAddr(H2_I1_ETH),[IPAddr(H2_I1_IP1),IPAddr(H2_I1_IP2)]),HostInterface(EthAddr(H2_I2_ETH),[IPAddr(H2_I2_IP)])]
    h = Host(interfaces)
    ether = ethernet()
    ether.type = ethernet.IP_TYPE
    ether.dst = EthAddr(H2_I1_ETH)
    ether.src = EthAddr(H1_I1_ETH)
    # Get the action and reply packet
    (action,reply_packet) = h.receive(interfaces[0],ether)
    self.assertTrue(action == h.PKT_RECEIVE_NO_REPLY)
    self.assertTrue(reply_packet == None)

  def test_invalid_arp(self):
    '''Receive a ARP packet that isn't desinated to it and ensure there is no reply'''
    interfaces = [HostInterface(EthAddr(H2_I1_ETH),[IPAddr(H2_I1_IP1),IPAddr(H2_I1_IP2)]),HostInterface(EthAddr(H2_I2_ETH),[IPAddr(H2_I2_IP)])]
    h = Host(interfaces)
    arp_req = arp()
    arp_req.hwsrc = EthAddr(H1_I1_ETH)
    arp_req.hwdst = EthAddr(b"\xff\xff\xff\xff\xff\xff")
    arp_req.opcode = arp.REQUEST
    arp_req.protosrc = IPAddr(H1_I1_IP)
    arp_req.protodst = IPAddr(H3_I3_IP)
    ether = ethernet()
    ether.type = ethernet.ARP_TYPE
    ether.dst = EthAddr(b"\xff\xff\xff\xff\xff\xff")
    ether.src = EthAddr(H1_I1_ETH)
    ether.payload = arp_req
    # Get the action and reply packet
    (action,reply_packet) = h.receive(interfaces[0],ether)
    self.assertTrue(action == h.PKT_RECEIVE_NO_REPLY)
    self.assertTrue(reply_packet == None)

  def test_arp_reply(self):
    '''Receive a valid ARP packet and ensure the correct reply'''
    interfaces = [HostInterface(EthAddr(H2_I1_ETH),[IPAddr(H2_I1_IP1),IPAddr(H2_I1_IP2)]),HostInterface(EthAddr(H2_I2_ETH),[IPAddr(H2_I2_IP)])]
    h = Host(interfaces)
    arp_req = arp()
    arp_req.hwsrc = EthAddr(H1_I1_ETH)
    arp_req.hwdst = EthAddr(b"\xff\xff\xff\xff\xff\xff")
    arp_req.opcode = arp.REQUEST
    arp_req.protosrc = IPAddr(H1_I1_IP)
    arp_req.protodst = IPAddr(H2_I1_IP1)
    ether = ethernet()
    ether.type = ethernet.ARP_TYPE
    ether.dst = EthAddr(b"\xff\xff\xff\xff\xff\xff")
    ether.src = EthAddr(H1_I1_ETH)
    ether.payload = arp_req
    # Get the action and arp reply packet
    (action,arp_reply) = h.receive(interfaces[0],ether)
    self.assertTrue(action == h.PKT_RECEIVE_REPLY)
    self.assertNotEqual(arp_reply,None)
    self.assertEqual(arp_reply.src,EthAddr(H2_I1_ETH))
    self.assertEqual(arp_reply.dst,EthAddr(H1_I1_ETH))
    self.assertEqual(arp_reply.type,ethernet.ARP_TYPE)
    reply_payload = arp_reply.payload
    self.assertEqual(reply_payload.opcode,arp.REPLY)
    self.assertEqual(reply_payload.hwsrc,EthAddr(H2_I1_ETH))
    self.assertEqual(reply_payload.hwdst,EthAddr(H1_I1_ETH))
    self.assertTrue(reply_payload.protosrc == H2_I1_IP1)
    self.assertTrue(reply_payload.protodst == H1_I1_IP)

