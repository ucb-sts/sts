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
STS Specific switches manager.
"""

import logging

from pox.lib.addresses import EthAddr
from pox.openflow.libopenflow_01 import ofp_phy_port

from sts.entities.sts_entities import FuzzSoftwareSwitch
from sts.util.console import msg

from sts.topology.switches_manager import SwitchManagerAbstractClass
from sts.topology.switches_manager import SwitchesManagerPolicy


LOG = logging.getLogger("sts.topology.sw_mgm")


class STSSwitchesManager(SwitchManagerAbstractClass):
  def __init__(self, policy=SwitchesManagerPolicy()):
    super(STSSwitchesManager, self).__init__(policy)
    self.log = LOG
    self.msg = msg
    self._failed_switches = set()
    self._live_switches = set()

  @property
  def switches(self):
    switches = set()
    switches = switches.union(self.live_switches)
    switches = switches.union(self.failed_switches)
    return switches

  @property
  def live_switches(self):
    """Returns set of live switches (or what is suppose to live)"""
    return self._live_switches

  @property
  def failed_switches(self):
    """Returns set of crashed switches (or what is suppose to crashed)"""
    return self._failed_switches

  @property
  def up_switches(self):
    """
    Returns set of UP switches.
    This method should check the actual status of the switches.
    """
    return self.live_switches

  @property
  def down_switches(self):
    """
    Returns set of dead switches.
    This method should check the actual status of the switches.
    """
    return self.failed_switches

  @property
  def live_edge_switches(self):
    """Return the switches which are currently up and can connect to hosts"""
    edge_switches = set(
      [sw for sw in self.live_switches if sw.can_connect_to_endhosts])
    return edge_switches - self.failed_switches

  def create_switch(self, switch_id, num_ports, can_connect_to_endhosts=True):
    assert self._policy.can_create_switch
    ports = []
    for port_no in range(1, num_ports + 1):
      eth_addr = EthAddr("00:00:00:00:%02x:%02x" % (switch_id, port_no))
      port = ofp_phy_port(port_no=port_no, hw_addr=eth_addr,
                          name="eth%d" % port_no)
      # monkey patch an IP address onto the port for anteater purposes
      port.ip_addr = "1.1.%d.%d" % (switch_id, port_no)
      ports.append(port)

    switch = FuzzSoftwareSwitch(dpid=switch_id,
                                name="s%d" % switch_id,
                                ports=ports,
                                can_connect_to_endhosts=can_connect_to_endhosts)
    return switch

  def add_switch(self, switch):
    """Adds switch to be managed by this manager"""
    assert self._policy.can_add_switch
    assert switch not in self.switches
    self._live_switches.add(switch)

  def remove_switch(self, switch):
    """Removes switch from this manager"""
    assert self._policy.can_remove_switch
    assert switch in self.switches
    if switch in self.live_switches:
      self._live_switches.remove(switch)
    elif switch in self.failed_switches:
      self._failed_switches.remove(switch)
    else:
      raise ValueError("Switch is not in live nor failed switches list: '%s'" %
                       str(switch))

  def crash_switch(self, switch):
    assert self._policy.can_crash_switch
    switch.fail()
    if switch in self._live_switches:
      self._live_switches.remove(switch)
    self._failed_switches.add(switch)

  def connect_to_controllers(self, switch, controllers):
    """
    Connect a switch to a list (of one or more) controllers
    """
    raise NotImplementedError()

  def recover_switch(self, switch, controllers=None):
    """Reboot previously crashed switch"""
    # TODO CONNECT
    assert self._policy.can_recover_switch
    self.msg.event("Rebooting switch %s" % str(switch))
    if controllers is None:
      controllers = set()
    if switch not in self.failed_switches:
      self.log.warn("Switch %s not currently down. (Currently down: %s)" %
                    (str(switch), str(self.failed_switches)))
    connected_to_at_least_one = switch.recover(down_controller_ids=controllers)
    if connected_to_at_least_one:
      self._failed_switches.remove(switch)
      self._live_switches.add(switch)
    return connected_to_at_least_one
