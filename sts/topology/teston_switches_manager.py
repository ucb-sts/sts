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
TestON Specific switches manager.
"""

from collections import Iterable
import logging
import re

from sts.entities.teston_entities import TestONOVSSwitch
from sts.entities.teston_entities import TestONPort

from sts.topology.switches_manager import SwitchManagerAbstractClass
from sts.topology.switches_manager import SwitchesManagerPolicy


LOG = logging.getLogger("sts.topology.teston_sw_mgm")


class TestONSwitchesManager(SwitchManagerAbstractClass):

  def __init__(self, teston_mn):
    policy = SwitchesManagerPolicy(
      can_add_switch=False, can_create_switch=False, can_crash_switch=False,
      can_remove_switch=False, can_recover_switch=False)
    super(TestONSwitchesManager, self).__init__(policy)
    self.log = LOG
    self._switches = set()
    self.teston_mn = teston_mn
    self._read_switches()

  def _read_ports(self, node_name):
    response = self.teston_mn.getInterfaces(node_name)
    ports = []
    for line in response.split("\n"):
      if not line.startswith("name="):
        continue
      port_vars = {}
      for var in line.split(","):
        key, value = var.split("=")
        port_vars[key] = value
      # TODO (AH): Read port status
      isUp = port_vars.pop('isUp', True)
      self.log.info("Reading switch port %s(%s)" % (port_vars['name'],
                                                    port_vars['mac']))
      tmp = TestONPort(hw_addr=port_vars['mac'], ips=port_vars['ip'],
                       name=port_vars['name'])
      ports.append((tmp))
    return ports

  def _read_switches(self):
    """
    Read switches from the Mininet driver.
    """
    # Regex patterns to parse dump output
    # Example Switch:
    # <OVSSwitch s1: lo:127.0.0.1,s1-eth1:None,s1-eth2:None,s1-eth3:None pid=5238>
    sw_re = r"<OVSSwitch\s(?P<name>[^:]+)\:\s(?P<ports>([^,]+,)*[^,\s]+)"
    # Get mininet dump
    dump = self.teston_mn.dump().split("\n")
    for line in dump:
      if line.startswith("<OVSSwitch"):
        result = re.search(sw_re, line, re.I)
        name = result.group('name')
        dpid = self.teston_mn.getSwitchDPID(name)
        print name, "DPID", dpid
        self.log.info("Reading switch %s(%s)" % (name, dpid))
        ports = self._read_ports(name)
        switch = TestONOVSSwitch(dpid, name, ports)
        # Todo read connected controllers
        self._switches.add(switch)

  @property
  def switches(self):
    return self._switches

  @property
  def live_switches(self):
    """Returns set of live switches (or what is suppose to live)"""
    return self.switches

  @property
  def failed_switches(self):
    """Returns set of crashed switches (or what is suppose to crashed)"""
    return set()

  @property
  def up_switches(self):
    """
    Returns set of UP switches.
    This method should check the actual status of the switches.
    """
    return self.switches

  @property
  def down_switches(self):
    """
    Returns set of dead switches.
    This method should check the actual status of the switches.
    """
    return set()

  @property
  def live_edge_switches(self):
    """Return the switches which are currently up and can connect to hosts"""
    return set()

  def get_switch(self, switch):
    if switch in self.switches:
      return switch
    for sw in self.switches:
      if sw.name == switch:
        return sw
    return None

  def has_switch(self, switch):
    return self.get_switch(switch) is not None

  def create_switch(self, switch_id, num_ports, can_connect_to_endhosts=True):
    assert self._policy.can_create_switch
    raise NotImplementedError()

  def add_switch(self, switch):
    """Adds switch to be managed by this manager"""
    assert self._policy.can_add_switch
    raise NotImplementedError()

  def remove_switch(self, switch):
    """Removes switch from this manager"""
    assert self._policy.can_remove_switch
    raise NotImplementedError()

  def crash_switch(self, switch):
    assert self._policy.can_crash_switch
    raise NotImplementedError()

  def connect_to_controllers(self, switch, controllers,
                             max_backoff_seconds=512):
    """
    Connect a switch to a list (of one or more) controllers
    """
    assert self._policy.can_connect_to_controllers
    assert switch in self.switches
    if not isinstance(controllers, Iterable):
      controllers = [controllers]
    for controller in controllers:
      switch.connect(controller, max_backoff_seconds=max_backoff_seconds)

  def recover_switch(self, switch, controllers=None):
    assert self._policy.can_recover_switch
    raise NotImplementedError()
