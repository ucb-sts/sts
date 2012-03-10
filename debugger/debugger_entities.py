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

import logging
import pickle

# TODO: model hosts in the network!

class FuzzSwitchImpl (SwitchImpl):
  """
  NOTE: a mock switch implementation for testing purposes. Can simulate dropping dead.
  """
  def __init__ (self, create_io_worker, dpid, name=None, ports=4, miss_send_len=128,
                n_buffers=100, n_tables=1, capabilities=None):
    SwitchImpl.__init__(self, dpid, name, ports, miss_send_len, n_buffers, n_tables, capabilities)

    self.create_io_worker = create_io_worker

    self.failed = False
    self.log = logging.getLogger("FuzzSwitchImpl(%d)" % dpid)

    def error_handler(e):
      self.log.exception(e)
      raise e

    self.error_handler = error_handler

  def _handle_ConnectionUp(self, event):
    self._setConnection(event.connection, event.ofp)

  def connect(self):
    # NOTE: create_io_worker is /not/ an instancemethod but just a function
    # so we have to pass in the self parameter explicitely
    io_worker = self.create_io_worker(self)

    conn = self.set_io_worker(io_worker)
    # cause errors to be raised
    conn.error_handler = self.error_handler

  def fail(self):
    # TODO: depending on the type of failure, a real switch failure
    # might not lead to an immediate disconnect
    if self.failed:
      self.log.warn("Switch already failed")
      return
    self.failed = True

    self._connection.close()
    self._connection = None

  def recover(self):
    if not self.failed:
      self.log.warn("Switch already up")
      return
    self.connect()
    self.failed = False

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
    
  def __eq__(self, other):
    if not type(other) == Link:
      return False
    return (self.start_switch_impl == other.start_switch_impl and
           self.start_port == other.start_port and
           self.end_switch_impl == other.end_switch_impl and
           self.end_port == other.end_port)
  
    
  def __repr__(self):
    return "(%d:%d) -> (%d:%d)" % (self.start_switch_impl.dpid, self.start_port.port_no, 
                                   self.end_switch_impl.dpid, self.end_port.port_no)
