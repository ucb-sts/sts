"""
This module mocks out openflow switches.

This is only for simulation, not emulation. For simluation, we run everything
in the same process, and mock out switch behavior. This way it's super easy
to track the state of the system at any point in time (total ordering of events).

Eventually, we want to test the entire stack. We're also going to want to
allow for the possibility of consistency bugs, which will imply separate
processes. To emulate, we'll want to :
    - Boot up MiniNet with some open v switches
    - inject randomly generated traffic to the switches themselves. This brings up two questions:
        * Is it possible to package a MiniNet VM as part of POX? That would
          go against the grain of POX's python-only, pre-packaged everything
          philosophy.
        * Can this module successfully interpose on all messages between vswitches
          and the control application?
"""

from pox.openflow.switch_impl import SwitchImpl
from pox.lib.util import connect_socket_with_backoff
 
import pickle

# TODO: model hosts in the network!

class FuzzSwitchImpl (SwitchImpl):
  """
  NOTE: a mock switch implementation for testing purposes. Can simulate dropping dead.
  """
  def __init__ (self, io_worker_constructor, io_worker_destructor, dpid, name=None, ports=4, miss_send_len=128,
                n_buffers=100, n_tables=1, capabilities=None):
    SwitchImpl.__init__(self, dpid, name=None, ports=4, miss_send_len=128,
      n_buffers=100, n_tables=1, capabilities=None)
    self.failed = False
    self.io_worker_constructor = io_worker_constructor
    self.io_worker_destructor = io_worker_destructor

  def _handle_ConnectionUp(self, event):
    self._setConnection(event.connection, event.ofp)

  def fail(self):
    # TODO: depending on the type of failure, a real switch failure
    # might not lead to an immediate disconnect
    if self.failed:
      self.log.warn("Switch already failed")
      return
    self.failed = True
    
    # Store the controller's address and port so we can reconnect later
    (self.controller_address, self.controller_port) = self._connection.io_worker.socket.getpeername()
    self.io_worker_destructor(self._connection.io_worker)
    self._connection = None

  def recover(self):
    if not self.failed:
      self.log.warn("Switch already up")
      return
    self.failed = False
    # Reconnect by creating a brand new tcp socket
    controller_socket = connect_socket_with_backoff(self.controller_address, self.controller_port)
    # Set non-blocking
    controller_socket.setblocking(0)
    io_worker = self.io_worker_constructor(controller_socket)
    self.set_socket(io_worker)

  def serialize(self):
    # Skip over non-serializable data, e.g. sockets
    # TODO: is self.log going to be a problem?
    serializable = MockOpenFlowSwitch(self.dpid, self.parent_controller_name)
    # Can't serialize files
    serializable.log = None
    # TODO: need a cleaner way to add in the NOM port representation
    if self.switch_impl:
      serializable.ofp_phy_ports = self.switch_impl.ports.values()
    return pickle.dumps(serializable, protocol=0)

class Link():
  """
  Temporary stand in for Murphy's graph-library for the NOM.

  Note: Directed!
  """
  def __init__(self, start_switch_impl, start_port, end_switch_impl, end_port):
    self.start_switch_impl = start_switch_impl
    self.start_port = start_port
    self.end_switch_impl = end_switch_impl
    self.end_port = end_port

class Message (object):
  """ So we can track a message throughout the network """
  def __init__(self, msg):
    self.in_transit = False
    self.delayed_rounds = 0
    self.msg = msg
