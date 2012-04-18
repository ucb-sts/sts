import itertools


class Controller (object):
  _port_gen = itertools.count(8888)
  
  def __init__(self, cmdline=[], address="127.0.0.1", port=None):
    ''' cmdline is an array of command line tokens '''
    self.cmdline = cmdline
    self.address = address
    if not port:
        port = self._port_gen.next()
    self.port = port

class Link (object):
  def __init__(self, switch1, switch2):
    self.switch1 = switch1
    self.switch2 = switch2

class Switch (object):
  def __init__(self, parent_controller, links):
    self.parent_controller = parent_controller 
    self.links = links

