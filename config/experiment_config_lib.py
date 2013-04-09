# Copyright 2011-2013 Colin Scott
# Copyright 2011-2013 Andreas Wundsam
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

from collections import namedtuple
import itertools
import os
import string
import sys
import re
import socket
import random
from sts.util.convenience import find_port

class ControllerConfig(object):
  _port_gen = itertools.count(6633)
  _controller_count_gen = itertools.count(1)
  _controller_labels = set()

  def __init__(self, cmdline="", address="127.0.0.1", port=None,
               additional_ports={}, cwd=None, sync=None, controller_type=None,
               label=None, config_file=None, config_template=None,
               try_new_ports=True):
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
    orig_port = port
    if (re.match("[0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}", address) or
        address == "localhost"):
      # Normal TCP socket
      if not port:
        port = self._port_gen.next()
      if try_new_ports:
        port = find_port(xrange(port, port+2000))
      self.port = port
      self._server_info = (self.address, port)
    else:
      # Unix domain socket
      self.port = None
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
      label = label
    else:
      label = "c"+str(self._controller_count_gen.next())
    if label in self._controller_labels:
      raise ValueError("Label %s already registered!" % label)
    self._controller_labels.add(label)
    self.label = label

    self.config_file = config_file
    self.config_template = config_template
    self.additional_ports = additional_ports

  @property
  def cid(self):
    ''' Return this controller's id '''
    return self.label

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
