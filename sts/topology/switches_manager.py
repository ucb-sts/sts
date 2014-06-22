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
Manages switches in the network.
"""


import abc

from sts.util.policy import Policy


class SwitchManagerPolicy(Policy):
  """
  Defines the policy of what can/cannot do for the SwitchManager.
  """
  def __init__(self, can_create_switch=True, can_add_switch=True,
               can_remove_switch=True, can_crash_switch=True,
               can_recover_switch=True, can_get_up_switches=True,
               can_get_down_switches=True):
    super(SwitchManagerPolicy, self).__init__()
    self._can_create_switch = can_create_switch
    self._can_add_switch = can_add_switch
    self._can_remove_switch = can_remove_switch
    self._can_crash_switch = can_crash_switch
    self._can_recover_switch = can_recover_switch
    self._can_get_up_switches = can_get_up_switches
    self._can_get_down_switches = can_get_down_switches

  @property
  def can_create_switch(self):
    """Returns True if switches created by this manager."""
    return self._can_create_switch

  @property
  def can_add_switch(self):
    """Returns True if switches can be added to the manager."""
    return self._can_add_switch

  @property
  def can_remove_switch(self):
    """Returns True if switches can be removed from the manager."""
    return self._can_remove_switch

  @property
  def can_crash_switch(self):
    """
    Returns True if the switches in the topology can be shutdown.
    """
    return self._can_crash_switch

  @property
  def can_recover_switch(self):
    """
    Returns True if the switches in the manager can recovered after fail event.
    """
    return self._can_recover_switch

  @property
  def can_get_up_switches(self):
    """
    Returns True if the switches manager can check the actual status of the
    switches and returns the ones that are actually UP.
    """
    return self._can_get_up_switches

  @property
  def can_get_down_switches(self):
    """
    Returns True if the switches manager can check the actual status of the
    switches and returns the ones that are actually UP.
    """
    return self._can_get_down_switches


class SwitchManagerAbstractClass(object):
  """
  Manages the switches in the network. This is meant to provide the mechanisms
  to control switches for the higher level policy controllers (e.g. Fuzzer,
  and Replayer).
  """
  __metaclass__ = abc.ABCMeta

  def __init__(self, policy=SwitchManagerPolicy()):
    self._policy = policy

  @abc.abstractproperty
  def live_switches(self):
    """Returns set of live switches (or what is suppose to live)"""
    raise NotImplementedError()

  @abc.abstractproperty
  def failed_switches(self):
    """Returns set of crashed switches (or what is suppose to crashed)"""
    raise NotImplementedError()

  @abc.abstractproperty
  def up_switches(self):
    """
    Returns set of UP switches.
    This method should check the actual status of the switches.
    """
    raise NotImplementedError()

  @abc.abstractproperty
  def down_switches(self):
    """
    Returns set of dead switches.
    This method should check the actual status of the switches.
    """
    raise NotImplementedError()

  @abc.abstractproperty
  def live_edge_switches(self):
    """Return the switches which are currently up and can connect to hosts"""
    raise NotImplementedError()

  @abc.abstractmethod
  def create_switch(self, switch_id, num_ports, can_connect_to_endhosts=True):
    """
    Creates new switch.
    The switch is not added by default the manager.
    See: `add_switch`
    """
    raise NotImplementedError()

  @abc.abstractmethod
  def add_switch(self, switch):
    """Adds switch to be managed by this manager"""
    raise NotImplementedError()

  @abc.abstractmethod
  def remove_switch(self, switch):
    """Removes switch from this manager"""
    raise NotImplementedError()

  @abc.abstractmethod
  def crash_switch(self, switch):
    """Brings the switch down"""
    raise NotImplementedError()

  @abc.abstractmethod
  def recover_switch(self, switch, controllers=None):
    """Reboot previously crashed switch"""
    raise NotImplementedError()

  @abc.abstractmethod
  def connect_to_controllers(self, switch, controllers):
    """Connects a switch to a list (of one or more) controllers"""
    raise NotImplementedError()
