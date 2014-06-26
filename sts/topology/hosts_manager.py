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
Hosts manager take care of managing host in the data plane.
"""


import abc
import random

from sts.util.policy import Policy


def mac_addresses_generator(max_addresses=None):
  """
  Generate random MAC addresses.
  Stops when max_addresses is reached, or goes forever if max_addresses is None
  """
  num = 0
  while max_addresses is None or num < max_addresses:
    num += 1
    mac = [0xE0]
    for _ in range(5):
      mac.append(random.randint(0x00, 0xff))
    yield ':'.join(["%02x" % x for x in mac])


def ip_addresses_generator(max_addresses=None):
  """
  Generate random IP addresses.
  Stops when max is reached, or goes forever if max is None
  """
  num = 0
  while max_addresses is None or num < max_addresses:
    num += 1
    ip_address = [10]
    for _ in range(3):
      ip_address.append(random.randint(0, 255))
    yield '.'.join(["%d" % x for x in ip_address])


def interface_names_generator(start=0, max_names=None):
  """
  Generate sequential interface names starting from eth0, eth1, ...
  Stops when max_names is reached, or goes forever if max_names is None
  """
  num = start
  while max_names is None or num < max_names:
    name = "eth%d" % num
    num += 1
    yield name


class HostsManagerPolicy(Policy):
  """
  Defines the policy of what can/cannot do for the HostsManager.
  """
  def __init__(self, can_create_host=True, can_create_interface=True,
               can_add_host=True, can_remove_host=True, can_crash_host=True,
               can_recover_host=True, can_get_up_hosts=True,
               can_get_down_hosts=True):
    super(HostsManagerPolicy, self).__init__()
    self._can_create_host = can_create_host
    self._can_create_interface = can_create_interface
    self._can_add_host = can_add_host
    self._can_remove_host = can_remove_host
    self._can_crash_host = can_crash_host
    self._can_recover_host = can_recover_host
    self._can_get_up_hosts = can_get_up_hosts
    self._can_get_down_hosts = can_get_down_hosts

  @property
  def can_create_host(self):
    """Returns True if hosts can be created by this manager."""
    return self._can_create_host

  @property
  def can_create_interface(self):
    """Returns True if host interfaces can be created by this manager."""
    return self._can_create_interface

  @property
  def can_add_host(self):
    """Returns True if hosts can be added to the manager."""
    return self._can_add_host

  @property
  def can_remove_host(self):
    """Returns True if hosts can be removed from the manager."""
    return self._can_remove_host

  @property
  def can_crash_host(self):
    """
    Returns True if the hosts in the topology can be shutdown.
    """
    return self._can_crash_host

  @property
  def can_recover_host(self):
    """
    Returns True if the hosts in the manager can recovered after fail event.
    """
    return self._can_recover_host

  @property
  def can_get_up_hosts(self):
    """
    Returns True if the hosts manager can check the actual status of the hosts
    and returns the ones that are actually UP.
    """
    return self._can_get_up_hosts

  @property
  def can_get_down_hosts(self):
    """
    Returns True if the hosts manager can check the actual status of the hosts
    and returns the ones that are actually UP.
    """
    return self._can_get_down_hosts


class HostsManagerAbstractClass(object):
  """
  Manages the hosts in the network. This is meant to provide the mechanisms
  to control hosts for the higher level policy controllers (e.g. Fuzzer,
  and Replayer).
  """
  __metaclass__ = abc.ABCMeta

  def __init__(self, policy):
    self.policy = policy

  @abc.abstractproperty
  def hosts(self):
    """Returns a set of all hosts managed by this manager."""
    raise NotImplementedError()

  @abc.abstractproperty
  def live_hosts(self):
    """Returns set of live hosts (or what is suppose to live)"""
    raise NotImplementedError()

  @abc.abstractproperty
  def failed_hosts(self):
    """Returns set of crashed hosts (or what is suppose to crashed)"""
    raise NotImplementedError()

  @abc.abstractproperty
  def up_hosts(self):
    """
    Returns set of UP hosts.
    This method should check the actual status of the hosts.
    """
    raise NotImplementedError()

  @abc.abstractproperty
  def down_hosts(self):
    """
    Returns set of dead hosts.
    This method should check the actual status of the hosts.
    """
    raise NotImplementedError()

  @abc.abstractmethod
  def create_host(self, hid, name=None, interfaces=None):
    """
    Create new Host.
    Note: the host is not added by default to be managed. See `add_host`.
    """
    raise NotImplementedError()

  @abc.abstractmethod
  def create_interface(self, hw_addr, ip_or_ips=None, name=None):
    """
    Creates interface for host.
    The interface is not attached to any host after calling this method
    """
    raise NotImplementedError()

  def create_host_with_interfaces(self, hid, name, num_interfaces,
                                  mac_generator, ip_generator,
                                  interface_name_generator):
    """
    Creates new host with the specified number of interfaces.

    Args:
      - hid: Host unique ID
      - name: human readable host name
      - num_interfaces: the total number of interfaces to be created
      - mac_generator: generates mac address for each interface
      - ip_generator: generates IP address for each interface
      - interface_name_generator: generates human readable names
    """
    assert self.policy.can_create_host
    assert self.policy.can_create_interface
    interfaces = []
    for iface_no in range(num_interfaces):
      hw_addr = mac_generator.next()
      ip_addr = ip_generator.next()
      iface_name = interface_name_generator.next()
      iface = self.create_interface(hw_addr=hw_addr, ip_or_ips=ip_addr,
                                    name=iface_name)
      interfaces.append(iface)
    host = self.create_host(hid=hid, name=name, interfaces=interfaces)
    return host

  @abc.abstractmethod
  def add_host(self, host):
    """Adds host to be managed by this manager"""
    raise NotImplementedError()

  @abc.abstractmethod
  def remove_host(self, host):
    """Removes host from this manager"""
    raise NotImplementedError()

  @abc.abstractmethod
  def crash_host(self, host):
    """Shutdown a host."""
    raise NotImplementedError()

  @abc.abstractmethod
  def recover_host(self, host):
    """Brings host back up"""
    raise NotImplementedError()
