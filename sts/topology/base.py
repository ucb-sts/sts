# Copyright 2011-2013 Colin Scott
# Copyright 2012-2013 Andrew Or
# Copyright 2011-2013 Andreas Wundsam
# Copyright 2012-2013 Sam Whitlock
# Copyright 2012-2012 Kyriakos Zarifis
# Copyright 2014      Ahmed El-Hassany
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
Basic representation of network topology.
"""

import logging

from sts.util.console import msg
from sts.util.capability import Capabilities

from sts.topology.graph import TopologyGraph


class TopologyCapabilities(Capabilities):
  """Basic topology settings for network topologies"""
  def __init__(self, can_create_host=True, can_add_host=True,
               can_create_interface=True, can_remove_host=True,
               can_create_switch=True, can_add_switch=True,
               can_remove_switch=True, can_create_network_link=True,
               can_add_network_link=True,
               can_remove_network_link=True, can_create_access_link=True,
               can_add_access_link=True, can_remove_access_link=True,
               can_change_link_status=True,
               can_change_access_link_status=True,
               can_add_controller=True, can_remove_controller=True,
               _can_get_connected_controllers=True):
    super(TopologyCapabilities, self).__init__()
    self._can_create_interface = can_create_interface
    self._can_create_host = can_create_host
    self._can_add_host = can_add_host
    self._can_remove_host = can_remove_host
    self._can_create_switch = can_create_switch
    self._can_add_switch = can_add_switch
    self._can_remove_switch = can_remove_switch
    self._can_create_network_link = can_create_network_link
    self._can_add_network_link = can_add_network_link
    self._can_remove_network_link = can_remove_network_link
    self._can_create_access_link = can_create_access_link
    self._can_add_access_link = can_add_access_link
    self._can_remove_access_link = can_remove_access_link
    self._can_change_link_status = can_change_link_status
    self._can_change_access_link_status = can_change_access_link_status
    self._can_add_controller = can_add_controller
    self._can_remove_controller = can_remove_controller
    self._can_get_connected_controllers = _can_get_connected_controllers
    # more for OF and per packet

  @property
  def can_create_interface(self):
    """Returns True if host interfaces can be created."""
    return self._can_create_interface

  @property
  def can_create_host(self):
    """Returns True if hosts can be created."""
    return self._can_create_host

  @property
  def can_add_host(self):
    """Returns True if hosts can be added to the topology."""
    return self._can_add_host

  @property
  def can_remove_host(self):
    """Returns True if hosts can be removed from the topology."""
    return self._can_remove_host

  @property
  def can_create_switch(self):
    """Returns True if switches can be created."""
    return self._can_create_switch

  @property
  def can_add_switch(self):
    """Returns True if switches can be added to the topology."""
    return self._can_add_switch

  @property
  def can_remove_switch(self):
    """Returns True if switches can be removed from the topology."""
    return self._can_remove_switch

  @property
  def can_create_network_link(self):
    """Returns True if network links can be created."""
    return self._can_create_network_link

  @property
  def can_add_network_link(self):
    """Returns True if links can be added to the topology."""
    return self._can_add_network_link

  @property
  def can_remove_network_link(self):
    """Returns True if links can be removed from the topology."""
    return self._can_remove_network_link

  @property
  def can_create_access_link(self):
    """Returns True if access links can be created."""
    return self._can_create_access_link

  @property
  def can_add_access_link(self):
    """Returns True if Access links can be added to the topology."""
    return self._can_add_access_link

  @property
  def can_remove_access_link(self):
    """Returns True if links can be removed from the topology."""
    return self._can_remove_access_link

  @property
  def can_change_link_status(self):
    """Returns True if links can change status (up or down)."""
    return self._can_change_link_status

  @property
  def can_change_access_link_status(self):
    """Returns True if links can change status (up or down)."""
    return self._can_change_access_link_status

  @property
  def can_add_controller(self):
    """Returns True if controllers can be added to the topology."""
    return self._can_add_controller

  @property
  def can_remove_controller(self):
    """Returns True if controllers can be removed from the topology."""
    return self._can_remove_controller

  @property
  def can_get_connected_controllers(self):
    """
    Returns True if for a given switch can return the list of connected
    controllers to it.
    """
    return self._can_get_connected_controllers


class Topology(object):
  """Keeps track of the network elements.

  Topology is just a director of network state. The actual work is done by:
    - TopologyGraph: A graph of the network elements (currently DataPlane only)
    - SwitchesManager: Manages switches in the network
    - HostManager
    - PatchPanel: Manages dataplane links

  """
  def __init__(self, hosts_manager, switches_manager, patch_panel,
               controllers_manager, capabilities, is_host, is_switch,
               is_network_link, is_access_link, is_host_interface, is_port,
               sts_console=msg):
    """
    Args:
      - is_*(x): return True if x is of correct type.
    """
    super(Topology, self).__init__()
    # Make sure the required arguments are passed
    assert is_host is not None, "Host check is defined"
    assert is_switch is not None, "Switch check is not defined"
    assert is_network_link is not None, "Link check is not defined"
    assert is_access_link is not None, "Access Link check is not defined"
    assert is_host_interface is not None, "Interface check is not defined"
    assert is_port is not None, "Port check is not defined"
    assert capabilities is not None, "Topology's Capabilities is not defined"
    self.is_host = is_host
    self.is_switch = is_switch
    self.is_network_link = is_network_link
    self.is_access_link = is_access_link
    self.is_host_interface = is_host_interface
    self.is_port = is_port

    self._patch_panel = patch_panel
    self._switches_manager = switches_manager
    self._hosts_manager = hosts_manager
    self._controllers_manager = controllers_manager
    self._graph = TopologyGraph()

    self.msg = sts_console
    self.log = logging.getLogger("sts.topology.base.Topology")
    self.capabilities = capabilities

    # Read existing hosts from the HostsManager
    for host in self.hosts_manager.hosts:
      self._graph.add_host(host)
    # Read existing switches from the SwitchesManager
    for switch in self.switches_manager.switches:
      self._graph.add_switch(switch)
    # Read existing links from PatchPanel
    for link in self.patch_panel.access_links:
      self._graph.add_link(link)
    for link in self.patch_panel.network_links:
      self._graph.add_link(link)

  @property
  def hosts_manager(self):
    """
    Returns read-only reference to the hosts manager.

    See: `sts.topology.hosts_manager.HostsManagerAbstractClass`
    """
    # TODO (AH): Return immutable copy
    return self._hosts_manager

  @property
  def switches_manager(self):
    """
    Returns read-only reference to the switches manager.

    See: `sts.topology.switches_manager.SwitchesManagerAbstractClass`
    """
    # TODO (AH): Return immutable copy
    return self._switches_manager

  @property
  def patch_panel(self):
    """
    Returns read-only reference to the links patch panel.

    See: `sts.topology.patch_panel.PatchPanel`
    """
    # TODO (AH): Return immutable copy
    return self._patch_panel

  @property
  def controllers_manager(self):
    """
    Returns read-only reference to the links patch panel.

    See: `sts.topology.patch_panel.PatchPanel`
    """
    # TODO (AH): Return immutable copy
    self._controllers_manager

  @property
  def graph(self):
    """Return the graph of the network."""
    # TODO (AH): Return immutable copy of the graph
    return self._graph

  def create_host(self, hid, name=None, interfaces=None):
    """
    Creates new host and adds it to the topology.

    See: `sts.topology.hosts_manager.HostsManager.create_host`
    """
    assert self.capabilities.can_create_host
    host = self.hosts_manager.create_host(hid=hid, name=name,
                                          interfaces=interfaces)
    self.add_host(host)
    return host

  def create_interface(self, hw_addr, ip_or_ips=None, name=None):
    """
    Creates interface for host.
    The interface is not attached to any host after calling this method.

    See: `sts.topology.hosts_manager.HostsManager.create_interface`
    """
    assert self.capabilities.can_create_interface
    iface = self.hosts_manager.create_interface(hw_addr=hw_addr,
                                                ip_or_ips=ip_or_ips,
                                                name=name)
    return iface

  def create_host_with_interfaces(self, hid, name, num_interfaces,
                                  mac_generator, ip_generator,
                                  interface_name_generator):
    """
    Create new hosts with the specified number of interfaces and adds to the
    topology.

    See: `sts.topology.hosts_manager.HostsManager.create_host_with_interfaces`
    """
    assert self.capabilities.can_create_host
    assert self.capabilities.can_create_interface
    host = self.hosts_manager.create_host_with_interfaces(
      hid=hid, name=name, num_interfaces=num_interfaces,
      mac_generator=mac_generator, ip_generator=ip_generator,
      interface_name_generator=interface_name_generator)
    self.add_host(host)
    return host

  def add_host(self, host):
    """
    Add Host to the topology.

    Args:
      host: Must be an instance of sts.entities.hosts.HostAbstractClass
    """
    assert self.capabilities.can_add_host
    assert self.is_host(host)
    assert not self._graph.has_host(host), "Host '%s' already added" % host
    self.hosts_manager.add_host(host)
    hid = self._graph.add_host(host)
    return hid

  def remove_host(self, host):
    """
    Removes host (with all associated links) from the topology
    """
    assert self.capabilities.can_remove_host
    assert self._graph.has_host(host)
    self.hosts_manager.remove_host(host)
    connected_links = self._graph.get_host_links(host)
    for link in connected_links:
      self.remove_access_link(link)
    self._graph.remove_host(host)

  def migrate_host(self, old_switch, old_port, new_switch, new_port):
    """
    Migrate the host from the old (ingress switch, port) to the new
    (ingress switch, port). Note that the new port must not already be
    present, otherwise an exception will be thrown (we treat all switches as
    configurable software switches for convenience, rather than hardware switches
    with a fixed number of ports)
    """
    # TODO (AH): Implement migrate host
    raise NotImplemented()

  def create_switch(self, switch_id, num_ports, can_connect_to_endhosts=True):
    """
    Creates new switch and adds it to the topology.

    See: `sts.topology.switches_manager.SwitchesManager.create_switch`
    """
    assert self.capabilities.can_create_switch
    switch = self.switches_manager.create_switch(
      switch_id=switch_id, num_ports=num_ports,
      can_connect_to_endhosts=can_connect_to_endhosts)
    self.add_switch(switch)
    return switch

  def add_switch(self, switch):
    """Adds switch to the topology"""
    assert self.capabilities.can_add_switch
    assert self.is_switch(switch)
    self._switches_manager.add_switch(switch)
    self._graph.add_switch(switch)
    return switch

  def remove_switch(self, switch):
    """Removes switch (and all associated links) from the topology"""
    assert self.capabilities.can_remove_switch
    self._switches_manager.remove_switch(switch)
    connected_links = self._graph.get_switch_links(switch)
    for link in connected_links:
      if self.is_network_link(link):
        self.remove_network_link(link)
      else:
        self.remove_access_link(link)
    self._graph.remove_switch(switch)

  def add_link(self, link):
    """Add link to the topology"""
    assert self.is_network_link(link) or self.is_access_link(link)
    if self.is_network_link(link):
      assert self.capabilities.can_add_network_link
    elif self.is_access_link(link):
      assert self.capabilities.can_add_access_link
    assert not self._graph.has_link(link)
    if hasattr(link, 'start_node'):
      bidir = False
    else:
      bidir = True
    self._graph.add_link(link, bidir=bidir)
    # Make sure the patch panel do whatever physically necessary to connect
    # the link
    if self.is_access_link(link):
      self.patch_panel.add_access_link(link)
    elif self.is_network_link(link):
      self.patch_panel.add_network_link(link)
    return link

  def add_network_link(self, link):
    """Add Network link to the topology"""
    return self.add_link(link)

  def add_access_link(self, link):
    """Add Access link to the topology"""
    return self.add_link(link)

  def sever_network_link(self, link):
    """Brings link down"""
    self.patch_panel.sever_network_link(link)

  def repair_network_link(self, link):
    """Brings link back up"""
    self.patch_panel.repair_network_link(link)

  def create_access_link(self, host, interface, switch, port):
    assert self.capabilities.can_create_access_link
    assert self._graph.has_host(host)
    assert self._graph.has_switch(switch)
    link = self.patch_panel.create_access_link(host, interface, switch, port)
    self.add_access_link(link)
    return link

  def create_network_link(self, src_switch, src_port, dst_switch, dst_port,
                          bidir=False):
    assert self.capabilities.can_create_network_link
    assert self._graph.has_switch(src_switch)
    assert self._graph.has_switch(dst_switch)
    link = self.patch_panel.create_network_link(src_switch, src_port,
                                                dst_switch, dst_port,
                                                bidir=bidir)
    self.add_link(link)
    return link

  def remove_access_link(self, link):
    assert self.capabilities.can_remove_access_link
    assert link in self.patch_panel.access_links
    assert self._graph.has_link(link)
    self._graph.remove_link(link)
    self.patch_panel.remove_access_link(link)

  def remove_network_link(self, link):
    assert self.capabilities.can_remove_network_link
    assert link in self.patch_panel.network_links
    assert self._graph.has_link(link)
    self._graph.remove_link(link)
    self.patch_panel.remove_network_link(link)

  def add_controller(self, controller):
    """Adds controller to the topology"""
    assert self.capabilities.can_add_controller
    self._controllers_manager.add_controller(controller)
    return controller

  def remove_controller(self, controller):
    """Removes a controller from the topology."""
    assert self.capabilities.can_remove_controller
    assert controller in self.controllers_manager.controllers
    self._controllers_manager.remove_controller(controller)

  def get_connected_controllers(self, switch):
    """Returns a list of the controllers that switch is connected to."""
    assert self.capabilities.can_get_connected_controllers
    assert self._switches_manager.has_switch(switch)
    return self._switches_manager.get_connected_controllers(
      switch, self._controllers_manager)
