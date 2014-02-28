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

import abc
from itertools import count


class DirectedLinkAbstractClass(object):
  """
  A directed network link
  """
  __metaclass__ = abc.ABCMeta

  def __init__(self, start_node, start_port, end_node, end_port):
    if hasattr(start_node, 'has_port'):
      assert(start_node.has_port(start_node))
    if hasattr(end_node, 'has_port'):
      assert(end_node.has_port(end_node))
    self._start_node = start_node
    self._start_port = start_port
    self._end_node = end_node
    self._end_port = end_port

  @property
  def start_node(self):
    return self._start_node

  @property
  def start_port(self):
    return self._start_port

  @property
  def end_node(self):
    return self._end_node

  @property
  def end_port(self):
    return self._end_port

  def __eq__(self, other):
    return (self.start_node == getattr(other, 'start_node', None) and
      self.start_port == getattr(other, 'start_port', None) and
      self.end_node == getattr(other, 'end_node', None) and
      self.end_port == getattr(other, 'end_port', None))

  def __ne__(self, other):
    return not self.__eq__(other)

  def __repr__(self):
    return "(%d:%d) -> (%d:%d)" % (self.start_node, self.start_port,
                                   self.end_node, self.end_port)


  def create_reversed_link(self):
    """Create a Link that is in the opposite direction of this Link."""
    return DirectedLinkAbstractClass(self.end_node, self.end_port,
                self.start_node, self.start_port)


class BiDirectionalLinkAbstractClass(object):
  """
  An bi-directed network link
  """
  __metaclass__ = abc.ABCMeta

  def __init__(self, node1, port1, node2, port2):
    if hasattr(node1, 'has_port'):
      assert(node1.has_port(port1))
    if hasattr(node2, 'has_port'):
      assert(node2.has_port(port2))
    self._node1 = node1
    self._port1 = port1
    self._node2 = node2
    self._port2 = port2

  @property
  def node1(self):
    return self._node1

  @property
  def port1(self):
    return self._port1

  @property
  def node2(self):
    return self._node2

  @property
  def port2(self):
    return self._port2

  def __eq__(self, other):
    return ((self.node1 == getattr(other, 'node1', None) and
      self.port1 == getattr(other, 'port1', None) and
      self.node2 == getattr(other, 'node2', None) and
      self.port2 == getattr(other, 'port2', None)) or
      (self.node1 == getattr(other, 'node2', None) and
      self.port1 == getattr(other, 'port2', None) and
      self.node2 == getattr(other, 'node1', None) and
      self.port2 == getattr(other, 'port1', None)))

  def __ne__(self, other):
    return not self.__eq__(other)

  def __repr__(self):
    return "(%d:%d) <-> (%d:%d)" % (self.node1, self.port1,
                                   self.node2, self.port2)


class HostInterfaceAbstractClass(object):
  """Represents a host's network interface (e.g. eth0)"""
  def __init__(self, hw_addr, ips=[], name=""):
    self._hw_addr = hw_addr
    ips = [] if ips is None else ips
    self._ips = ips if isinstance(ips, list) else [ips]
    self._name = name

  @property
  def ips(self):
    """List of IP addresses assigned to this interface"""
    return self._ips

  @property
  def name(self):
    """Human Readable name for this interface"""
    return self._name

  @property
  def hw_addr(self):
    """Hardware address of this interface"""
    return self._hw_addr

  @abc.abstractproperty
  def port_no(self):
    """Port number"""
    raise NotImplementedError()

  @abc.abstractproperty
  def hw_addr_hash(self):
    """Hash for the HW address"""
    raise NotImplementedError()

  @abc.abstractproperty
  def ips_hashes(self):
    """List of hashes for the IP addresses assigned to this interface"""
    raise NotImplementedError()

  def __hash__(self):
    """Generate unique hash for this interface"""
    hash_code = self.hw_addr_hash
    for ip_hash in self.ips_hashes:
      hash_code += ip_hash
    hash_code += self.name.__hash__()
    return hash_code

  def __str__(self):
    return "HostInterface:" + self.name + ":" + str(self.hw_addr) +\
           ":" + str(self.ips)

  def __repr__(self):
    return self.__str__()


class HostAbstractClass(object):
  """
  Host abstract representation.
  """
  __metaclass__ = abc.ABCMeta

  _hids = count(1)

  def __init__(self, interfaces, name="", hid=None):
    """
    Init new host

    Options:
      - interfaces: list of network interfaces attached to the host.
      - name: human readable name of the host
      - hid: unique ID for the host
    """
    self._interfaces = interfaces
    self._hid = hid if hid is not None else self._hids.next()
    self._name = name if name else "Host%s" % self._hid

  @property
  def interfaces(self):
    return self._interfaces

  @property
  def name(self):
    return self._name

  @property
  def hid(self):
    return self._hid

  @abc.abstractmethod
  def send(self, interface, packet):
    """
    Send packet on a specific interface.
    """
    raise NotImplementedError()

  @abc.abstractmethod
  def receive(self, interface, packet):
    """
    Receive a packet from a specific interface.
    """
    raise NotImplementedError()

  def has_port(self, port):
    """Return True if the port is one of the interfaces"""
    return port in self.interfaces

  def __str__(self):
    "%s (%d)" % (self.name, self.hid)

  def __repr__(self):
    return "Host(%d)" % self.hid