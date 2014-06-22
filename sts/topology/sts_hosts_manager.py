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
Hosts manager specific STS Hosts.
"""


from sts.entities.hosts import Host
from sts.entities.hosts import HostInterface

from sts.topology.hosts_manager import HostsManagerAbstractClass
from sts.topology.hosts_manager import HostsManagerPolicy


class STSHostsManager(HostsManagerAbstractClass):
  """
  Hosts manager specific STS Hosts.
  """
  def __init__(self, policy=HostsManagerPolicy(can_crash_host=False,
                                               can_recover_host=False)):
    super(STSHostsManager, self).__init__(policy)
    self._live_hosts = set()
    self._failed_hosts = set()

  @property
  def live_hosts(self):
    """Returns set of live hosts (or what is suppose to live)"""
    return self._live_hosts

  @property
  def failed_hosts(self):
    """Returns set of crashed hosts (or what is suppose to crashed)"""
    return self._failed_hosts

  @property
  def up_hosts(self):
    """
    Returns set of UP hosts.
    This method should check the actual status of the hosts.
    """
    assert self.policy.can_get_up_hosts
    return self.live_hosts

  @property
  def down_hosts(self):
    """
    Returns set of dead hosts.
    This method should check the actual status of the hosts.
    """
    assert self.policy.can_get_down_hosts
    return self.failed_hosts

  def create_host(self, hid, name=None, interfaces=None):
    assert self.policy.can_create_host
    host = Host(interfaces=interfaces, name=name, hid=hid)
    return host

  def create_interface(self, hw_addr, ip_or_ips=None, name=None):
    assert self.policy.can_create_interface
    interface = HostInterface(hw_addr=hw_addr, ip_or_ips=ip_or_ips, name=name)
    return interface

  def add_host(self, host):
    """Adds host to be managed by this manager"""
    assert self.policy.can_add_host
    self._live_hosts.add(host)
    return host

  def remove_host(self, host):
    """Removes host from this manager"""
    assert self.policy.can_remove_host
    if host in self._live_hosts:
      self._live_hosts.remove(host)
    elif host in self._failed_hosts:
      self._failed_hosts.remove(host)
    else:
      raise ValueError("Host: '%s' is not managed by this manager" % host)

  def crash_host(self, host):
    assert self.policy.can_crash_host
    raise NotImplementedError()

  def recover_host(self, host):
    assert self.policy.can_recover_host
    raise NotImplementedError()
