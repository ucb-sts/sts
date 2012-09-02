"""
This module mocks out openflow switches, links, and hosts. These are all the
'entities' that exist within our simulated environment.
"""

from pox.openflow.software_switch import SoftwareSwitch, DpPacketOut
from pox.openflow.nx_software_switch import NXSoftwareSwitch
from pox.lib.util import connect_socket_with_backoff, assert_type
from pox.openflow.libopenflow_01 import *
from pox.lib.revent import Event, EventMixin
from sts.procutils import popen_filtered, kill_procs

import logging
import pickle
import signal

class FuzzSoftwareSwitch (NXSoftwareSwitch):
  """
  A mock switch implementation for testing purposes. Can simulate dropping dead.
  """
  def __init__ (self, create_io_worker, dpid, name=None, ports=4, miss_send_len=128,
                n_buffers=100, n_tables=1, capabilities=None):
    NXSoftwareSwitch.__init__(self, dpid, name, ports, miss_send_len, n_buffers, n_tables, capabilities)

    self.create_io_worker = create_io_worker

    self.failed = False
    self.log = logging.getLogger("FuzzSoftwareSwitch(%d)" % dpid)

    def error_handler(e):
      self.log.exception(e)
      raise e

    self.error_handler = error_handler
    self.controller_info = []

  def add_controller_info(self, info):
    self.controller_info.append(info)

  def _handle_ConnectionUp(self, event):
    self._setConnection(event.connection, event.ofp)

  def connect(self):
    # NOTE: create_io_worker is /not/ an instancemethod but just a function
    # so we have to pass in the self parameter explicitly
    for info in self.controller_info:
      io_worker = self.create_io_worker(self, info)
      conn = self.set_io_worker(io_worker)
      # cause errors to be raised
      conn.error_handler = self.error_handler

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

  def recover(self):
    if not self.failed:
      self.log.warn("Switch already up")
      return
    self.connect()
    self.failed = False

  def serialize(self):
    # Skip over non-serializable data, e.g. sockets
    # TODO(cs): is self.log going to be a problem?
    serializable = MockOpenFlowSwitch(self.dpid, self.parent_controller_name)
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

  def __hash__(self):
    return (self.start_software_switch.__hash__() +  self.start_port.__hash__() +
           self.end_software_switch.__hash__() +  self.end_port.__hash__())

  def __repr__(self):
    return "(%d:%d) -> (%d:%d)" % (self.start_software_switch.dpid, self.start_port.port_no,
                                   self.end_software_switch.dpid, self.end_port.port_no)

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
  def __init__(self, mac, ip_or_ips=[], name=""):
    self.mac = mac
    if type(ip_or_ips) != list:
      ip_or_ips = [ip_or_ips]
    self.ips = ip_or_ips
    self.name = name

  def __eq__(self, other):
    if type(other) != HostInterface:
      return False
    if self.mac.toInt() != other.mac.toInt():
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
    hash_code = self.mac.toInt().__hash__()
    for ip in self.ips:
      hash_code += ip.toUnsignedN().__hash__()
    hash_code += self.name.__hash__()
    return hash_code

  def __str__(self, *args, **kwargs):
    return "HostInterface:" + self.name + ":" + str(self.mac) + ":" + str(self.ips)

  def __repr__(self, *args, **kwargs):
    return self.__str__()

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

  def __init__(self, interfaces, name=""):
    '''
    - interfaces A list of HostInterfaces
    '''
    self.interfaces = interfaces
    self.log = logging.getLogger(name)
    self.name = name

  def send(self, interface, packet):
    ''' Send a packet out a given interface '''
    self.raiseEvent(DpPacketOut(self, packet, interface))

  def receive(self, interface, packet):
    '''
    Process an incoming packet from a switch

    Called by PatchPanel
    '''
    self.log.info("received packet on interface %s: %s" % (interface.name, str(packet)))

  def __str__(self):
    return self.name

class Controller(object):
  '''Encapsulates the state of a running controller.'''

  _active_processes = set() # set of processes that are currently running. These are all killed upon signal reception

  @staticmethod
  def kill_active_procs():
    '''Kill the active processes. Used by the simulator module to shut down the
    controllers because python can only have a single method to handle SIG* stuff.'''
    kill_procs(Controller._active_processes)

  def _register_proc(self, proc):
    '''Register a Popen instance that a controller is running in for the cleanup
    that happens when the simulator receives a signal. This method is idempotent.'''
    self._active_processes.add(proc)

  def _unregister_proc(self, proc):
    '''Remove a process from the set of this to be killed when a signal is
    received. This is for use when the Controller process is stopped. This
    method is idempotent.'''
    self._active_processes.discard(proc)

  def __del__(self):
    if hasattr(self, 'process'): # if it fails in __init__, process may not have been assigned
      if self.process.poll():
        self._unregister_proc(self.process) # don't let this happen for shutdown
      else:
        self.kill() # make sure it is killed if this was started errantly

  def __init__(self, controller_config):
    '''idx is the unique index for the controller used mostly for logging purposes.'''
    self.config = controller_config
    self.start()

  @property
  def pid(self):
    '''Return the PID of the Popen instance the controller was started with.'''
    return self.process.pid

  @property
  def uuid(self):
    '''Return the uuid of this controller. See ControllerConfig for more details.'''
    return self.config.uuid

  def kill(self):
    '''Kill the process the controller is running in.'''
    kill_procs([self.process])
    self._unregister_proc(self.process)

  def start(self):
    '''Start a new controller process based on the config's cmdline
    attribute. Registers the Popen member variable for deletion upon a SIG*
    received in the simulator process.'''
    self.process = popen_filtered("c%s" % str(self.uuid), self.config.cmdline)
    self._register_proc(self.process)

    if self.config.nom_port:
      self.nom_socket = connect_socket_with_backoff(self.config.address,
                                                    self.config.nom_port)

  def restart(self):
    self.kill()
    self.start()

  def send_policy_request(self, controller, api_call):
    pass

