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
Patch panel connects the different elements in the network together.
"""


import abc

from sts.util.capability import Capabilities

from sts.entities.base import DirectedLinkAbstractClass
from sts.entities.base import BiDirectionalLinkAbstractClass


def is_bidir_network_link(link):
  """Returns True if the link is bidirectional"""
  return not isinstance(link, DirectedLinkAbstractClass)


def is_network_link(link):
  """Returns True if link is a valid network link"""
  return isinstance(link, (DirectedLinkAbstractClass,
                           BiDirectionalLinkAbstractClass))


class PatchPanelCapabilities(Capabilities):
  """
  Expresses what a PatchPanel can/cannot do.
  """
  def __init__(self, can_create_network_link=True, can_add_network_link=True,
               can_remove_network_link=True, can_sever_network_link=True,
               can_repair_network_link=True, can_get_down_network_links=True,
               can_get_up_network_links=True, can_create_access_link=True,
               can_add_access_link=True, can_remove_access_link=True,
               can_sever_access_link=True, can_repair_access_link=True,
               can_get_down_access_links=True, can_get_up_access_links=True):
    self._can_create_network_link = can_create_network_link
    self._can_add_network_link = can_add_network_link
    self._can_remove_network_link = can_remove_network_link
    self._can_sever_network_link = can_sever_network_link
    self._can_repair_network_link = can_repair_network_link
    self._can_get_down_network_links = can_get_down_network_links
    self._can_get_up_network_links = can_get_up_network_links
    self._can_create_access_link = can_create_access_link
    self._can_add_access_link = can_add_access_link
    self._can_remove_access_link = can_remove_access_link
    self._can_sever_access_link = can_sever_access_link
    self._can_repair_access_link = can_repair_access_link
    self._can_get_down_access_links = can_get_down_access_links
    self._can_get_up_access_links = can_get_up_access_links

  @property
  def can_create_network_link(self):
    """
    True if the PatchPanel can create new link between two switches.
    """
    return self._can_create_network_link

  @property
  def can_add_network_link(self):
    """
    True if the PatchPanel can add a link (someone else created it) between
    two switches.
    """
    return self._can_add_network_link

  @property
  def can_remove_network_link(self):
    """
    True if the PatchPanel can removes a link between two switches.
    """
    return self._can_remove_network_link

  @property
  def can_sever_network_link(self):
    """
    True if the PatchPanel can bring a link down.
    """
    return self._can_sever_network_link

  @property
  def can_repair_network_link(self):
    """
    True if the PatchPanel can bring a link UP.
    """
    return self._can_repair_network_link

  @property
  def can_get_down_network_links(self):
    """
    True if the PatchPanel can check the status of the network links and
    return a list of the links that are DOWN.
    """
    return self._can_get_down_network_links

  @property
  def can_get_up_network_links(self):
    """
    True if the PatchPanel can check the status of the network links and
    return a list of the links that are UP.
    """
    return self._can_get_up_network_links

  @property
  def can_create_access_link(self):
    """
    True if the PatchPanel can create new link between a host and switch.
    """
    return self._can_create_access_link

  @property
  def can_add_access_link(self):
    """
    True if the PatchPanel can add a link (someone else created it) between
    a host and switch.
    """
    return self._can_add_access_link

  @property
  def can_remove_access_link(self):
    """
    True if the PatchPanel can removes a link between a host and switch.
    """
    return self._can_remove_access_link

  @property
  def can_sever_access_link(self):
    """
    True if the PatchPanel can bring an access link DOWN.
    """
    return self._can_sever_access_link

  @property
  def can_repair_access_link(self):
    """
    True if the PatchPanel can bring an access link UP.
    """
    return self._can_repair_access_link

  @property
  def can_get_down_access_links(self):
    """
    True if the PatchPanel can check the status of the access links and
    return a list of the links that are DOWN.
    """
    return self._can_get_down_access_links

  @property
  def can_get_up_access_links(self):
    """
    True if the PatchPanel can check the status of the access links and
    return a list of the links that are UP.
    """
    return self._can_get_up_access_links


class PatchPanelAbstractClass(object):
  """
  Patch panel connects the different elements in the network together.

  In this basic model, the patch panel has any-to-any connectivity, but it
  can be extended to support different models. Simply all ports for each
  network element are connected to the patch panel. The patch panel can connect
  any two ports (aka create a link) or disconnect them (bring the link down),
  or migrate hosts (change the switch side of the link).

  Since this is a simple model, this class is merely a data structure to track
  link status and migrate virtual links, but it can be extended to support
  a real patch panel (OVS or hardware)

  For the simulation purposes, the PatchPanel distinguishes between links
  connecting switches to hosts (AccessLinks) and links connecting switches
  (just Link).
  """

  __metaclass__ = abc.ABCMeta

  def __init__(self, capabilities):
    self.capabilities = capabilities

  @abc.abstractproperty
  def network_links(self):
    """Return list of internal network links"""
    raise NotImplementedError()

  @abc.abstractproperty
  def access_links(self):
    """Return list of access links (host->switch)"""
    raise NotImplementedError()

  @abc.abstractproperty
  def live_network_links(self):
    """Returns list of live internal network links"""
    raise NotImplementedError()

  @abc.abstractproperty
  def cut_network_links(self):
    """Returns list of network links that has been brought down"""
    raise NotImplementedError()

  @abc.abstractproperty
  def down_network_links(self):
    """
    Returns list of network links that are DOWN either by PatchPanel or due or
    other failure.
    This property is supposed to go and check the actual state of links.
    """
    raise NotImplementedError()

  @abc.abstractproperty
  def up_network_links(self):
    """
    Returns list of network links that are UP either by PatchPanel or due or
    other failure.
    This property is supposed to go and check the actual state of links.
    """
    raise NotImplementedError()

  @abc.abstractproperty
  def live_access_links(self):
    """Returns list of live access links"""
    raise NotImplementedError()

  @abc.abstractproperty
  def cut_access_links(self):
    """Returns list of access links that has been brought down"""
    raise NotImplementedError()

  @abc.abstractproperty
  def down_access_links(self):
    """
    Returns list of access links that are down either by PatchPanel or due or
    other failure.
    This property is supposed to go and check the actual state of links.
    """
    raise NotImplementedError()

  @abc.abstractproperty
  def up_access_links(self):
    """
    Returns list of access links that are UP either by PatchPanel or due or
    other failure.
    This property is supposed to go and check the actual state of links.
    """
    raise NotImplementedError()

  @abc.abstractmethod
  def is_port_connected(self, port):
    """
    Returns True if the port is currently connected to anything
    """
    raise NotImplementedError()

  @abc.abstractmethod
  def is_interface_connected(self, interface):
    """
    Returns True if the interface is currently connected to anything
    """
    raise NotImplementedError()

  @abc.abstractmethod
  def create_network_link(self, src_switch, src_port, dst_switch, dst_port,
                          bidir=False):
    """
    Create a unidirectional network (internal) link between two switches
    If a port is not provided and create_new_ports=True,
    an unused port in the corresponding switch is used.
    """
    raise NotImplementedError()

  @abc.abstractmethod
  def add_network_link(self, link):
    """Connect whatever necessary to make the link connected."""
    raise NotImplementedError()

  @abc.abstractmethod
  def remove_network_link(self, link):
    """
    Removes a network links between two switches.

    Basically says to the patch panel don't manage this link any more.
    """
    raise NotImplementedError()

  def switch_ports_iter(self, switch):
    """
    Helper method to iterate over ports for a given switch.
    Returns port_id and port object.
    """
    for port_id, port in switch.ports.iteritems():
      yield port_id, port

  @abc.abstractmethod
  def query_network_links(self, src_switch, src_port, dst_switch, dst_port):
    """
    Get links between two switches. Set port=None for wildcard query on port.
    Returns a `set`
    """
    raise NotImplementedError()

  @abc.abstractmethod
  def create_access_link(self, host, interface, switch, port):
    """
    Create an access link between a host and a switch.
    The new link wont be added to this manager.
    See
    """
    raise NotImplementedError()

  @abc.abstractmethod
  def add_access_link(self, link):
    """Connect whatever necessary to make the link connected."""
    raise NotImplementedError()

  @abc.abstractmethod
  def remove_access_link(self, link):
    """
    Removes access link between a host and a switch.
    """
    raise NotImplementedError()

  def host_interfaces_iter(self, host):
    """
    Helper method to iterate over interfaces for a given host.
    Returns interface id and Interface object.
    """
    for interface in host.interfaces:
      yield interface.port_no, interface

  @abc.abstractmethod
  def query_access_links(self, host, interface, switch, port):
    """
    Get links between a host and a switch.
    Set port=None for wildcard query on port, and interface=None to wildcard it.
    Returns a `set`
    """
    raise NotImplementedError()

  @abc.abstractmethod
  def get_other_side(self, node, port):
    """
    Given a node and a port, return a tuple (node, port) that is directly
    connected to the port.

    This can be used in 2 ways
    - node is a Host type and port is a HostInterface type
    - node is a Switch type and port is a ofp_phy_port type.
    """
    raise NotImplementedError()

  @abc.abstractmethod
  def sever_network_link(self, link):
    """
    Disconnect link
    """
    raise NotImplementedError()

  @abc.abstractmethod
  def repair_network_link(self, link):
    """Bring a link back online"""
    raise NotImplementedError()

  @abc.abstractmethod
  def sever_access_link(self, link):
    """
    Disconnect host-switch link
    """
    raise NotImplementedError()

  @abc.abstractmethod
  def repair_access_link(self, link):
    """Bring a link back online"""
    raise NotImplementedError()


class PatchPanelBK(PatchPanelAbstractClass):
  """
  This class implements the bookkeeping methods of PatchPanelAbstractClass to
  make it easier to extend.
  """

  __metaclass__ = abc.ABCMeta


  def __init__(self, network_link_factory, access_link_factory,
               capabilities=PatchPanelCapabilities(), is_network_link=is_network_link,
               is_bidir_network_link=is_bidir_network_link,
               is_access_link=is_network_link):
    super(PatchPanelBK, self).__init__(capabilities=capabilities)
    self.is_network_link = is_network_link
    self.is_bidir_network_link = is_bidir_network_link
    self.network_link_factory = network_link_factory
    self.is_access_link = is_access_link
    self.access_link_factory = access_link_factory

    self._cut_network_links = set()
    self._cut_access_links = set()
    self.port2access_link = {}
    self.interface2access_link = {}
    self.src_port2internal_link = {}
    self.dst_port2internal_link = {}

  @property
  def network_links(self):
    """Return list of internal network links"""
    return list(set(self.src_port2internal_link.values()))

  @property
  def live_network_links(self):
    """Returns list of live internal network links"""
    return set(self.network_links) - self.cut_network_links

  @property
  def cut_network_links(self):
    """Returns list of links have been brought down."""
    return self._cut_network_links

  @property
  def up_network_links(self):
    """
    Returns list of UP Links, Checks the actual status of network links.
    """
    assert self.capabilities.can_get_up_network_links
    return set(self.network_links) - self.cut_network_links

  @property
  def down_network_links(self):
    """
    Returns list of DOWN Links, Checks the actual status of network links.
    """
    assert self.capabilities.can_get_down_network_links
    return set(self.network_links) - self.cut_network_links

  @property
  def access_links(self):
    """Returns list of access links (host->switch)"""
    return self.interface2access_link.values()

  @property
  def live_access_links(self):
    """Return list of live access links"""
    return set(self.access_links) - self.cut_access_links

  @property
  def cut_access_links(self):
    """Returns list of access links have been brought down."""
    return self._cut_access_links

  @property
  def up_access_links(self):
    """
    Returns list of UP Links, Checks the actual status of network links.
    """
    assert self.capabilities.can_get_up_access_links
    return set(self.access_links) - self.cut_access_links

  @property
  def down_access_links(self):
    """
    Returns list of DOWN Links, Checks the actual status of network links.
    """
    assert self.capabilities.can_get_down_access_links
    return set(self.access_links) - self.cut_access_links

  def is_port_connected(self, port):
    """
    Returns True if the port is currently connected to anything.
    """
    return (port in self.port2access_link or
            port in self.interface2access_link or
            port in self.src_port2internal_link or
            port in self.dst_port2internal_link)

  def is_interface_connected(self, interface):
    """
    Returns True if the interface is currently connected to anything.
    """
    return interface in self.interface2access_link

  def find_unused_interface(self, host):
    """
    Find a host's unused interface; if no such interface exists, return None.
    """
    for interface in host.interfaces:
      if not self.is_interface_connected(interface):
        return interface
    return None

  def find_unused_port(self, switch):
    """
    Find a switch's unused port; if no such port exists, return None.
    """
    for _, port in switch.ports.iteritems():
      if not self.is_port_connected(port):
        return port
    return None

  def create_network_link(self, src_switch, src_port, dst_switch, dst_port,
                          bidir=False):
    """
    Create a unidirectional network (internal) link between two switches.
    The new link wont be added to this manager.
    See `add_network_link`.
    """
    assert self.capabilities.can_create_network_link
    assert src_port is not None
    assert dst_port is not None
    link = self.network_link_factory(src_switch, src_port, dst_switch, dst_port)
    return link

  def add_network_link(self, link):
    """Connect whatever necessary to make the link connected."""
    assert self.capabilities.can_add_network_link
    assert self.is_network_link(link), link
    if self.is_bidir_network_link(link):
      self.src_port2internal_link[link.port1] = link
      self.src_port2internal_link[link.port2] = link
      self.dst_port2internal_link[link.port1] = link
      self.dst_port2internal_link[link.port2] = link
    else:
      self.src_port2internal_link[link.start_port] = link
      self.dst_port2internal_link[link.end_port] = link
    return link

  def remove_network_link(self, link):
    """
    Removes a network links between two switches.

    Basically says to the patch panel don't manage this link any more.
    """
    assert self.capabilities.can_remove_network_link
    assert self.is_network_link(link)
    assert link in self.network_links
    if self.is_bidir_network_link(link):
      del self.src_port2internal_link[link.port1]
      del self.src_port2internal_link[link.port2]
      del self.dst_port2internal_link[link.port1]
      del self.dst_port2internal_link[link.port2]
    else:
      del self.src_port2internal_link[link.start_port]
      del self.dst_port2internal_link[link.end_port]

  def query_network_links(self, src_switch, src_port, dst_switch, dst_port):
    """
    Get links between two switches. Set port=None for wildcard query on port.
    Returns a `set`
    """
    links = []
    for _, port in self.switch_ports_iter(src_switch):
      if port not in self.src_port2internal_link.keys():
        # Port is not connected, skip it
        continue
      link = self.src_port2internal_link[port]
      if link in links:
        continue
      is_bidr = self.is_bidir_network_link(link)
      if is_bidr:
        if set([src_switch, dst_switch]) != set([link.node1, link.node2]):
          continue
        if src_port is not None and src_port not in [link.port1, link.port2]:
          continue
        if dst_port is not None and dst_port not in [link.port1, link.port2]:
          continue
        # Special case that would escape the previous checks
        if (src_port == dst_port and src_port is not None and
                link.port1 != link.port2):
          continue
      elif not is_bidr:
        if link.start_node != src_switch:
          continue
        if link.end_node != dst_switch:
          continue
        if src_port is not None and src_port != link.start_port:
          continue
        if dst_port is not None and dst_port != link.end_port:
          continue
      links.append(link)
    return set(links)

  def create_access_link(self, host, interface, switch, port):
    """
    Create an access link between a host and a switch.
    The new link wont be added to this manager.
    See `add_access_link`.
    """
    assert self.capabilities.can_create_access_link
    assert port is not None
    assert interface is not None
    link = self.access_link_factory(host, interface, switch, port)
    return link

  def add_access_link(self, link):
    """Connects whatever necessary to make the link connected."""
    assert self.capabilities.can_add_access_link
    assert self.is_access_link(link)
    self.port2access_link[link.switch_port] = link
    self.interface2access_link[link.interface] = link
    return link

  def remove_access_link(self, link):
    """
    Removes access link between a host and a switch.
    """
    assert self.capabilities.can_remove_access_link
    assert link in self.access_links
    del self.interface2access_link[link.interface]
    del self.port2access_link[link.switch_port]

  def query_access_links(self, host, interface, switch, port):
    """
    Get links between a host and a switch.
    Set port=None for wildcard query on port, and interface=None to wildcard it.
    Returns a `set`
    """
    links = []
    for _, iface in self.host_interfaces_iter(host):
      if iface not in self.interface2access_link:
        continue
      link = self.interface2access_link[iface]
      if link.host != host:
        continue
      if interface is not None and iface != interface:
        continue
      if link.switch != switch:
        continue
      if port is not None and port != link.switch_port:
        continue
      links.append(link)
    return set(links)

  def get_other_side(self, node, port):
    """
    Given a node and a port, return a tuple (node, port) that is directly
    connected to the port.

    This can be used in 2 ways
    - node is a Host type and port is a HostInterface type
    - node is a Switch type and port is a switch port type.
    """
    if port in self.port2access_link:
      access_link = self.port2access_link[port]
      return access_link.host, access_link.interface
    if port in self.interface2access_link:
      access_link = self.interface2access_link[port]
      return access_link.switch, access_link.switch_port
    elif port in self.src_port2internal_link:
      network_link = self.src_port2internal_link[port]
      return network_link.end_node, network_link.end_port
    if port in self.dst_port2internal_link:
      network_link = self.dst_port2internal_link[port]
      return network_link.start_node, network_link.start_port
    else:
      raise ValueError("Unknown port %s on node %s" % (str(port), str(node)))

  @abc.abstractmethod
  def sever_network_link(self, link):
    """
    Disconnect link
    """
    raise NotImplementedError()

  @abc.abstractmethod
  def repair_network_link(self, link):
    """Bring a link back online"""
    raise NotImplementedError()

  @abc.abstractmethod
  def sever_access_link(self, link):
    """
    Disconnect host-switch link
    """
    raise NotImplementedError()

  @abc.abstractmethod
  def repair_access_link(self, link):
    """Bring a link back online"""
    raise NotImplementedError()
