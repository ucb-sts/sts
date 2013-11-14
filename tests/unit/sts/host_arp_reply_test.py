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

class ArpReplyTest(unittest.TestCase):

  def test_arp_reply(self):
    REQ_IP = '1.1.1.1'
    REQ_ETH_ADDR = '\x01\x01\x01\x01\x01\x01'
    REPLY_IP = '2.2.2.2'
    REPLY_ETH_ADDR = '\x02\x02\x02\x02\x02\x02'
    interface = HostInterface(EthAddr(REPLY_ETH_ADDR),IPAddr(REPLY_IP)) 
    h = Host(interface)
    arp_req = arp()
    arp_req.hwsrc = EthAddr(REQ_ETH_ADDR)
    arp_req.hwdst = EthAddr(b"\xff\xff\xff\xff\xff\xff")
    arp_req.opcode = arp.REQUEST
    arp_req.protosrc = IPAddr(REQ_IP)
    arp_req.protodst = IPAddr(REPLY_IP)
    ether = ethernet()
    ether.type = ethernet.ARP_TYPE
    ether.dst = EthAddr(b"\xff\xff\xff\xff\xff\xff")
    ether.src = EthAddr(REQ_ETH_ADDR)
    ether.payload = arp_req
    arp_reply = h.checkARPReply(interface,ether)
    self.assertEqual(arp_reply.src,EthAddr(REPLY_ETH_ADDR))
    self.assertEqual(arp_reply.dst,EthAddr(REQ_ETH_ADDR))
    self.assertEqual(arp_reply.type,ethernet.ARP_TYPE)
    reply_payload = arp_reply.payload
    self.assertEqual(reply_payload.opcode,arp.REPLY)
    self.assertEqual(reply_payload.hwsrc,EthAddr(REPLY_ETH_ADDR))
    self.assertEqual(reply_payload.hwdst,EthAddr(REQ_ETH_ADDR))
    self.assertTrue(reply_payload.protosrc == REPLY_IP)
    self.assertTrue(reply_payload.protodst == REQ_IP)
    h.receive(interface,ether)

