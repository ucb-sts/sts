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


from collections import Iterable

from sts.util.capability import Capabilities

from sts.entities.controllers import ControllerState


class ControllersManagerCapabilities(Capabilities):
  """
  Defines the capabilities of what can/cannot do for the ControllersManager.
  """
  def __init__(self, can_create_controller=True, can_add_controller=True,
               can_remove_controller=True, can_crash_controller=True,
               can_recover_controller=True, can_partition_control_plane=True,
               can_get_up_controllers=True, can_get_down_controllers=True,
               can_block_peers=True, can_unblock_peers=True):
    super(ControllersManagerCapabilities, self).__init__()
    self._can_create_controller = can_create_controller
    self._can_add_controller = can_add_controller
    self._can_remove_controller = can_remove_controller
    self._can_crash_controller = can_crash_controller
    self._can_recover_controller = can_recover_controller
    self._can_partition_control_plane = can_partition_control_plane
    self._can_get_up_controllers = can_get_up_controllers
    self._can_get_down_controllers = can_get_down_controllers
    self._can_block_peers = can_block_peers
    self._can_unblock_peers = can_unblock_peers

  @property
  def can_create_controller(self):
    """Returns True if new controllers created by this manager."""
    return self._can_create_controller

  @property
  def can_add_controller(self):
    """
    Returns True if controllers (created somewhere else) can be added to the
    manager.
    """
    return self._can_add_controller

  @property
  def can_remove_controller(self):
    """Returns True if controllers can be removed from the manager."""
    return self._can_remove_controller

  @property
  def can_crash_controller(self):
    """
    Returns True if the controllers in the topology can be shutdown.
    """
    return self._can_crash_controller

  @property
  def can_recover_controller(self):
    """
    Returns True if the controller in the manager can recovered after
    fail event.
    """
    return self._can_recover_controller

  @property
  def can_partition_control_plane(self):
    """
    Returns True if the controller plane can be partitioned
    (losing connectivity between controllers)
    """
    return self._can_partition_control_plane

  @property
  def can_get_up_controllers(self):
    """
    Returns True if the controllers manager can check the actual status of the
    controllers and returns the ones that are actually down.
    """
    return self._can_get_up_controllers

  @property
  def can_get_down_controllers(self):
    """
    Returns True if the controllers manager can check the actual status of the
    controllers and returns the ones that are actually down.
    """
    return self._can_get_down_controllers

  @property
  def can_block_peers(self):
    """
    Returns True if the controllers manager can partition the control plane.
    """
    return self._can_block_peers

  @property
  def can_unblock_peers(self):
    """
    Returns True if the controllers manager can un-partition the control plane.
    """
    return self._can_unblock_peers


class ControllersManager(object):
  """
  Manages set of Controllers.
  """
  def __init__(self, capabilities=ControllersManagerCapabilities()):
    self.capabilities = capabilities
    self._live_controllers = set()
    self._failed_controllers = set()

  @property
  def controllers(self):
    """Returns set of all controllers managed by this manager"""
    controllers = set()
    controllers = controllers.union(self.live_controllers)
    controllers = controllers.union(self.failed_controllers)
    return controllers

  @property
  def live_controllers(self):
    """
    Returns set of all live (not killed) controllers managed by this manager
    """
    return self._live_controllers

  @property
  def failed_controllers(self):
    """Returns set of crashed controllers (or what is suppose to crashed)"""
    return self._failed_controllers

  @property
  def up_controllers(self):
    """
    Returns set of UP controllers.
    This method should check the actual status of the controllers.
    """
    assert self.capabilities.can_get_up_controllers
    controllers = set()
    for controller in self.controllers:
      print "CHECK STATUS", controller.check_status(None)
      if controller.check_status(None) == ControllerState.ALIVE:
        controllers.add(controller)
    return controllers

  @property
  def down_controllers(self):
    """
    Returns set of dead controllers.
    This method should check the actual status of the controllers.
    """
    assert self.capabilities.can_get_down_controllers
    controllers = set()
    for controller in self.controllers:
      if controller.check_status(None) == ControllerState.DEAD:
        controllers.add(controller)
    return controllers

  def create_controller(self, ip_address, port):
    """
    Creates new controller. The controller is not added to the manager.
    See: `add_controller`
    """
    assert self.capabilities.can_create_controller
    raise NotImplementedError()

  def add_controller(self, controller):
    """Adds a controller instance to be managed by this manager"""
    assert self.capabilities.can_add_controller
    assert controller not in self.controllers
    if controller.state == ControllerState.ALIVE:
      self._live_controllers.add(controller)
    else:
      self._failed_controllers.add(controller)

  def remove_controller(self, controller):
    """Remove a controller instance from being managed by this manager"""
    assert self.capabilities.can_remove_controller
    assert controller in self.controllers
    if controller in self.live_controllers:
      self._live_controllers.remove(controller)
    else:
      self._failed_controllers.remove(controller)

  def crash_controller(self, controller):
    """Kill the controller."""
    assert self.capabilities.can_crash_controller
    assert controller in self.controllers
    controller.kill()
    if controller in self._live_controllers:
      self._live_controllers.remove(controller)
    self._failed_controllers.add(controller)

  def recover_controller(self, controller):
    """Restart the controller."""
    assert self.capabilities.can_recover_controller
    assert controller in self.controllers
    controller.start()
    if controller in self._failed_controllers:
      self._failed_controllers.remove(controller)
    self._live_controllers.add(controller)

  def block_peers(self, controller, peers):
    """Blocks connectivity between the controller and set of peers"""
    assert self.capabilities.can_block_peers
    assert controller in self.controllers
    if not isinstance(peers, Iterable):
      peers = [peers]
    for peer in peers:
      controller.block_peer(peer)

  def unblock_peers(self, controller, peers):
    """Restores connectivity between the controller and set of peers"""
    assert self.capabilities.can_unblock_peers
    assert controller in self.controllers
    if not isinstance(peers, Iterable):
      peers = [peers]
    for peer in peers:
      controller.unblock_peer(peer)
