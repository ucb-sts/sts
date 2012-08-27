import itertools

class Controller (object):
  _port_gen = itertools.count(8888)
  
  def __init__(self, cmdline="", address="127.0.0.1", port=None):
    ''' cmdline is an array of command line tokens '''
    # TODO: document the __address__ and __port__ semantics
    self.cmdline = cmdline.split()
    self.address = address
    if not port and not self.needs_boot:
      raise RuntimeError("Need to specify port for already booted controllers")
    else if not port:
      port = self._port_gen.next()
    self.port = port

  @property
  def needs_boot(self):
    return self.cmdline != []
