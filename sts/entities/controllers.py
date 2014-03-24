# Copyright 2011-2013 Colin Scott
# Copyright 2012-2013 Sam Whitlock
# Copyright 2011-2013 Andreas Wundsam
# Copyright 2012-2012 Kyriakos Zarifis
# Copyright 2014 Ahmed El-Hassany
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

"""
OpenFlow controller wrappers for STS
"""

import abc
import logging
import os
import re


from pox.lib.util import connect_socket_with_backoff
from pox.lib.util import parse_openflow_uri

from sts.util.procutils import popen_filtered, kill_procs
from sts.util.console import msg
from sts.util.network_namespace import launch_namespace
from sts.util.network_namespace import bind_pcap
from sts.util.convenience import IPAddressSpace
from sts.util.convenience import deprecated

from sts.entities.base import SSHEntity
from sts.entities.sts_entities import SnapshotPopen


class ControllerState(object):
  """
  Represents different states of a controller

  TODO: use enum package
  """
  ALIVE = 0
  STARTING = 1
  DEAD = 2


class ControllerConfig(object):
  """
  Initial controller's configuration state.

  Most configuration are static at the this stage, it's better to put dynamic
  aspects of configurations (like finding free port) somewhere else.
  See: config.experiment_config_lib.py for dynamic configuration.

  Args:
    start_cmd: command that starts the controller followed by a list of
      command line tokens as arguments. You may make use of two
      macros: __address__ expands to the address given in this constructor
      and __port__ expands to the port given in this constructor.
    kill_cmd: command that kills the controller followed by a list of
      command line tokens as arguments
    restart_cmd: define this if restart is not as simple as kill then start
      or to implement a soft restart command.
    address, port: controller socket info for listening to OpenFlow
      connections from switches. address may be specified as "auto" to
      automatically find a non-localhost IP address in the range
      192.168.1.0/24, or "__address__" to use get_address_cmd
      to choose an address.
    sync: A URI where this controller should listen for a STSSyncProto
      connection. Example: "tcp:localhost:18899"
    cwd: the working directory for the controller
    cid: controller unique ID
    label: controller human readable label
  """
  def __init__(self, start_cmd, kill_cmd, restart_cmd=None, check_cmd=None,
               address="127.0.0.1", port=6633, sync=None,
               cwd=None, cid=None, label=None):
    self._start_cmd = start_cmd
    self._kill_cmd = kill_cmd
    self._restart_cmd = restart_cmd
    self._check_cmd = check_cmd
    self._address = address
    self._port = port
    self._sync = sync
    self._cwd = cwd
    self._cid = cid
    self._label = label
    if self._label is None and self._cid is not None:
      self._label = "Controller(%s)" % self._cid

  @property
  def address(self):
    """The address of the controller"""
    return self._address

  @property
  def port(self):
    """The port (Openflow) that the controller is listening to"""
    return self._port

  @property
  def cid(self):
    """Controller's unique ID"""
    return self._cid

  @property
  def label(self):
    """Controller's human readable label."""
    return self._label

  @property
  def start_cmd(self):
    """
    The command to start the controller

    The specific format of the command is dependent on the controller type
    """
    return self._start_cmd

  @property
  def kill_cmd(self):
    """
    The command to kill the controller

    The specific format of the command is dependent on the controller type
    """
    return self._kill_cmd

  @property
  def restart_cmd(self):
    """
    The command to restart the controller

    The specific format of the command is dependent on the controller type
    """
    return self._restart_cmd

  @property
  def check_cmd(self):
    """
    The unix (bash) command to check the status the controller

    The specific format of the command is dependent on the controller type
    """
    return self._check_cmd

  @property
  def expanded_start_cmd(self):
    """Start command with substituted variables and arguments as a list"""
    return self._expand_vars(self.start_cmd).split()

  @property
  def expanded_kill_cmd(self):
    """Kill command with substituted variables and arguments as a list"""
    return self._expand_vars(self.kill_cmd).split()

  @property
  def expanded_restart_cmd(self):
    """Restart command with substituted variables and arguments as a list"""
    return self._expand_vars(self.restart_cmd).split()

  @property
  def expanded_check_cmd(self):
    """
    Check status command with substituted variables and arguments as a list
    """
    return self._expand_vars(self.check_cmd).split()

  @property
  def sync(self):
    return self._sync

  @property
  def cwd(self):
    """Controller's working directory"""
    return self._cwd

  def _expand_vars(self, cmd):
    """
    Utility method to substitute variables in strings.

    Looks for variables of the form __NAME__ in the string and then replace it
    with local attributes of the same name (if any).
    """
    if cmd is None:
      return None
    for cstr in re.findall("__[^_]*__", cmd):
      attr = cstr.strip("__")
      if hasattr(self, attr) and getattr(self, attr, None) is not None:
        cmd = cmd.replace(cstr, str(getattr(self, attr)))
    return cmd


class ControllerAbstractClass(object):
  """
  Controller Representation
  """

  __metaclass__ = abc.ABCMeta

  def __init__(self, controller_config, sync_connection_manager=None,
               snapshot_service=None):
    """
    Init a controller entity

    Args:
      controller_config: controller specific configuration object
      sync_connection_manager: ???
      snapshot_service: a SnapshotService instance (sts/snapshot.py)
        for checking extracting the controller's current view of the network
        state.
    """
    self._config = controller_config
    self._state = ControllerState.DEAD
    self._sync_connection_manager = sync_connection_manager
    self._snapshot_service = snapshot_service

  @property
  def config(self):
    """Controller specific configuration object"""
    return self._config

  @property
  def label(self):
    """Human readable label for the controller"""
    return self.config.label

  @property
  def cid(self):
    """Controller unique ID"""
    return self.config.cid

  @property
  def state(self):
    """
    The current controller state.

    See: ControllerState
    """
    return self._state

  @state.setter
  def state(self, value):
    self._state = value

  @property
  def snapshot_service(self):
    return self._snapshot_service

  @property
  def sync_connection_manager(self):
    return self._sync_connection_manager

  @abc.abstractproperty
  def is_remote(self):
    """
    Returns True if the controller is running on a different host that sts
    """
    raise NotImplementedError()

  @abc.abstractproperty
  def blocked_peers(self):
    """Return a list of blocked peer controllers (if any)"""
    raise NotImplementedError()

  @abc.abstractmethod
  def start(self, multiplex_sockets=False):
    """Starts the controller"""
    raise NotImplementedError()

  @abc.abstractmethod
  def block_peer(self, peer_controller):
    """Ignore traffic to/from the given peer controller
    """
    raise NotImplementedError()

  @abc.abstractmethod
  def unblock_peer(self, peer_controller):
    """Stop ignoring traffic to/from the given peer controller"""
    raise NotImplementedError()

  @abc.abstractmethod
  def check_status(self, simulation):
    """
    Check whether the actual status of the controller coincides with self.state

    Returns a tuple of ControllerStatus and message entailing the details of
    the status.
    """
    raise NotImplementedError()


class Controller(ControllerAbstractClass):
  """
  Encapsulates the state of a running controller

  This is a basic implementation, not intended to work with a real controller
  """

  # set of processes that are currently running.
  # These are all killed upon signal reception
  _active_processes = set()

  def _register_proc(self, proc):
    """
    Register a Popen instance that a controller is running in for the cleanup
    that happens when the simulator receives a signal.

    This method is idempotent
    """
    self._active_processes.add(proc)

  def _unregister_proc(self, proc):
    """
    Remove a process from the set of this to be killed when a signal is
    received. This is for use when the Controller process is stopped. This
    method is idempotent
    """
    self._active_processes.discard(proc)

  def __del__(self):
    # if it fails in __init__, process may not have been assigned
    if hasattr(self, 'process') and self.process is not None:
      if self.process.poll():
        # don't let this happen for shutdown
        self._unregister_proc(self.process)
      else:
        self.kill()  # make sure it is killed if this was started errantly

  def __init__(self, controller_config, sync_connection_manager=None,
               snapshot_service=None):
    """
    idx is the unique index for the controller used mostly for logging purposes
    """
    super(Controller, self).__init__(controller_config,
                                     sync_connection_manager, snapshot_service)
    self.process = None
    self.sync_connection = None
    self.log = logging.getLogger("Controller")
    # For network namespaces only:
    self.guest_eth_addr = None
    self.host_device = None
    self.welcome_msg = " =====> Starting Controller <===== "
    self.snapshot_socket = None

  @property
  @deprecated
  def remote(self):
    """
    Returns True if the controller is listening to some something other than
    localhost
    """
    return self.config.address != "127.0.0.1" and \
           self.config.address != "localhost"

  @property
  def is_remote(self):
    return self.remote

  @property
  def pid(self):
    """
    Return the PID of the Popen instance the controller was started with
    """
    return self.process.pid if self.process else -1

  @property
  def label(self):
    """
    Return the label of this controller. See ControllerConfig for more details
    """
    return self.config.label

  @property
  def cid(self):
    """
    Return the id of this controller. See ControllerConfig for more details
    """
    return self.config.cid

  def kill(self):
    """ Kill the process the controller is running in """
    if self.state != ControllerState.ALIVE:
      self.log.warn("Killing controller %s when it is not alive!" % self.label)
      return
    msg.event("Killing controller %s (pid %d)" % (self.cid, self.pid))
    kill_procs([self.process])
    if self.config.kill_cmd not in ["", None]:
      self.log.info("Killing controller %s: %s" % (
        self.label, " ".join(self.config.expanded_kill_cmd)))
      popen_filtered(
        "[%s]" % self.label, self.config.expanded_kill_cmd, self.config.cwd)
    self._unregister_proc(self.process)
    self.process = None
    self.state = ControllerState.DEAD

  def _bind_pcap(self, host_device):
    filter_string = "(not tcp port %d)" % self.config.port
    if self.config.sync is not None and self.config.sync != "":
      # TODO(cs): this is not quite correct. The *listen* port is sync_port,
      # but the sync data connection will go over over an ephermeral port.
      # Luckily this mistake is not fatal -- the kernel copies all
      # packets sent to the pcap, and we'll just drop the copied packets when
      # we realize we don't know where to route them.
      (_, _, sync_port) = parse_openflow_uri(self.config.sync)
      filter_string += " and (not tcp port %d)" % sync_port
    return bind_pcap(host_device, filter_string=filter_string)

  def _check_snapshot_connect(self):
    if getattr(self.config, "snapshot_address", None):
      # N.B. snapshot_socket is intended to be blocking
      self.log.debug("Connecting snapshot socket")
      self.snapshot_socket = connect_socket_with_backoff(
        address=self.config.snapshot_address)

  def start(self, multiplex_sockets=False):
    """
    Start a new controller process based on the config's start_cmd
    attribute. Registers the Popen member variable for deletion upon a SIG*
    received in the simulator process
    """
    self.log.info(self.welcome_msg)
    if self.state != ControllerState.DEAD:
      self.log.warn("Starting controller %s when it is not dead!" % self.label)
      return
    if self.config.start_cmd == "":
      raise RuntimeError(
        "No command found to start controller %s!" % self.label)
    self.log.info(
      "Launching controller %s: %s" % (
        self.label, " ".join(self.config.expanded_start_cmd)))
    # These configurations are specific to controllers launched in namespaces
    # Probably it should be factored somewhere else
    launch_in_network_namespace = getattr(self.config,
                                          'launch_in_network_namespace', None)
    if launch_in_network_namespace:
      unclaimed_address = IPAddressSpace.find_unclaimed_address(
        ip_prefix=self.config.address)
      (self.process, self.guest_eth_addr, self.host_device) = \
          launch_namespace(" ".join(self.config.expanded_start_cmd),
                           self.config.address, self.cid,
                           host_ip_addr_str=unclaimed_address)
    else:
      self.process = popen_filtered("[%s]" % self.label,
                                    self.config.expanded_start_cmd,
                                    self.config.cwd)
    self._register_proc(self.process)
    self._check_snapshot_connect()
    self.state = ControllerState.ALIVE

  def restart(self):
    """
    Restart the controller
    """
    if self.state != ControllerState.DEAD:
      self.log.warn(
        "Restarting controller %s when it is not dead!" % self.label)
      return
    self.start()

  def check_status(self, simulation):
    """
    Check whether the actual status of the controller coincides with self.state
    Returns a message entailing the details of the status
    """
    if self.state == ControllerState.DEAD:
      return (True, "OK")
    if not self.process:
      return (False,
              "Controller %s: Alive, but no controller process "
              "found" % self.cid)
    rc = self.process.poll()
    if rc is not None:
      return (False,
              "Controller %s: Alive, but controller process terminated with "
              "return code %d" % (self.cid, rc))
    return (True, "OK")

  def block_peer(self, peer_controller):
    """Ignore traffic to/from the given peer controller"""
    raise NotImplementedError("Peer blocking not yet supported")

  def unblock_peer(self, peer_controller):
    """Stop ignoring traffic to/from the given peer controller"""
    raise NotImplementedError("Peer blocking not yet supported")

  @property
  def blocked_peers(self):
    raise NotImplementedError()

  def snapshot(self):
    """
    Causes the controller to fork() a (suspended) copy of itself.
    """
    self.log.info("Initiating snapshot")
    self.snapshot_socket.send("SNAPSHOT")

  def snapshot_proceed(self):
    """
    Tell the previously fork()ed controller process to wake up, and connect
    a new socket to the fork()ed controller's (OpenFlow) port. Also
    de-registers the old controller process and registers the new controller
    process.

    Note that it is the responsibility of the caller to kill the previously
    fork()ed controller process.

    This method may block if the fork()ed process is not ready to proceed.

    Returns: a new socket connected to the woken controller.

    Pre: snapshot() has been invoked
    """
    self.log.info("Initiating snapshot proceed")
    # Check that the fork()ed controller is ready
    self.log.debug("Checking READY")
    # N.B. snapshot_socket is blocking
    response = self.snapshot_socket.recv(100)
    match = re.match(r"READY (?P<pid>\d+)", response)
    if not match:
      raise ValueError("Unknown response %s" % response)
    pid = int(match.group('pid'))

    # De-registers the old controller process and registers the new controller
    # process.
    self._unregister_proc(self.process)
    self.process = SnapshotPopen(pid)
    self._register_proc(self.process)

    # Send PROCEED
    self.log.debug("Sending PROCEED")
    self.snapshot_socket.send("PROCEED")

    # Reconnect
    self.log.debug("Connecting new mux socket")
    true_socket = connect_socket_with_backoff(address=self.config.address,
                                              port=self.config.port)
    true_socket.setblocking(0)
    self.log.debug("Finished snapshot proceed")
    return true_socket


class POXController(Controller):
  """
  N.B. controller-specific configuration is optional. The purpose of this
  class is to load POX's syncproto module, which helps us reduce
  non-determinism in POX.
  """
  def __init__(self, controller_config, sync_connection_manager=None,
               snapshot_service=None):
    """
    Controller Configs (in addition to the options defined in ControllerConfig)
      - launch_in_network_namespace: if true new network namespace is created
    """
    super(POXController, self).__init__(
      controller_config, sync_connection_manager, snapshot_service)
    self.welcome_msg = " =====> Starting POX Controller <===== "

  def start(self, multiplex_sockets=False):
    """
    Start a new POX controller process based on the config's start_cmd
    attribute. Registers the Popen member variable for deletion upon a SIG*
    received in the simulator process
    """
    self.log.info(self.welcome_msg)

    if self.state != ControllerState.DEAD:
      self.log.warn(
        "Starting controller %s when controller is not dead!" % self.label)
      return

    msg.event("Starting POX controller %s" % (str(self.cid)))
    env = None

    if self.config.sync:
      # If a sync connection has been configured in the controller conf
      # launch the controller with environment variable 'sts_sync' set
      # to the appropriate listening port. This is quite a hack.
      env = os.environ.copy()
      port_match = re.search(r':(\d+)$', self.config.sync)
      if port_match is None:
        raise ValueError("sync: cannot find port in %s" % self.config.sync)
      port = port_match.group(1)
      env['sts_sync'] = "ptcp:0.0.0.0:%d" % (int(port),)

    if self.config.sync or multiplex_sockets:
      src_dir = os.path.join(os.path.dirname(__file__), "../../")
      pox_ext_dir = os.path.join(self.config.cwd, "ext")
      if os.path.exists(pox_ext_dir):
        for f in ("sts/util/io_master.py", "sts/syncproto/base.py",
                  "sts/syncproto/pox_syncer.py", "sts/__init__.py",
                  "sts/util/socket_mux/__init__.py",
                  "sts/util/socket_mux/pox_monkeypatcher.py",
                  "sts/util/socket_mux/base.py",
                  "sts/util/socket_mux/server_socket_multiplexer.py"):
          src_path = os.path.join(src_dir, f)
          if not os.path.exists(src_path):
            raise ValueError(
              "Integrity violation: sts sync source path %s (abs: %s) "
              "does not exist" % (src_path, os.path.abspath(src_path)))
          dst_path = os.path.join(pox_ext_dir, f)
          dst_dir = os.path.dirname(dst_path)
          init_py = os.path.join(dst_dir, "__init__.py")
          if not os.path.exists(dst_dir):
            os.makedirs(dst_dir)
          if not os.path.exists(init_py):
            open(init_py, "a").close()
          if os.path.islink(dst_path):
            # Remove symlink and recreate
            os.remove(dst_path)
          if not os.path.exists(dst_path):
            rel_link = os.path.abspath(src_path)
            self.log.debug("Creating symlink %s -> %s", rel_link, dst_path)
            os.symlink(rel_link, dst_path)
      else:
        self.log.warn("Could not find pox ext dir in %s. " +
                      "Cannot check/link in sync module" % pox_ext_dir)

    if self.config.start_cmd in ["", None]:
      raise RuntimeError(
        "No command found to start controller %s!" % self.label)

    start_cmd = getattr(self.config, "expanded_start_cmd",
                        self.config.start_cmd)
    self.log.info(
      "Launching controller %s: %s" % (self.label, " ".join(start_cmd)))

    launch_in_network_namespace = getattr(self.config,
                                          "launch_in_network_namespace",
                                          False)
    if launch_in_network_namespace:
      (self.process, self.guest_eth_addr, self.host_device) = \
          launch_namespace(
            " ".join(start_cmd),
            self.config.address, self.cid,
            host_ip_addr_str=IPAddressSpace.find_unclaimed_address(
              ip_prefix=self.config.address),
            cwd=self.config.cwd, env=env)
    else:
      self.process = popen_filtered("[%s]" % self.label,
                                    start_cmd, self.config.cwd, env)
    self._register_proc(self.process)
    if self.config.sync:
      self.sync_connection = self.sync_connection_manager.connect(
        self, self.config.sync)
    self._check_snapshot_connect()
    self.state = ControllerState.ALIVE


class VMController(Controller):
  """Controllers that are run in virtual machines rather than processes"""
  __metaclass__ = abc.ABCMeta

  def __init__(self, controller_config, cmd_executor=None,
               sync_connection_manager=None, snapshot_service=None,
               username=None, password=None):
    """
    Args:
      controller_config: see ControllerConfig
      cmd_executer: a class that has execute_command method. If not specified
                    SSHEntity will be used
                    See SSHEntity and LocalEntity
      username: overrides the username specified in controller_config (if any)
      password: overrides the password specified in controller_config (if any)
    """
    Controller.__init__(self, controller_config, sync_connection_manager,
                        snapshot_service)
    self.username = username
    self.password = password
    if self.username is None and hasattr(self.config, 'username'):
      self.username = self.config.username
    if self.password is None and hasattr(self.config, 'password'):
      self.password = self.config.password
    self.cmd_executor = cmd_executor
    if self.cmd_executor is None and hasattr(self.config, 'cmd_executor'):
      self.cmd_executor = self.config.cmd_executer
    if self.cmd_executor is None:
      key_filename = getattr(self.config, 'key_filename', None)
      self.cmd_executor = SSHEntity(controller_config.address,
                                    username=self.username,
                                    password=self.password,
                                    key_filename=key_filename,
                                    cwd=getattr(self.config, "cwd", None),
                                    redirect_output=True,
                                    block=True)
    assert hasattr(self.cmd_executor, "execute_command")
    self.commands = {}
    self.populate_commands()
    self.welcome_msg = " =====> Starting VM Controller <===== "
    self.alive_status_string = ""  # subclass dependent

  def populate_commands(self):
    if self.config.start_cmd == "":
      raise RuntimeError(
        "No command found to start controller %s!" % self.label)
    if self.config.kill_cmd == "":
      raise RuntimeError(
        "No command found to kill controller %s!" % self.label)
    if self.config.restart_cmd == "":
      raise RuntimeError(
        "No command found to restart controller %s!" % self.label)
    self.commands["start"] = " ".join(self.config.expanded_start_cmd)
    self.commands["kill"] = " ".join(self.config.expanded_kill_cmd)
    self.commands["restart"] = " ".join(self.config.expanded_restart_cmd)
    if hasattr(self.config, "expanded_check_cmd"):
      self.commands["check"] = " ".join(self.config.expanded_check_cmd)
    else:
      self.commands["check"] = getattr(self.config, "check_cmd", "")

  def kill(self):
    if self.state != ControllerState.ALIVE:
      self.log.warn(
        "Killing controller %s when controller is not alive!" % self.label)
      return
    kill_cmd = self.commands["kill"]
    self.log.info("Killing controller %s: %s" % (self.label, kill_cmd))
    self.cmd_executor.execute_command(kill_cmd)
    self.state = ControllerState.DEAD

  def start(self, multiplex_sockets=False):
    self.log.info(self.welcome_msg)
    if self.state != ControllerState.DEAD:
      self.log.warn(
        "Starting controller %s when controller is not dead!" % self.label)
      return
    start_cmd = self.commands["start"]
    self.log.info("Launching controller %s: %s" % (self.label, start_cmd))
    ret = self.cmd_executor.execute_command(start_cmd)
    if ret is not None:
      self.log.info(ret)
    self.state = ControllerState.ALIVE

  def restart(self):
    if self.state != ControllerState.DEAD:
      self.log.warn(
        "Restarting controller %s when controller is not dead!" % self.label)
      return
    restart_cmd = self.commands["restart"]
    self.log.info("Relaunching controller %s: %s" % (self.label, restart_cmd))
    self.cmd_executor.execute_command(restart_cmd)
    self.state = ControllerState.ALIVE

  # SSH into the VM to check on controller process
  def check_status(self, simulation):
    check_cmd = self.commands["check"]
    self.log.info(
      "Checking status of controller %s: %s" % (self.label, check_cmd))
    # By make sure the status cmd will return status rather than
    # printing it out on stdout. If the executor has redirect_output
    # set to True there is not way to check the return status because it's
    # printed out.
    old_redirect_status = self.cmd_executor.redirect_output
    self.cmd_executor.redirect_output = False
    # Execute the status command
    remote_status = self.cmd_executor.execute_command(check_cmd)
    # Restore to the old redirect status
    self.cmd_executor.redirect_output = old_redirect_status
    actual_state = ControllerState.DEAD
    # Alive means remote controller process exists
    if self.alive_status_string in remote_status:
      actual_state = ControllerState.ALIVE
    if (self.state == ControllerState.DEAD and
            actual_state == ControllerState.ALIVE):
      self.log.warn("%s is dead, but controller process found!" % self.label)
      self.state = ControllerState.ALIVE
    if (self.state == ControllerState.ALIVE and
            actual_state == ControllerState.DEAD):
      return (False, "Alive, but no controller process found!")
    return (True, "OK")

  def block_peer(self, peer_controller):
    for chain in ['INPUT', 'OUTPUT']:
      check_block_cmd = "sudo iptables -L %s | grep \"DROP.*%s\"" % (
        chain, peer_controller.config.address)
      add_block_cmd = "sudo iptables -I %s 1 -s %s -j DROP" % (
        chain, peer_controller.config.address)
      # If already blocked, do nothing
      if self.cmd_executor.execute_command(check_block_cmd) != "":
        continue
      self.cmd_executor.execute_command(add_block_cmd)

  def unblock_peer(self, peer_controller):
    for chain in ['INPUT', 'OUTPUT']:
      check_block_cmd = "sudo iptables -L %s | grep \"DROP.*%s\"" % (
        chain, peer_controller.config.address)
      remove_block_cmd = "sudo iptables -D %s -s %s -j DROP" % (
        chain, peer_controller.config.address)
      max_iterations = 10
      while max_iterations > 0:
        # If already unblocked, do nothing
        if self.cmd_executor.execute_command(check_block_cmd) == "":
          break
        self.cmd_executor.execute_command(remove_block_cmd)
        max_iterations -= 1


class BigSwitchController(VMController):
  """BigSwitch Controller specific wrapper"""
  def __init__(self, controller_config, sync_connection_manager=None,
               snapshot_service=None, username="root", password=""):
    super(BigSwitchController, self).__init__(controller_config,
          sync_connection_manager, snapshot_service,
          username=username, password=password)
    self.welcome_msg = " =====> Starting BigSwitch Controller <===== "
    self.alive_status_string = "start/running"

  def populate_commands(self):
    if self.config.start_cmd == "":
      raise RuntimeError(
        "No command found to start controller %s!" % self.label)
    self.commands["start"] = " ".join(self.config.expanded_start_cmd)
    self.commands["kill"] = "service floodlight stop"
    self.commands["restart"] = "service floodlight start; initctl stop bscmon"
    self.commands["check"] = "service floodlight status"

  def start(self, multiplex_sockets=False):
    super(BigSwitchController, self).start()
    self.cmd_executor.execute_command(self.commands["restart"])

  def kill(self):
    if self.state != ControllerState.ALIVE:
      self.log.warn(
        "Killing controller %s when controller is not alive!" % self.label)
      return
    kill_cmd = self.commands["kill"]
    self.log.info("Killing controller %s: %s" % (self.label, kill_cmd))
    self.cmd_executor.execute_command(kill_cmd)
    self.state = ControllerState.DEAD

  def restart(self):
    if self.state != ControllerState.DEAD:
      self.log.warn(
        "Restarting controller %s when controller is not dead!" % self.label)
      return
    restart_cmd = self.commands["restart"]
    self.log.info("Relaunching controller %s: %s" % (self.label, restart_cmd))
    self.cmd_executor.execute_command(restart_cmd)
    self.state = ControllerState.STARTING


class ONOSController(VMController):
  """ONOS Specific wrapper"""
  def __init__(self, controller_config, cmd_executor=None,
               sync_connection_manager=None, snapshot_service=None,
               username="mininet", password="mininet"):
    if not getattr(controller_config, "check_cmd", None):
      controller_config.check_cmd = "./start-onos.sh status"
    super(ONOSController, self).__init__(controller_config, cmd_executor,
          sync_connection_manager, snapshot_service,
          username=username, password=password)
    self.welcome_msg = " =====> Starting ONOS Controller <===== "
    self.alive_status_string = "1 instance of onos running"
