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
  def cids(self):
    return self.cid2controller.keys().sort()

  @property
  def live_controllers(self):
    alive = [controller for controller in self.controllers if controller.state == ControllerState.ALIVE]
    return set(alive)

  @property
  def down_controllers(self):
    down = [controller for controller in self.controllers if controller.state == ControllerState.DEAD]
    return set(down)

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

