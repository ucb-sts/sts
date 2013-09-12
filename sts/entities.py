# Copyright 2011-2013 Colin Scott
# Copyright 2012-2013 Sam Whitlock
# Copyright 2011-2013 Andreas Wundsam
# Copyright 2012-2012 Kyriakos Zarifis
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
This module defines the simulated entities, such as openflow switches, links, and hosts.
"""

from pox.openflow.software_switch import DpPacketOut, OFConnection
from pox.openflow.nx_software_switch import NXSoftwareSwitch
from pox.openflow.flow_table import FlowTableModification
from pox.openflow.libopenflow_01 import *
from pox.lib.revent import EventMixin
import pox.lib.packet.ethernet as eth
from pox.lib.addresses import EthAddr, IPAddr
from sts.util.procutils import popen_filtered, kill_procs
from sts.util.console import msg
from sts.util.network_namespace import launch_namespace
from sts.util.convenience import IPAddressSpace

from itertools import count
import logging
import os
import re
import pickle

class DeferredOFConnection(OFConnection):
  def __init__(self, io_worker, cid, dpid, god_scheduler):
    super(DeferredOFConnection, self).__init__(io_worker)
    self.cid = cid
    self.dpid = dpid
    self.god_scheduler = god_scheduler
    # Don't feed messages to the switch directly
    self.on_message_received = self.insert_pending_receipt
    self.true_on_message_handler = None

  @property
  def closed(self):
    return self.io_worker.closed

  def get_controller_id(self):
    return self.cid

  def insert_pending_receipt(self, _, ofp_msg):
    ''' Rather than pass directly on to the switch, feed into the god scheduler'''
    self.god_scheduler.insert_pending_receipt(self.dpid, self.cid, ofp_msg, self)

  def set_message_handler(self, handler):
    ''' Take the switch's handler, and store it for later use '''
    self.true_on_message_handler = handler

  def allow_message_receipt(self, ofp_message):
    ''' Allow the message to actually go through to the switch '''
    self.true_on_message_handler(self, ofp_message)

  def send(self, ofp_message):
    ''' Interpose on switch sends as well '''
    self.god_scheduler.insert_pending_send(self.dpid, self.cid, ofp_message, self)

  def allow_message_send(self, ofp_message):
    ''' Allow message actually be sent to the controller '''
    super(DeferredOFConnection, self).send(ofp_message)

class ConnectionlessOFConnection(object):
  ''' For use with InteractiveReplayer, where controllers are mocked out, and
  events are replayed to headless switches.'''
  def __init__(self, cid, dpid):
    self.cid = cid
    self.dpid = dpid
    self.on_message_received = None
    OFConnection.ID += 1
    self.ID = OFConnection.ID

  @property
  def closed(self):
    return False

  def close(self):
    pass

  def get_controller_id(self):
    return self.cid

  def set_message_handler(self, handler):
    self.on_message_handler = handler

  def send(self, ofp_message):
    ''' Into the abyss you go!'''
    pass

  # N.B. different interface than OFConnection. It's OK, since we don't actually
  # use io_workers -- this is only invoked by
  # ControlMessageReceive.manually_inject()
  def read (self, ofp_message):
    self.on_message_handler(self, ofp_message)


class FuzzSoftwareSwitch (NXSoftwareSwitch):
  """
  A mock switch implementation for testing purposes. Can simulate dropping dead.
  """
  _eventMixin_events = set([DpPacketOut])

  def __init__(self, dpid, name=None, ports=4, miss_send_len=128,
               n_buffers=100, n_tables=1, capabilities=None,
               can_connect_to_endhosts=True):
    NXSoftwareSwitch.__init__(self, dpid, name, ports, miss_send_len,
                              n_buffers, n_tables, capabilities)

    # Whether this is a core or edge switch
    self.can_connect_to_endhosts = can_connect_to_endhosts
    self.create_connection = None

    self.failed = False
    self.log = logging.getLogger("FuzzSoftwareSwitch(%d)" % dpid)

    if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
      def _print_entry_remove(table_mod):
        if table_mod.removed != []:
          self.log.debug("Table entry removed %s" % str(table_mod.removed))
      self.table.addListener(FlowTableModification, _print_entry_remove)

    def error_handler(e):
      self.log.exception(e)
      raise e

    self.cid2connection = {}
    self.error_handler = error_handler
    self.controller_info = []

  def add_controller_info(self, info):
    self.controller_info.append(info)

  def _handle_ConnectionUp(self, event):
    self._setConnection(event.connection, event.ofp)

  def connect(self, create_connection, down_controller_ids=None):
    ''' - create_connection is a factory method for creating Connection objects
          which are connected to controllers. Takes a ControllerConfig object
          and a reference to a switch (self) as a parameter
    '''
    # Keep around the connection factory for fail/recovery later
    if down_controller_ids is None:
      down_controller_ids = set()
    self.create_connection = create_connection
    connected_to_at_least_one = False
    for info in self.controller_info:
      # Don't connect to down controllers
      if info.cid not in down_controller_ids:
        conn = create_connection(info, self)
        self.set_connection(conn)
        # cause errors to be raised
        conn.error_handler = self.error_handler
        self.cid2connection[info.cid] = conn
        connected_to_at_least_one = True

    return connected_to_at_least_one

  def send(self, *args, **kwargs):
    if self.failed:
      self.log.warn("Currently down. Dropping send()")
    else:
      super(FuzzSoftwareSwitch, self).send(*args, **kwargs)

  def get_connection(self, cid):
    if cid not in self.cid2connection.keys():
      raise ValueError("No such connection %s" % str(cid))
    return self.cid2connection[cid]

  def is_connected_to(self, cid):
    if cid in self.cid2connection.keys():
      conn = self.get_connection(cid)
      return not conn.closed
    return False

  def fail(self):
    # TODO(cs): depending on the type of failure, a real switch failure
    # might not lead to an immediate disconnect
    if self.failed:
      self.log.warn("Switch already failed")
      return
    self.failed = True

    for connection in self.connections:
      connection.close()
    self.connections = []

  def recover(self, down_controller_ids=None):
    if not self.failed:
      self.log.warn("Switch already up")
      return
    if self.create_connection is None:
      self.log.warn("Never connected in the first place")

    connected_to_at_least_one = self.connect(self.create_connection,
                                             down_controller_ids=down_controller_ids)
    if connected_to_at_least_one:
      self.failed = False
    return connected_to_at_least_one

  def serialize(self):
    # Skip over non-serializable data, e.g. sockets
    # TODO(cs): is self.log going to be a problem?
    serializable = FuzzSoftwareSwitch(self.dpid, self.parent_controller_name)
    # Can't serialize files
    serializable.log = None
    # TODO(cs): need a cleaner way to add in the NOM port representation
    if self.software_switch:
      serializable.ofp_phy_ports = self.software_switch.ports.values()
    return pickle.dumps(serializable, protocol=0)

class Link (object):
  """
  A network link between two switches

  Temporary stand in for Murphy's graph-library for the NOM.

  Note: Directed!
  """
  def __init__(self, start_software_switch, start_port, end_software_switch, end_port):
    if type(start_port) == int:
      assert(start_port in start_software_switch.ports)
      start_port = start_software_switch.ports[start_port]
    if type(end_port) == int:
      assert(end_port in start_software_switch.ports)
      end_port = end_software_switch.ports[end_port]
    assert_type("start_port", start_port, ofp_phy_port, none_ok=False)
    assert_type("end_port", end_port, ofp_phy_port, none_ok=False)
    self.start_software_switch = start_software_switch
    self.start_port = start_port
    self.end_software_switch = end_software_switch
    self.end_port = end_port

  def __eq__(self, other):
    if not type(other) == Link:
      return False
    return (self.start_software_switch == other.start_software_switch and
            self.start_port == other.start_port and
            self.end_software_switch == other.end_software_switch and
            self.end_port == other.end_port)

  def __ne__(self, other):
    # NOTE: __ne__ in python does *NOT* by default delegate to eq
    return not self.__eq__(other)


  def __hash__(self):
    return (self.start_software_switch.__hash__() +  self.start_port.__hash__() +
           self.end_software_switch.__hash__() +  self.end_port.__hash__())

  def __repr__(self):
    return "(%d:%d) -> (%d:%d)" % (self.start_software_switch.dpid, self.start_port.port_no,
                                   self.end_software_switch.dpid, self.end_port.port_no)

  def reversed_link(self):
    '''Create a Link that is in the opposite direction of this Link.'''
    return Link(self.end_software_switch, self.end_port,
                self.start_software_switch, self.start_port)

class AccessLink (object):
  '''
  Represents a bidirectional edge: host <-> ingress switch
  '''
  def __init__(self, host, interface, switch, switch_port):
    assert_type("interface", interface, HostInterface, none_ok=False)
    assert_type("switch_port", switch_port, ofp_phy_port, none_ok=False)
    self.host = host
    self.interface = interface
    self.switch = switch
    self.switch_port = switch_port

class HostInterface (object):
  ''' Represents a host's interface (e.g. eth0) '''
  def __init__(self, hw_addr, ip_or_ips=[], name=""):
    self.hw_addr = hw_addr
    if type(ip_or_ips) != list:
      ip_or_ips = [ip_or_ips]
    self.ips = ip_or_ips
    self.name = name

  @property
  def port_no(self):
    # Hack
    return self.hw_addr.toStr()

  def __eq__(self, other):
    if type(other) != HostInterface:
      return False
    if self.hw_addr.toInt() != other.hw_addr.toInt():
      return False
    other_ip_ints = map(lambda ip: ip.toUnsignedN(), other.ips)
    for ip in self.ips:
      if ip.toUnsignedN() not in other_ip_ints:
        return False
    if len(other.ips) != len(self.ips):
      return False
    if self.name != other.name:
      return False
    return True

  def __hash__(self):
    hash_code = self.hw_addr.toInt().__hash__()
    for ip in self.ips:
      hash_code += ip.toUnsignedN().__hash__()
    hash_code += self.name.__hash__()
    return hash_code

  def __str__(self, *args, **kwargs):
    return "HostInterface:" + self.name + ":" + str(self.hw_addr) + ":" + str(self.ips)

  def __repr__(self, *args, **kwargs):
    return self.__str__()

  def to_json(self):
    return {'name' : self.name,
            'ips' : [ ip.toStr() for ip in self.ips ],
            'hw_addr' : self.hw_addr.toStr()}

  @staticmethod
  def from_json(json_hash):
    name = json_hash['name']
    ips = []
    for ip in json_hash['ips']:
      ips.append(IPAddr(str(ip)))
    hw_addr = EthAddr(json_hash['hw_addr'])
    return HostInterface(hw_addr, ip_or_ips=ips, name=name)

#                Host
#          /      |       \
#  interface   interface  interface
#    |            |           |
# access_link acccess_link access_link
#    |            |           |
# switch_port  switch_port  switch_port

class Host (EventMixin):
  '''
  A very simple Host entity.

  For more sophisticated hosts, we should spawn a separate VM!

  If multiple host VMs are too heavy-weight for a single machine, run the
  hosts on their own machines!
  '''
  _eventMixin_events = set([DpPacketOut])
  _hids = count(1)

  def __init__(self, interfaces, name=""):
    '''
    - interfaces A list of HostInterfaces
    '''
    self.interfaces = interfaces
    self.log = logging.getLogger(name)
    self.name = name
    self.hid = self._hids.next()

  def send(self, interface, packet):
    ''' Send a packet out a given interface '''
    self.log.info("sending packet on interface %s: %s" % (interface.name, str(packet)))
    self.raiseEvent(DpPacketOut(self, packet, interface))

  def receive(self, interface, packet):
    '''
    Process an incoming packet from a switch

    Called by PatchPanel
    '''
    self.log.info("received packet on interface %s: %s" % (interface.name, str(packet)))

  @property
  def dpid(self):
    # Hack
    return self.hid

  def __str__(self):
    return "%s (%d)" % (self.name, self.hid)

  def __repr__(self):
    return "Host(%d)" % self.hid

class NamespaceHost(Host):
  '''
  A host that launches a process in a separate namespace process.
  '''
  def __init__(self, ip_addr_str, create_io_worker, name="", cmd="xterm"):
    '''
    - ip_addr_str must be a string! not a IPAddr object
    - cmd: a string of the command to execute in the separate namespace
      The default is "xterm", which opens up a new terminal window.
    '''
    self.hid = self._hids.next()
    (self.socket, self.guest, guest_eth_addr) = launch_namespace(cmd, ip_addr_str, self.hid)
    # Set up an io worker for our end of the socket
    self.io_worker = create_io_worker(self.socket)
    self.io_worker.set_receive_handler(self.send)

    self.interfaces = [HostInterface(self.guest_eth_addr, IPAddr(ip_addr_str))]
    if name == "":
      name = "host:" + ip_addr_str
    self.name = name

  def send(self, io_worker):
    message = io_worker.peek_receive_buf()
    # Create an ethernet packet
    # TODO(cs): this assumes that the raw socket returns exactly one ethernet
    # packet. Since ethernet frames do not include length information, the
    # only way to correctly handle partial packets would be to get access to
    # framing information. Should probably look at what Mininet does.
    packet = eth.ethernet(raw=message)
    if not packet.parsed:
      return
    io_worker.consume_receive_buf(packet.hdr_len + packet.payload_len)
    super(NamespaceHost, self).send(packet)

  def receive(self, interface, packet):
    '''
    Process an incoming packet from a switch
    Called by PatchPanel
    '''
    self.log.info("received packet on interface %s: %s. Passing to netns" %
                  (interface.name, str(packet)))
    self.io_worker.send(packet.pack())

class ControllerState():
  ''' Represents different states of a controller '''
  ALIVE = 0
  STARTING = 1
  DEAD = 2

class Controller(object):
  ''' Encapsulates the state of a running controller '''

  _active_processes = set() # set of processes that are currently running. These are all killed upon signal reception

  def _register_proc(self, proc):
    ''' Register a Popen instance that a controller is running in for the cleanup
    that happens when the simulator receives a signal. This method is idempotent '''
    self._active_processes.add(proc)

  def _unregister_proc(self, proc):
    ''' Remove a process from the set of this to be killed when a signal is
    received. This is for use when the Controller process is stopped. This
    method is idempotent '''
    self._active_processes.discard(proc)

  def __del__(self):
    if hasattr(self, 'process') and self.process != None: # if it fails in __init__, process may not have been assigned
      if self.process.poll():
        self._unregister_proc(self.process) # don't let this happen for shutdown
      else:
        self.kill() # make sure it is killed if this was started errantly

  def __init__(self, controller_config, sync_connection_manager, snapshot_service):
    ''' idx is the unique index for the controller used mostly for logging purposes '''
    self.config = controller_config
    self.state = ControllerState.DEAD
    self.process = None
    self.sync_connection_manager = sync_connection_manager
    self.sync_connection = None
    self.snapshot_service = snapshot_service
    self.log = logging.getLogger("Controller")
    # For network namespaces only:
    self.raw_socket = None

  @property
  def pid(self):
    ''' Return the PID of the Popen instance the controller was started with '''
    return self.process.pid if self.process else -1

  @property
  def label(self):
    ''' Return the label of this controller. See ControllerConfig for more details '''
    return self.config.label

  @property
  def cid(self):
    ''' Return the id of this controller. See ControllerConfig for more details '''
    return self.config.cid

  def kill(self):
    ''' Kill the process the controller is running in '''
    if self.state != ControllerState.ALIVE:
      self.log.warn("Killing controller %s when it is not alive!" % self.label)
      return
    msg.event("Killing controller %s" % self.cid)
    kill_procs([self.process])
    if self.config.kill_cmd != "":
      self.log.info("Killing controller %s: %s" % (self.label, " ".join(self.config.expanded_kill_cmd)))
      popen_filtered("[%s]" % self.label, self.config.expanded_kill_cmd, self.config.cwd)
    self._unregister_proc(self.process)
    self.process = None
    self.state = ControllerState.DEAD

  def start(self):
    ''' Start a new controller process based on the config's start_cmd
    attribute. Registers the Popen member variable for deletion upon a SIG*
    received in the simulator process '''
    if self.state != ControllerState.DEAD:
      self.log.warn("Starting controller %s when it is not dead!" % self.label)
      return
    if self.config.start_cmd == "":
      raise RuntimeError("No command found to start controller %s!" % self.label)
    self.log.info("Launching controller %s: %s" % (self.label, " ".join(self.config.expanded_start_cmd)))
    if self.config.launch_in_network_namespace:
      (self.raw_socket, self.process, _) = \
          launch_namespace(" ".join(self.config.expanded_start_cmd),
                           self.config.address, self.cid,
                           host_ip_addr_str=IPAddressSpace.find_unclaimed_address(ip_prefix=self.config.address))
    else:
      self.process = popen_filtered("[%s]" % self.label, self.config.expanded_start_cmd, self.config.cwd)
    self._register_proc(self.process)
    self.state = ControllerState.ALIVE

  def restart(self):
    if self.state != ControllerState.DEAD:
      self.log.warn("Restarting controller %s when it is not dead!" % self.label)
      return
    self.start()

  def check_status(self, simulation):
    ''' Check whether the actual status of the controller coincides with self.state. Returns a message
    entailing the details of the status '''
    if self.state == ControllerState.DEAD:
      return (True, "OK")
    if not self.process:
      return (False, "Controller %s: Alive, but no controller process found" % self.cid)
    rc = self.process.poll()
    if rc is not None:
      return (False, "Controller %s: Alive, but controller process terminated with return code %d" %
              (self.cid, rc))
    return (True, "OK")


class POXController(Controller):
  # N.B. controller-specific configuration is optional. The purpose of this
  # class is to load POX's syncproto module, which helps us reduce
  # non-determinism in POX.
  def __init__(self, controller_config, sync_connection_manager, snapshot_service):
    super(POXController, self).__init__(controller_config, sync_connection_manager, snapshot_service)
    self.log.info(" =====> STARTING POX CONTROLLER <===== ")

  def start(self):
    ''' Start a new POX controller process based on the config's start_cmd
    attribute. Registers the Popen member variable for deletion upon a SIG*
    received in the simulator process '''
    if self.state != ControllerState.DEAD:
      self.log.warn("Starting controller %s when controller is not dead!" % self.label)
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

      src_dir = os.path.join(os.path.dirname(__file__), "..")
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
            raise ValueError("Integrity violation: sts sync source path %s (abs: %s) does not exist" %
                (src_path, os.path.abspath(src_path)))
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
        self.log.warn("Could not find pox ext dir in %s. Cannot check/link in sync module" % pox_ext_dir)

    if self.config.start_cmd == "":
      raise RuntimeError("No command found to start controller %s!" % self.label)
    self.log.info("Launching controller %s: %s" % (self.label, " ".join(self.config.expanded_start_cmd)))
    if self.config.launch_in_network_namespace:
      (self.raw_socket, self.process, _) = \
          launch_namespace(" ".join(self.config.expanded_start_cmd),
                           self.config.address, self.cid,
                           host_ip_addr_str=IPAddressSpace.find_unclaimed_address(ip_prefix=self.config.address),
                           cwd=self.config.cwd, env=env)
    else:
      self.process = popen_filtered("[%s]" % self.label, self.config.expanded_start_cmd, self.config.cwd, env)
    self._register_proc(self.process)
    if self.config.sync:
      self.sync_connection = self.sync_connection_manager.connect(self, self.config.sync)
    self.state = ControllerState.ALIVE

class BigSwitchController(Controller):
  def __init__(self, controller_config, sync_connection_manager, snapshot_service):
    super(BigSwitchController, self).__init__(controller_config, sync_connection_manager, snapshot_service)
    self.log.info(" =====> STARTING BIG SWITCH CONTROLLER <===== ")

  def kill(self):
    if self.state != ControllerState.ALIVE:
      self.log.warn("Killing controller %s when controller is not alive!" % self.label)
      return
    if self.config.kill_cmd == "":
      raise RuntimeError("No command found to kill controller %s!" % self.label)
    self.log.info("Killing controller %s: %s" % (self.label, " ".join(self.config.expanded_kill_cmd)))
    p = popen_filtered("[%s]" % self.label, self.config.expanded_kill_cmd, self.config.cwd)
    p.wait()
    self.state = ControllerState.DEAD

  def start(self):
    if self.state != ControllerState.DEAD:
      self.log.warn("Starting controller %s when controller is not dead!" % self.label)
      return
    if self.config.start_cmd == "":
      raise RuntimeError("No command found to start controller %s!" % self.label)
    self.log.info("Launching controller %s: %s" % (self.label, " ".join(self.config.expanded_start_cmd)))
    p = popen_filtered("[%s]" % self.label, self.config.expanded_start_cmd, self.config.cwd)
    p.wait()
    self.state = ControllerState.STARTING

  def restart(self):
    if self.state != ControllerState.DEAD:
      self.log.warn("Restarting controller %s when controller is not dead!" % self.label)
      return
    if self.config.restart_cmd == "":
      raise RuntimeError("No command found to restart controller %s!" % self.label)
    self.log.info("Relaunching controller %s: %s" % (self.label, " ".join(self.config.expanded_restart_cmd)))
    p = popen_filtered("[%s]" % self.label, self.config.expanded_restart_cmd, self.config.cwd)
    p.wait()
    self.state = ControllerState.STARTING

  def check_status(self, simulation):
    if self.state == ControllerState.STARTING:
      return (True, "OK")
    # Retrieve status from script
    if self.config.check_status_cmd == "":
      raise RuntimeError("No command found to check status of controller %s!" % self.label)
    self.log.info("Checking status of controller %s: %s" % (self.label, " ".join(self.config.expanded_check_status_cmd)))
    p = popen_filtered("[%s]" % self.label, self.config.expanded_check_status_cmd, self.config.cwd, redirect_output=False)
    (out, _) = p.communicate()
    # Actual state is whether remote process exists
    actual_state = ControllerState.ALIVE if ("start" in out) else ControllerState.DEAD
    if self.state == ControllerState.DEAD and actual_state == ControllerState.ALIVE:
      return (False, "Dead, but controller process exists!")
    if self.state == ControllerState.ALIVE and actual_state == ControllerState.DEAD:
      return (False, "Alive, but no controller process found!")
    return (True, "OK")

