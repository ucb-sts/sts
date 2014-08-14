# Copyright 2011-2013 Colin Scott
# Copyright 2012-2013 Andrew Or
# Copyright 2011-2013 Andreas Wundsam
# Copyright 2012-2013 Sam Whitlock
# Copyright 2012-2012 Kyriakos Zarifis
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

"""
If the user does not specify a topology to test on, use by default a full mesh
of switches, with one host connected to each switch. For example, with N = 3:

              controller
     host1                         host2
       |                            |
     switch1-(1)------------(3)--switch2
        \                       /
        (2)                   (4)
          \                   /
           \                 /
            \               /
             (6)-switch3-(5)
                    |
                  host3
"""

import logging

from pox.openflow.libopenflow_01 import *

from sts.entities import Link, Host, HostInterface, AccessLink

from sts.topology.sts_patch_panel import STSPatchPanel
from sts.topology.sts_switches_manager import STSSwitchesManager
from sts.topology.sts_hosts_manager import STSHostsManager
from sts.topology.controllers_manager import ControllersManager
from sts.topology.connectivity_tracker import ConnectivityTracker
from sts.topology.dp_buffer import BufferedPatchPanel

from sts.topology.base import Topology
from sts.topology.base import TopologyCapabilities


log = logging.getLogger("sts.topology")


class STSTopology(Topology):
  """
  Topology composed of STS entities.
  """
  def __init__(self, create_connection, capabilities=TopologyCapabilities(),
               patch_panel=None, switches_manager=None, hosts_manager=None,
               controllers_manager=None, dp_buffer=None,
               connectivity_tracker=ConnectivityTracker(True)):
    if not patch_panel:
      patch_panel = STSPatchPanel()
    if not switches_manager:
      switches_manager = STSSwitchesManager(create_connection)
    if not hosts_manager:
      hosts_manager = STSHostsManager()
    if not controllers_manager:
      controllers_manager = ControllersManager()
    if not dp_buffer:
      dp_buffer = BufferedPatchPanel([], [], patch_panel.get_other_side)
    is_host = lambda x: isinstance(x, Host)
    is_switch = lambda x: hasattr(x, 'dpid')
    is_network_link =lambda x: isinstance(x, Link)
    is_access_link = lambda x: isinstance(x, AccessLink)
    is_host_interface = lambda x: isinstance(x, HostInterface)
    is_port = lambda x: isinstance(x, ofp_phy_port)
    super(STSTopology, self).__init__(
      capabilities=capabilities, patch_panel=patch_panel,
      switches_manager=switches_manager, hosts_manager=hosts_manager,
      controllers_manager=controllers_manager, dp_buffer=dp_buffer,
      is_host=is_host, is_switch=is_switch, is_network_link=is_network_link,
      is_access_link=is_access_link, is_host_interface=is_host_interface,
      is_port=is_port, connectivity_tracker=connectivity_tracker)


class MeshTopology(STSTopology):
  """
  Mesh Topology composed of STS entities.
  """
  def __init__(self, create_connection, num_switches=3,
               capabilities=TopologyCapabilities(),
               connectivity_tracker=ConnectivityTracker(True)):
    super(MeshTopology, self).__init__(
      create_connection, capabilities=capabilities,
      connectivity_tracker=connectivity_tracker)
    from sts.topology.topology_factory import create_mesh_topology
    create_mesh_topology(self, num_switches=num_switches)


# TODO (AH): implement FatTree factory
FatTree = MeshTopology
