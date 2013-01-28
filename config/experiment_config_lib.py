from collections import namedtuple
import itertools
import os
import string
import sys
import re
import socket
import random

# don't use the standard instance - we don't want to be seeded
true_random = random.Random()

def port_used(address='127.0.0.1', port=6633):
  s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  try:
    s.bind((address, port))
    s.listen(1)
    s.close()
    return False
  except Exception, e:
    # TODO(cs): catch specific errors
    return True

def find_port(port_spec):
  if isinstance(port_spec, int):
    def port_gen():
      yield port_spec
      raise Exception("Fixed port %d is busy. Consider specifying a range or a lambda " % port_spec)
  elif isinstance(port_spec, list):
    def port_gen():
      cands = list(port_spec)
      true_random.shuffle(cands)
      for c in cands:
        yield c
      raise Exception("Port list/range %s exhausted" % str(port_spec))
  elif isinstance(port_spec, types.FunctionType) or isinstance(port_spec, types.LambdaType):
    port_gen = port_spec

  gen = port_gen()
  for attempt in range(0,100):
    candidate = gen.next()
    if not port_used(port=candidate):
      return candidate
  raise Exception("Could not find a port in 100 tries")

def find_ports(**kwargs):
  return { k : find_port(v) for k, v in kwargs.iteritems() }

class ControllerConfig(object):
  _port_gen = itertools.count(6633)
  _controller_count_gen = itertools.count(1)

  def __init__(self, cmdline="", address="127.0.0.1", port=None, additional_ports={}, cwd=None, sync=None, controller_type=None, label=None, uuid=None, config_file=None, config_template=None):
    '''
    Store metadata for the controller.
      - cmdline is an array of command line tokens.

        Note: if you need to pass in the address and port to controller's
        command line, use the aliases __address__ and __port__ to have the
        values interpolated automatically
      - address and port are the sockets switches will bind to
      - controller_type: help us figure out by specifying controller_type as a
        string that represents the controller. If it is not specified, this
        method will try to guess if it is either pox or floodlight.
    '''
    if cmdline == "":
      raise RuntimeError("Must specify boot parameters.")
    self.cmdline = cmdline

    self.address = address
    if (re.match("[0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}", address) or
        address == "localhost"):
      orig_port = port
      # Normal TCP socket
      if not port:
        port = self._port_gen.next()
      while port_used(port=port):
        print "Port %d in use... trying next" % port
        port += true_random.rand_int(0,50)
      self.port = port
      self._uuid = uuid if uuid else (self.address, orig_port if orig_port else 6633)
      self._server_info = (self.address, port)
    else:
      # Unix domain socket
      self.port = None
      self._uuid = uuid if uuid else (self.address, orig_port if orig_port else 6633)
      self._server_info = address

    # TODO(sam): we should either call them all controller_type or all 'name'
    # we only accept strings
    self.name = ""
    if isinstance(controller_type,str):
      self.name = controller_type
    elif "pox" in self.cmdline:
      self.name = "pox"
    elif "floodlight" in self.cmdline:
      self.name = "floodlight"

    self.cwd = cwd
    if not cwd:
        sys.stderr.write("""
        =======================================================================
        WARN - no working directory defined for controller with command line 
        %s
        The controller is run in the STS base directory. This may result
        in unintended consequences (i.e., POX not logging correctly).
        =======================================================================
        \n""" % (self.cmdline) )

    self.sync = sync
    if label:
      self.label = label
    else:
      self.label = "c"+str(self._controller_count_gen.next())

    self.config_file = config_file
    self.config_template = config_template
    self.additional_ports = additional_ports

  @property
  def uuid(self):
    """ information about the (virtual/non-translated) socket to be matched in finger prints"""
    return self._uuid

  @property
  def server_info(self):
    """ information about the _real_ socket that the controller is listening on"""
    return self._server_info

  def _expand_vars(self, s):
    return reduce(lambda s, (name, val): s.replace("__%s_port__" % name, str(val)), self.additional_ports.iteritems(), s) \
            .replace("__port__", str(self.port)) \
            .replace("__address__", str(self.address)) \
            .replace("__config__", str(os.path.abspath(self.config_file) if self.config_file else ""))

  @property
  def expanded_cmdline(self):
    return map(self._expand_vars, self.cmdline.split())

  def generate_config_file(self, target_dir):
    if self.config_file is None:
      self.config_file = os.path.join(target_dir, os.path.basename(self.config_template).replace(".template", ""))

    with open(self.config_template, "r") as in_file:
      with open(self.config_file, "w") as out_file:
        out_file.write(self._expand_vars(in_file.read()))

  def __repr__(self):
    attributes = ("cmdline", "address", "port", "cwd", "sync")

    pairs = ( (attr, getattr(self, attr)) for attr in attributes)
    quoted = ( "%s=%s" % (attr, repr(value)) for (attr, value) in pairs if value)

    return self.__class__.__name__  + "(" + ", ".join(quoted) + ")"
