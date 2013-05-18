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

from sts.util.console import msg

class ControllerManager(object):
  ''' Encapsulate a list of controllers objects '''
  def __init__(self, controllers):
    self.cid2controller = {
      controller.cid : controller
      for controller in controllers
    }

  @property
  def controller_configs(self):
    return [ c.config for c in self.controllers ]

  @property
  def controllers(self):
     cs = self.cid2controller.values()
     cs.sort(key=lambda c: c.cid)
     return cs

  @property
  def live_controllers(self):
    alive = [controller for controller in self.controllers if controller.alive]
    return set(alive)

  @property
  def down_controllers(self):
    down = [controller for controller in self.controllers if not controller.alive]
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
    msg.event("Killing controller %s" % str(controller))
    controller.kill()

  @staticmethod
  def reboot_controller(controller):
    msg.event("Restarting controller %s" % str(controller))
    controller.start()

  def check_controller_processes_alive(self):
    controllers_with_problems = []
    live = list(self.live_controllers)
    live.sort(key=lambda c: c.cid)
    for c in live:
      (rc, msg) = c.check_process_status()
      if not rc:
        c.alive = False
        controllers_with_problems.append ( (c, msg) )
    return controllers_with_problems
