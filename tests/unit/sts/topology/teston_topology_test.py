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

import mock
import unittest


from sts.topology.teston_topology import TestONTopology


class TestONSwitchesManagerTest(unittest.TestCase):
  def _mock_teston(self):
    mininet_dump = """<Host h1: h1-eth0:10.0.0.1 pid=26370>
<Host h2: h2-eth0:10.0.0.2 pid=26371>
<Host h3: h3-eth0:10.0.0.3 pid=26372>
<Host h4: h4-eth0:10.0.0.4 pid=26373>
<Host h5: h5-eth0:10.0.0.5 pid=26374>
<Host h6: h6-eth0:10.0.0.6 pid=26375>
<Host h7: h7-eth0:10.0.0.7 pid=26376>
<Host h8: h8-eth0:10.0.0.8 pid=26377>
<Host h9: h9-eth0:10.0.0.9 pid=26378>
<OVSSwitch s1: lo:127.0.0.1,s1-eth1:None,s1-eth2:None,s1-eth3:None pid=26381>
<OVSSwitch s2: lo:127.0.0.1,s2-eth1:None,s2-eth2:None,s2-eth3:None,s2-eth4:None pid=26386>
<OVSSwitch s3: lo:127.0.0.1,s3-eth1:None,s3-eth2:None,s3-eth3:None,s3-eth4:None pid=26391>
<OVSSwitch s4: lo:127.0.0.1,s4-eth1:None,s4-eth2:None,s4-eth3:None,s4-eth4:None pid=26396>
<RemoteController c0: 127.0.0.1:6633 pid=26363>
    """

    h1_eth0 = """, i.isUp()) for i in h1.intfs.values()])p=%s" % (i.name, i.MAC(), i.IP()
name=h1-eth0,mac=00:00:00:00:00:01,ip=10.0.0.1,isUp=True
mininet>
"""


    h2_eth0 = """, i.isUp()) for i in h2.intfs.values()])p=%s" % (i.name, i.MAC(), i.IP()
name=h2-eth0,mac=00:00:00:00:00:02,ip=10.0.0.2,isUp=True
mininet>
"""

    h3_eth0 = """, i.isUp()) for i in h3.intfs.values()])p=%s" % (i.name, i.MAC(), i.IP()
name=h3-eth0,mac=00:00:00:00:00:03,ip=10.0.0.3,isUp=True
mininet>
"""
    h4_eth0 = """, i.isUp()) for i in h4.intfs.values()])p=%s" % (i.name, i.MAC(), i.IP()
name=h4-eth0,mac=00:00:00:00:00:04,ip=10.0.0.4,isUp=True
mininet>
"""
    h5_eth0 = """, i.isUp()) for i in h5.intfs.values()])p=%s" % (i.name, i.MAC(), i.IP()
name=h5-eth0,mac=00:00:00:00:00:05,ip=10.0.0.5,isUp=True
mininet>
"""
    h6_eth0 = """, i.isUp()) for i in h6.intfs.values()])p=%s" % (i.name, i.MAC(), i.IP()
name=h6-eth0,mac=00:00:00:00:00:06,ip=10.0.0.6,isUp=True
mininet>
"""
    h7_eth0 = """, i.isUp()) for i in h7.intfs.values()])p=%s" % (i.name, i.MAC(), i.IP()
name=h7-eth0,mac=00:00:00:00:00:07,ip=10.0.0.7,isUp=True
mininet>
"""
    h8_eth0 = """, i.isUp()) for i in h8.intfs.values()])p=%s" % (i.name, i.MAC(), i.IP()
name=h8-eth0,mac=00:00:00:00:00:08,ip=10.0.0.8,isUp=True
mininet>
"""
    h9_eth0 = """, i.isUp()) for i in h9.intfs.values()])p=%s" % (i.name, i.MAC(), i.IP()
name=h9-eth0,mac=00:00:00:00:00:09,ip=10.0.0.9,isUp=True
mininet>
"""
    s1_ports = """
, i.isUp()) for i in s1.intfs.values()])p=%s" % (i.name, i.MAC(), i.IP()
name=lo,mac=None,ip=127.0.0.1,isUp=True
name=s1-eth1,mac=ce:c5:1e:ee:36:b4,ip=None,isUp=True
name=s1-eth2,mac=de:29:d4:1c:4d:a1,ip=None,isUp=True
name=s1-eth3,mac=b6:2e:aa:c3:2e:0d,ip=None,isUp=True
mininet>
    """

    s2_ports = """
, i.isUp()) for i in s2.intfs.values()])p=%s" % (i.name, i.MAC(), i.IP()
name=lo,mac=None,ip=127.0.0.1,isUp=True
name=s2-eth1,mac=3e:cd:cd:bc:d0:bc,ip=None,isUp=True
name=s2-eth2,mac=76:ea:fc:0c:dd:f2,ip=None,isUp=True
name=s2-eth3,mac=5e:2b:cc:f5:a2:e5,ip=None,isUp=True
name=s2-eth4,mac=42:b2:02:de:49:5c,ip=None,isUp=True
mininet>
    """

    s3_ports = """
, i.isUp()) for i in s3.intfs.values()])p=%s" % (i.name, i.MAC(), i.IP()
name=lo,mac=None,ip=127.0.0.1,isUp=True
name=s3-eth1,mac=66:c8:b8:3a:d5:c0,ip=None,isUp=True
name=s3-eth2,mac=16:97:73:d7:43:8a,ip=None,isUp=True
name=s3-eth3,mac=96:46:1e:cc:26:36,ip=None,isUp=True
name=s3-eth4,mac=2a:d3:7e:8a:22:72,ip=None,isUp=True
mininet>
    """

    s4_ports = """
, i.isUp()) for i in s4.intfs.values()])p=%s" % (i.name, i.MAC(), i.IP()
name=lo,mac=None,ip=127.0.0.1,isUp=True
name=s4-eth1,mac=4a:82:af:b3:dd:bf,ip=None,isUp=True
name=s4-eth2,mac=fa:30:f4:61:c7:c2,ip=None,isUp=True
name=s4-eth3,mac=c2:8f:63:d1:27:f9,ip=None,isUp=True
name=s4-eth4,mac=5e:c8:ae:c9:2c:fc,ip=None,isUp=True
mininet>
    """

    def getInterfaces(name):
      if name == 'h1':
        return h1_eth0
      elif name == 'h2':
        return h2_eth0
      elif name == 'h3':
        return h3_eth0
      elif name == 'h4':
        return h4_eth0
      elif name == 'h5':
        return h5_eth0
      elif name == 'h6':
        return h6_eth0
      elif name == 'h7':
        return h7_eth0
      elif name == 'h8':
        return h8_eth0
      elif name == 'h9':
        return h9_eth0
      if name == 's1':
        return s1_ports
      elif name == 's2':
        return s2_ports
      elif name == 's3':
        return s3_ports
      elif name == 's4':
        return s4_ports
      else:
        raise ValueError("No ports were mocked for node: %s" % name)

    mininet_net = """mininet> net
h1 h1-eth0:s2-eth1
h2 h2-eth0:s2-eth2
h3 h3-eth0:s2-eth3
h4 h4-eth0:s3-eth1
h5 h5-eth0:s3-eth2
h6 h6-eth0:s3-eth3
h7 h7-eth0:s4-eth1
h8 h8-eth0:s4-eth2
h9 h9-eth0:s4-eth3
s1 lo:  s1-eth1:s2-eth4 s1-eth2:s3-eth4 s1-eth3:s4-eth4
s2 lo:  s2-eth1:h1-eth0 s2-eth2:h2-eth0 s2-eth3:h3-eth0 s2-eth4:s1-eth1
s3 lo:  s3-eth1:h4-eth0 s3-eth2:h5-eth0 s3-eth3:h6-eth0 s3-eth4:s1-eth2
s4 lo:  s4-eth1:h7-eth0 s4-eth2:h8-eth0 s4-eth3:h9-eth0 s4-eth4:s1-eth3
"""

    mn_driver = mock.Mock(name='TestONMininetDriver')
    mn_driver.net.return_value = mininet_net
    mn_driver.dump.return_value = mininet_dump
    mn_driver.getInterfaces.side_effect = getInterfaces
    return mn_driver

  def test_read_topology(self):
    # Arrange
    mn_driver = self._mock_teston()
    # Act
    topo = TestONTopology(mn_driver, None)
    # Assert
