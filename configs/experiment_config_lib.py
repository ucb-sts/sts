import itertools

class Controller (object):
  _port_gen = itertools.count(8888)

  def __init__(self, cmdline="", address="127.0.0.1", port=None, nom_port=None):
    '''
    Store metadata for the controller.
      - cmdline is an array of command line tokens.

        Note: if you need to pass in the address and port to controller's
        command line, use the aliases __address__ and __port__ to have the
        values interpolated automatically
      - address and port are the sockets switches will bind to
      - address and nom_port is the socket the simulator will use to grab the
        NOM from (None for no correspondence checking)
    '''
    self.cmdline = cmdline.split()
    self.address = address
    if not port and not self.needs_boot:
      raise RuntimeError("Need to specify port for already booted controllers")
    else if not port:
      port = self._port_gen.next()
    self.port = port
    self.nom_port = nom_port

  @property
  def needs_boot(self):
    return self.cmdline != []
