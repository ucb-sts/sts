# Copyright 2011-2013 Colin Scott
# Copyright 2011-2013 Andreas Wundsam
# Copyright 2012-2013 Sam Whitlock
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

''' Convenience object for encapsulating and interacting with Controller processes '''

from sts.entities import ControllerState
from sts.util.console import msg

class ControllerManager(object):
  ''' Encapsulate a list of controllers objects '''
  def __init__(self, controllers, simulation=None):
    self.cid2controller = {
      controller.cid : controller
      for controller in controllers
    }
    self.simulation = simulation

  def set_simulation(self, simulation):
    self.simulation = simulation

  @property
  def controller_configs(self):
    return [ c.config for c in self.controllers ]

  @property
  def controllers(self):
    cs = self.cid2controller.values()
    cs.sort(key=lambda c: c.cid)
    return cs

  @property
  def remote_controllers(self):
    # N.B. includes local controllers in network namespaces or VMs.
    # TODO(cs): does not currently support BigSwitchControllers (which do not
    # set self.guest_device).
    return [ c for c in self.controllers if c.guest_device is not None ]

  @property
  def cids(self):
    ids = self.cid2controller.keys()
    ids.sort()
    return ids

  @property
  def live_controllers(self):
    self.check_controller_status()
    alive = [controller for controller in self.controllers if controller.state == ControllerState.ALIVE]
    return set(alive)

  @property
  def down_controllers(self):
    self.check_controller_status()
    down = [controller for controller in self.controllers if controller.state == ControllerState.DEAD]
    return set(down)

  def all_controllers_down(self):
    return len(self.live_controllers) == 0

  def get_controller_by_label(self, label):
    for c in self.cid2controller.values():
      if c.label == label:
        return c
    return None

  def get_controller(self, cid):
    if cid not in self.cid2controller:
      raise ValueError("unknown cid %s" % str(cid))
    return self.cid2controller[cid]

  def kill_all(self):
    for c in self.live_controllers:
      c.kill()
    self.cid2controller = {}

  @staticmethod
  def kill_controller(controller):
    controller.kill()

  @staticmethod
  def reboot_controller(controller):
    controller.restart()

  def check_controller_status(self):
    controllers_with_problems = []
    for c in self.controllers:
      (ok, msg) = c.check_status(self.simulation)
      if ok and c.state == ControllerState.STARTING:
        c.state = ControllerState.ALIVE
      if not ok and c.state != ControllerState.STARTING:
        c.state = ControllerState.DEAD
        controllers_with_problems.append((c, msg))
    return controllers_with_problems


class ControllerPatchPanel(object):
  '''
  When multiple controllers are managing the network, we need to interpose on the
  messages sent between controllers, for at least two reasons:
    - interposition will allow us to simulate important failure modes, e.g.
      by delaying or dropping heartbeat messages.
    - interposition mitigates non-determinism during replay, as we have
      better control over message arrival.

  Note that wiring the distributed controllers to route through the
  patch panel is a separate task (specific to each controller), and is
  not implemented here. We assume here that the controllers route through
  interfaces on this machine.
  '''
  # TODO(cs): implement fingerprints for all control messages (e.g. Cassandra,
  # VRRP).
  pass

# TODO(cs): the distinction between Local/Remote may not be necessary. The
# main difference seems to be that the RemoteControllerPatchPanel must only
# use one (or two?) interfaces, and possibly tunnels, to multiplex between the
# controllers. It's not clear to me whether that difference is fundamental.

class LocalControllerPatchPanel(object):
  ''' For cases when all controllers are run on this machine, either in
  virtual machines or network namepaces. '''
  # TODO(cs): implement buffering. Do I need io_workers?
  def __init__(self):
    pass

  def register_host_veth(self, guest_eth_addr, guest_device_name, raw_socket=None):
    ''' raw_socket may be None, as in the case of a controller VM '''
    # TODO(cs): use libpcap rather than raw sockets? Would make it much easier
    # to filter out OpenFlow connections.
    pass
