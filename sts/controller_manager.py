from sts.util.console import msg

class ControllerManager(object):
  ''' Encapsulate a list of controllers objects '''
  def __init__(self, controllers):
    self.uuid2controller = {
      controller.uuid : controller
      for controller in controllers
    }

  @property
  def controllers(self):
    return self.uuid2controller.values()

  @property
  def live_controllers(self):
    alive = [controller for controller in self.controllers if controller.alive]
    return set(alive)

  @property
  def down_controllers(self):
    down = [controller for controller in self.controllers if not controller.alive]
    return set(down)

  def get_controller(self, uuid):
    if uuid not in self.uuid2controller:
      raise ValueError("unknown uuid %s" % str(uuid))
    return self.uuid2controller[uuid]

  def kill_all(self):
    for c in self.live_controllers:
      c.kill()
    self.uuid2controller = {}

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
    for c in self.live_controllers:
      (rc, msg) = c.check_process_status()
      if not rc:
        c.alive = False
        controllers_with_problems.append ( (c, msg) )
    return controllers_with_problems
