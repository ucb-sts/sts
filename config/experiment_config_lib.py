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

import itertools
import os
import sys
import subprocess
import logging
import re
import time
from sts.util.convenience import address_is_ip, find_port, IPAddressSpace
from sts.entities import Controller, POXController, BigSwitchController

log = logging.getLogger("controller-config")

controller_type_map = {
  "pox": POXController,
  "bsc": BigSwitchController,
}

class ControllerConfig(object):
  _port_gen = itertools.count(6633)
  _controller_count_gen = itertools.count(1)
  _controller_labels = set()
  _controller_addresses = []
  _address_retriever = None
  _max_address_retrieval_attempts = 5

  def __init__(self, start_cmd="", address="127.0.0.1", port=None, additional_ports={},
               cwd=None, sync=None, controller_type=None, label=None, config_file=None,
               config_template=None, try_new_ports=False, kill_cmd="", restart_cmd="",
               get_address_cmd="", launch_in_network_namespace=False):
    '''
    Store metadata for the controller.
      - start_cmd: command that starts a controller or a set of controllers,
          followed by a list of command line tokens as arguments. You may make
          use of two macros: __address__ expands to some available IP address
          for the controller, and __port__ expands to some available (OpenFlow) port.
      - kill_cmd: command that kills a controller or a set of controllers,
          followed by a list of command line tokens as arguments
      - address, port: controller socket info for listening to OpenFlow
        connections from switches. address may be specified as "auto" to automatically find a
        non-localhost IP address in the range 192.168.1.0/24, or "__address__" to use
        get_address_cmd to choose an address.
      - get_address_cmd: an optional bash command that returns an address for
        the controller to bind to.
      - controller_type: controller type, specified by the corresponding Controller
          class itself, or a string chosen from one of the keys in controller_type_map
    '''
    if start_cmd == "":
      raise RuntimeError("Must specify boot parameters.")
    self.start_cmd = start_cmd
    self.kill_cmd = kill_cmd
    self.restart_cmd = restart_cmd
    self.launch_in_network_namespace = launch_in_network_namespace
    if launch_in_network_namespace and (address == "127.0.0.1" or address == "localhost"):
      raise ValueError("""Must set a non-localhost address for namespace controller.\n"""
                       """Specify `auto` to automatically find an available IP.""")

    # Set label
    if label is None:
      label = "c%s" % str(self._controller_count_gen.next())
    if label in self._controller_labels:
      raise ValueError("Label %s already registered!" % label)
    self._controller_labels.add(label)
    self.label = label

    # Set index, for assigning IP addresses in the case of multiple controllers
    match = re.search("c(\d+)", self.label)
    if match:
      self.index = int(match.groups()[0])
    else:
      self.index = None

    # Set address.
    if address == "__address__":
      address = self.get_address(get_address_cmd, cwd)
    elif address == "auto":
      # TODO(cs): need to add support for auto to the sync uri.
      address = IPAddressSpace.find_unclaimed_address()
    self.address = address
    IPAddressSpace.register_address(address)

    if address_is_ip(address) or address == "localhost":
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

    self.controller_type = controller_type
    if controller_type is None:
      for t in controller_type_map.keys():
        if t in self.start_cmd:
          self.controller_class = controller_type_map[t]
          break
      else:
        # Default to Base Controller class
        self.controller_class = Controller
    else:
      if controller_type not in controller_type_map.keys():
        raise RuntimeError("Unknown controller type: %s" % controller_type)
      self.controller_class = controller_type_map[controller_type]

    self.cwd = cwd
    if not cwd:
        sys.stderr.write("""
        =======================================================================
        WARN - no working directory defined for controller with command line
        %s
        The controller is run in the STS base directory. This may result
        in unintended consequences (i.e. controller not logging correctly).
        =======================================================================
        \n""" % (self.start_cmd) )

    self.sync = sync

    self.config_file = config_file
    self.config_template = config_template
    self.additional_ports = additional_ports

  def get_address(self, get_address_cmd, cwd):
    '''
    In the event of having to start a controller without the knowledge of its IP address a priori,
    periodically attempt to retrieve the IP from the output of get_address_cmd. If multiple controller
    instances are launched in this case, only the designated address retriever makes such attempts.
    '''
    if get_address_cmd is "":
      raise RuntimeError("Controller address cannot be resolved!")
    for _ in range(self._max_address_retrieval_attempts):
      # If another controller instance is already retrieving address, back off and wait
      if self._address_retriever is None or self._address_retriever == self.label:
        ControllerConfig._address_retriever = self.label
        p = subprocess.Popen(get_address_cmd, shell=True, stdout=subprocess.PIPE, cwd=cwd)
        (new_addresses, _) = p.communicate()
        new_addresses = new_addresses.strip()
        new_addresses = re.split("\s+", new_addresses)
        new_addresses = [a for a in new_addresses if address_is_ip(a)]
        self._controller_addresses.extend(new_addresses)
      if len(self._controller_addresses) != 0:
        break
      log.warn("Controller addresses not found... Keep trying.")
      time.sleep(5.0)
    else:
      raise RuntimeError("Cannot retrieve controller IP addresses after %d attempts!" %
                           self._max_address_retrieval_attempts)
    address = None
    if self.index is not None and self.index <= len(self._controller_addresses):
      address = self._controller_addresses[self.index-1]
      self.address = address
      log.info("Found controller address for %s: %s!" % (self.label, self.address))
    else:
      raise RuntimeError("No IP address resolved for controller %s!" % self.label)
    return address

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
  def expanded_start_cmd(self):
    return map(self._expand_vars, self.start_cmd.split())

  @property
  def expanded_kill_cmd(self):
    return map(self._expand_vars, self.kill_cmd.split())

  @property
  def expanded_restart_cmd(self):
    return map(self._expand_vars, self.restart_cmd.split())

  def generate_config_file(self, target_dir):
    if self.config_file is None:
      self.config_file = os.path.join(target_dir, os.path.basename(self.config_template).replace(".template", ""))

    with open(self.config_template, "r") as in_file:
      with open(self.config_file, "w") as out_file:
        out_file.write(self._expand_vars(in_file.read()))

  def __repr__(self):
    attributes = ("start_cmd", "label", "address", "cwd", "controller_type", "sync", "kill_cmd", "restart_cmd")

    pairs = ( (attr, getattr(self, attr)) for attr in attributes)
    quoted = ( "%s=%s" % (attr, repr(value)) for (attr, value) in pairs if value)

    return self.__class__.__name__  + "(" + ", ".join(quoted) + ")"
