# Copyright 2011-2013 Colin Scott
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
import os
import time

sys.path.append(os.path.dirname(__file__) + "/../../..")

from sts.controller_manager import LocalControllerPatchPanel
from sts.util.network_namespace import *

class LocalControllerPatchPanelTest(unittest.TestCase):
  def test_without_host_ips_set(self):
    if os.geteuid() != 0: # Must be run as root
      return

    # Have two net_ns processes ping eachother, and verify that the pings go through.
    p = LocalControllerPatchPanel(pass_through=True)
    ping1_addr = "192.168.1.3"
    ping2_addr = "192.168.1.4"
    (ping1_proc, ping1_eth_addr, ping1_host_device) = launch_namespace("ping -c 1 %s" % ping2_addr, ping1_addr, 1)
    ping1_pcap = bind_pcap(ping1_host_device)
    p.register_controller(ping1_eth_addr, ping1_pcap)

    (ping2_proc, ping2_eth_addr, ping2_host_device) = launch_namespace("ping -c 1 %s" % ping1_addr, ping2_addr, 2)
    ping2_pcap = bind_pcap(ping2_host_device)
    p.register_controller(ping2_eth_addr, ping2_pcap)

    # TODO(cs): this number is super finicky. Figure out a better way to
    # ensure that all packets have been processed.
    for i in xrange(1000):
      p.process_all_incoming_traffic()
      if i % 33 == 0:
        time.sleep(0.01)

    # TODO(cs): when buffering is implemented, verify that at least 2 ICMP
    # replies have been buffered.
