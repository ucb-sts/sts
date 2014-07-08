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
Hosts manager specific TestON Hosts.
"""


import re
import logging

from sts.entities.teston_entities import TestONHost
from sts.entities.teston_entities import TestONHostInterface


from sts.topology.hosts_manager import HostsManagerAbstractClass
from sts.topology.hosts_manager import HostsManagerCapabilities


LOG = logging.getLogger("sts.topology.teston_h_mgm")


class TestONHostsManager(HostsManagerAbstractClass):
  """
  Hosts manager specific TestON Hosts.
  """
  def __init__(self, teston_mn):
    capabilities = HostsManagerCapabilities(
      can_crash_host=False, can_recover_host=False, can_create_host=False,
      can_remove_host=False, can_create_interface=False)
    super(TestONHostsManager, self).__init__(capabilities)
    self.log = LOG
    self._hosts = set()
    self.teston_mn = teston_mn
    self._read_nodes()

  def _read_interfaces(self, node_name):
    """
    Read host interfaces from Mininet Driver
    """
    response = self.teston_mn.getInterfaces(node_name)
    interfaces = []
    for line in response.split("\n"):
      if not line.startswith("name="):
        continue
      vars = {}
      for var in line.split(","):
        key, value = var.split("=")
        vars[key] = value
      # TODO (AH): Read port status
      isUp = vars.pop('isUp', True)
      self.log.info("Reading host port %s(%s)" % (vars['name'], vars['mac']))
      tmp = TestONHostInterface(hw_addr=vars['mac'], ips=vars['ip'],
                                name=vars['name'])
      interfaces.append((tmp))
    return interfaces

  def _read_nodes(self):
    """
    Read hosts from Mininet.
    """
    # Regex patterns to parse dump output
    # Example host: <Host h1: h1-eth0:10.0.0.1 pid=5227>
    host_re = r"<Host\s(?P<name>[^:]+)\:\s(?P<ifname>[^:]+)\:(?P<ip>[^\s]+)"
    # Get mininet dump
    dump = self.teston_mn.dump().split("\n")
    for line in dump:
      if line.startswith("<Host"):
        result = re.search(host_re, line)
        host_name = result.group('name')
        interfaces = self._read_interfaces(host_name)
        host = TestONHost(interfaces, name=host_name)
        self._hosts.add(host)

  @property
  def hosts(self):
    return self._hosts

  @property
  def live_hosts(self):
    """Returns set of live hosts (or what is suppose to live)"""
    return self._hosts

  @property
  def failed_hosts(self):
    """Returns set of crashed hosts (or what is suppose to crashed)"""
    return set()

  @property
  def up_hosts(self):
    """
    Returns set of UP hosts.
    This method should check the actual status of the hosts.
    """
    assert self.capabilities.can_get_up_hosts
    return self._hosts

  @property
  def down_hosts(self):
    """
    Returns set of dead hosts.
    This method should check the actual status of the hosts.
    """
    assert self.capabilities.can_get_down_hosts
    return set()

  def get_host(self, host):
    if host in self.hosts:
      return host
    for h in self.hosts:
      if h.name == host:
        return h
    return None

  def has_host(self, host):
    return self.get_host(host) is not None

  def create_host(self, hid, name=None, interfaces=None):
    assert self.capabilities.can_create_host
    raise NotImplementedError()

  def create_interface(self, hw_addr, ip_or_ips=None, name=None):
    assert self.capabilities.can_create_interface
    raise NotImplementedError()

  def add_host(self, host):
    """Adds host to be managed by this manager"""
    assert self.capabilities.can_add_host
    raise NotImplementedError()

  def remove_host(self, host):
    """Removes host from this manager"""
    assert self.capabilities.can_remove_host
    raise NotImplementedError()

  def crash_host(self, host):
    assert self.capabilities.can_crash_host
    raise NotImplementedError()

  def recover_host(self, host):
    assert self.capabilities.can_recover_host
    raise NotImplementedError()
