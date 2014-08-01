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
Helper method to fill Topology objects.
"""

from sts.topology.hosts_manager import mac_addresses_generator
from sts.topology.hosts_manager import ip_addresses_generator
from sts.topology.hosts_manager import interface_names_generator


def create_mesh_topology(topology, num_switches=3,
                         mac_addresses_generator=mac_addresses_generator,
                         ip_addresses_generator=ip_addresses_generator,
                         interface_names_generator=interface_names_generator):
  # Every switch has a link to every other switch + 1 host,
  # for N*(N-1)+N = N^2 total ports
  ports_per_switch = (num_switches - 1) + 1
  # 1- Create switches
  switches = []
  for switch_id in range(1, num_switches + 1):
    sw = topology.create_switch(switch_id, ports_per_switch)
    switches.append(sw)
  # 2- Create hosts
  hosts = []
  mac_gen = mac_addresses_generator()
  ip_gen = ip_addresses_generator()
  for switch_id in range(1, num_switches + 1):
    name_gen = interface_names_generator()
    host = topology.create_host_with_interfaces(
      hid=switch_id, name="h%d" % switch_id, num_interfaces=1,
      mac_generator=mac_gen, ip_generator=ip_gen, interface_name_generator=name_gen)
    hosts.append(host)
  # 3- Create access links
  for index in range(len(hosts)):
    print "Creating access link:", hosts[index], hosts[index].interfaces[0].port_no, switches[index], switches[index].ports[1].port_no
    access_link = topology.create_access_link(
      hosts[index], hosts[index].interfaces[0], switches[index],
      switches[index].ports[1])
  # 4- Create network links
  for i, switch_i in enumerate(switches):
    for switch_j in switches[i + 1:]:
      src_port = topology.patch_panel.find_unused_port(switch_i)
      dst_port = topology.patch_panel.find_unused_port(switch_j)
      topology.create_network_link(switch_i, src_port, switch_j, dst_port, False)
      topology.create_network_link(switch_j, dst_port, switch_i, src_port, False)



'''
class MeshTopology(Topology):
  def __init__(self, num_switches=3, create_io_worker=None, netns_hosts=False,
               gui=False, ip_format_str="123.123.%d.%d"):
    """
    Populate the topology as a mesh of switches, connect the switches
    to the controllers

    Optional argument(s):
      - num_switches. The total number of switches to include in the mesh
      - netns_switches. Whether to create network namespace hosts instead of
        normal hosts.
      - ip_format_str: a format string for assigning IP addresses to hosts.
        Takes two digits to be interpolated, the switch dpid and the port
        number. For example, "10.%d.%d.255" will assign hosts the IP address
        10.DPID.PORT_NUMBER.255, where DPID is the dpid of their ingress
        switch, and PORT_NUMBER is the number of the switch's access link.
    """
    host_cls = NamespaceHost if netns_hosts == True else Host
    super(MeshTopology, self).__init__(create_io_worker=create_io_worker,
                                       gui=gui, host_cls=host_cls)

    # Every switch has a link to every other switch + 1 host,
    # for N*(N-1)+N = N^2 total ports
    ports_per_switch = (num_switches - 1) + 1

    # Initialize switches
    switches = [create_switch(switch_id, ports_per_switch)
                for switch_id in range(1, num_switches + 1)]
    for switch in switches:
      self.add_switch(switch)

    if netns_hosts:
      host_access_link_pairs = [create_netns_host(create_io_worker, switch)
                                 for switch in self.switches]
    else:
      host_access_link_pairs = [create_host(switch, ip_format_str=ip_format_str)
                                for switch in self.switches]
    access_link_list_list = []
    for host, access_link_list in host_access_link_pairs:
      access_link_list_list.append(access_link_list)
      self.add_host(host)

    # this is python's .flatten:
    access_links = list(itertools.chain.from_iterable(access_link_list_list))
    for access_link in access_links:
      self.add_link(access_link)

    # grab a fully meshed patch panel to wire up these guys
    self.patch_panel = MeshTopology.FullyMeshedLinks(self.switches, access_links)
    self.get_connected_port = self.patch_panel.get_other_side
    if self.gui is not None:
      self.gui.launch()

  class FullyMeshedLinks(STSPatchPanel):
    """
    A factory method (inner class) for creating a fully meshed network.
    Connects every pair of switches. Ports are in ascending order of
    the dpid of connected switch, while skipping the self-connections.
    I.e., for (dpid, portno):
        (0, 0) <-> (1,0)
        (2, 1) <-> (1,1)
    """
    def __init__(self, switches, access_links=[]):
      STSPatchPanel.__init__(self)
      for link in access_links:
        self.add_access_link(link)

      switch2unclaimed_ports = {switch: filter(lambda p: p not in
                                                         self.port2access_link,
                                               switch.ports.values())
                                for switch in switches}

      for i, switch_i in enumerate(switches):
        for switch_j in switches[i+1:]:
          switch_i_port = switch2unclaimed_ports[switch_i].pop()
          switch_j_port = switch2unclaimed_ports[switch_j].pop()
          link_i2j = Link(switch_i, switch_i_port, switch_j, switch_j_port)
          link_j2i = link_i2j.reversed_link()
          self.add_link(link_i2j)
          self.add_link(link_j2i)


class FatTree (Topology):
  """Construct a FatTree topology with a given number of pods"""
  def __init__(self, num_pods=4, create_io_worker=None, gui=False,
               use_portland_addressing=True, ip_format_str="123.123..%d.%d",
               netns_hosts=True):
    """
    If not use_portland_addressing, use a format string for assigning
    IP addresses to hosts. Takes two digits to be interpolated, the switch
    dpid and the port number.

    For example, "10.%d.%d.255" will assign hosts the IP address
    10.DPID.PORT_NUMBER.255, where DPID is the dpid of their ingress
    switch, and PORT_NUMBER is the number of the switch's access link.
    """
    host_cls = NamespaceHost if netns_hosts == True else Host
    super(FatTree, self).__init__(create_io_worker=create_io_worker,
                                  gui=gui, host_cls=host_cls)
    if num_pods < 2:
      raise ValueError("Can't handle Fat Trees with less than 2 pods")
    Topology.__init__(self, create_io_worker=create_io_worker, gui=gui)
    self.cores = []
    self.aggs = []
    self.edges = []
    self.use_portland_addressing = use_portland_addressing
    self.ip_format_str = ip_format_str

    self.construct_tree(num_pods)

    if self.gui is not None:
      self.gui.launch()

  def construct_tree(self, num_pods):
    """
    According to  "A Scalable, Commodity Data Center Network Architecture",
    k = number of ports per switch = number of pods
    number core switches =  (k/2)^2
    number of edge switches per pod = k / 2
    number of agg switches per pod = k / 2
    number of hosts attached to each edge switch = k / 2
    number of hosts per pod = (k/2)^2
    total number of hosts  = k^3 / 4
    """
    self.log.debug("Constructing fat tree with %d pods" % num_pods)

    # self == store these numbers for later
    k = self.k = self.ports_per_switch = self.num_pods = num_pods
    self.hosts_per_pod = self.total_core = (k/2)**2
    self.edge_per_pod = self.agg_per_pod = self.hosts_per_edge = k / 2
    self.total_hosts = self.hosts_per_pod * num_pods

    access_links = set()
    network_links = set()

    current_pod_id = -1
    # zero is not a valid dpid -- (first dpid is 0+1)
    current_dpid = 0
    # We construct it from bottom up, starting at host <-> edge
    for i in range(self.total_hosts):
      if not i % 1000:
        log.debug("Host %d / %d" % (i, self.total_hosts))

      if (i % self.hosts_per_pod) == 0:
        current_pod_id += 1

      if (i % self.hosts_per_edge) == 0:
        current_dpid += 1
        edge_switch = create_switch(current_dpid, self.ports_per_switch)
        edge_switch.pod_id = current_pod_id
        self.edges.append(edge_switch)

      edge = self.edges[-1]
      # edge ports 1 through (k/2) are dedicated to hosts, and (k/2)+1 through
      # k are for agg
      edge_port_no = (i % self.hosts_per_edge) + 1
      # We give it a portland pseudo mac, just for giggles
      # Slightly modified from portland (no vmid, assume 8 bit pod id):
      # 00:00:00:<pod>:<position>:<port>
      # position and pod are 0-indexed, port is 1-indexed
      position = (len(self.edges)-1) % self.edge_per_pod
      edge.position = position
      portland_mac = EthAddr("00:00:00:%02x:%02x:%02x" %
                             (current_pod_id, position, edge_port_no))
      if self.use_portland_addressing:
        portland_ip_addr = IPAddr("123.%d.%d.%d" %
                         (current_pod_id, position, edge_port_no))
        (host, host_access_links) = create_host(edge, portland_mac, portland_ip_addr,
                                                lambda switch: switch.ports[edge_port_no])
      else:
        (host, host_access_links) = create_host(edge, mac_or_macs=portland_mac, ip_format_str=self.ip_format_str,
                                                get_switch_port=lambda switch: switch.ports[edge_port_no])
      host.pod_id = current_pod_id
      self.add_host(host)
      access_links = access_links.union(set(host_access_links))

    # Now edge <-> agg
    for pod_id in range(num_pods):
      if not pod_id % 10:
        log.debug("edge<->agg for pod %d / %d" % (pod_id, num_pods))
      current_aggs = []
      for _ in  range(self.agg_per_pod):
        current_dpid += 1
        agg = create_switch(current_dpid, self.ports_per_switch,
                            can_connect_to_endhosts=False)
        agg.pod_id = pod_id
        current_aggs.append(agg)

      current_edges = self.edges[pod_id * self.edge_per_pod : \
                                (pod_id * self.edge_per_pod) + self.edge_per_pod]
      # edge ports (k/2)+1 through k connect to aggs
      # agg port k+1 connects to edge switch k in the pod
      current_agg_port_no = 1
      for edge in current_edges:
        current_edge_port_no = (k/2)+1
        for agg in current_aggs:
          network_links.add(Link(edge, edge.ports[current_edge_port_no],
                                      agg, agg.ports[current_agg_port_no]))
          network_links.add(Link(agg, agg.ports[current_agg_port_no],
                                      edge, edge.ports[current_edge_port_no]))
          current_edge_port_no += 1
        current_agg_port_no += 1

      self.aggs += current_aggs

    # Finally, agg <-> core
    for i in range(self.total_core):
      if not i % 100:
        log.debug("agg<->core %d / %d" % (i, self.total_core))
      current_dpid += 1
      self.cores.append(create_switch(current_dpid, self.ports_per_switch,
                                      can_connect_to_endhosts=False))

    core_cycler = itertools.cycle(self.cores)
    for agg in self.aggs:
      # agg ports (k/2)+1 through k connect to cores
      # core port i+1 connects to pod i
      for agg_port_no in range(k/2+1, k+1):
        core = core_cycler.next()
        core_port_no = agg.pod_id + 1
        network_links.add(Link(agg, agg.ports[agg_port_no], core,
                                    core.ports[core_port_no]))
        network_links.add(Link(core, core.ports[core_port_no], agg,
                                    agg.ports[agg_port_no]))

    switches = self.cores + self.aggs + self.edges
    #self._populate_dpid2switch(switches)
    for switch in switches:
      if not self.has_switch(switch):
        self.add_switch(switch)
    self.wire_tree(access_links, network_links)
    self._sanity_check_tree(access_links, network_links)
    self.log.debug("Fat tree construction: done (%d cores, %d aggs,"
                   "%d edges, %d hosts)" %
                   (len(self.cores), len(self.aggs), len(self.edges),
                    len(self.hosts)))

  def wire_tree(self, access_links, network_links):
    # Auxiliary data to make get_connected_port efficient
    for access_link in access_links:
      self.patch_panel.add_access_link(access_link)
    for link in network_links:
      self.patch_panel.add_link(link)
    self.get_connected_port = self.patch_panel.get_other_side

  def _sanity_check_tree(self, access_links, network_links):
    # TODO(cs): this should be in a unit test, not here
    if len(access_links) != self.total_hosts:
      raise RuntimeError("incorrect # of access links (%d, s/b %d)" % \
                          (len(access_links),len(self.total_hosts)))

    # k = number of ports per switch = number of pods
    # number core switches =  (k/2)^2
    # number of edge switches per pod = k / 2
    # number of agg switches per pod = k / 2
    total_switches = self.total_core + ((self.edge_per_pod + self.agg_per_pod) * self.k)
    # uni-directional links (on in both directions):
    total_network_links = (total_switches * self.k) - self.total_hosts
    if len(network_links) != total_network_links:
      raise RuntimeError("incorrect # of internal links (%d, s/b %d)" % \
                          (len(network_links),total_network_links))

  def install_default_routes(self):
    """
    Install static routes as proposed in Section 3 of
    "A Scalable, Commodity Data Center Network Architecture".
    This is really a strawman routing scheme. PORTLAND, et. al. are much better
    """
    pass

  def install_portland_routes(self):
    """
    We use a modified version of PORTLAND. We make two changes: OpenFlow 1.0
    doesn't support prefix matching on MAC addresses, so we use IP addresses
    instead. (same # of flow entries, and we don't model flooding anyway)
    Second, we ignore vmid and assume 8 bit pod ids. So, IPs are of the form:
    123.pod.position.port
    """
    k = self.k

    for core in self.cores:
      # When forwarding a packet, the core switch simply inspects the bits
      # corresponding to the pod number in the PMAC destination address to
      # determine the appropriate output port.
      for port_no in core.ports.keys():
        # port_no i+1 corresponds to pod i
        match = ofp_match(nw_dst="123.%d.0.0/16" % (port_no-1))
        flow_mod = ofp_flow_mod(match=match, actions=[ofp_action_output(port=port_no)])
        core._receive_flow_mod(flow_mod)

    for agg in self.aggs:
      # Aggregation switches must determine whether a packet is destined for a host
      # in the same or different pod by inspecting the PMAC. If in the same pod,
      # the packet must be forwarded to an output port corresponding to the position
      # entry in the PMAC. If in a different pod, the packet may be forwarded along
      # any of the aggregation switch's links to the core layer in the fault-free case.
      pod_id = agg.pod_id
      for port_no in range(1, k/2+1):
        # ports 1 through k/2 are connected to edge switches 0 through k/2-1
        position = port_no - 1
        match = ofp_match(nw_dst="123.%d.%d.0/24" % (pod_id, position))
        flow_mod = ofp_flow_mod(match=match, actions=[ofp_action_output(port=port_no)])
        agg._receive_flow_mod(flow_mod)

      # We model load balancing to uplinks as a single flow entry -- h/w supports
      # ecmp efficiently while only requiring a single TCAM entry
      match = ofp_match(nw_dst="123.0.0.0/8")
      # Forward to the right-most uplink
      flow_mod = ofp_flow_mod(match=match, actions=[ofp_action_output(port=k)])
      agg._receive_flow_mod(flow_mod)

    for edge in self.edges:
      # if a connected host, deliver to host. Else, ECMP over uplinks
      pod_id = edge.pod_id
      position = edge.position
      for port_no in range(1,k/2+1):
        # Route down to the host
        match = ofp_match(nw_dst="123.%d.%d.%d" % (pod_id, position, port_no))
        flow_mod = ofp_flow_mod(match=match, actions=[ofp_action_output(port=port_no)])
        edge._receive_flow_mod(flow_mod)

      # We model load balancing to uplinks as a single flow entry --
      # h/w supports ecmp efficiently while only requiring a single TCAM entry
      match = ofp_match(nw_dst="123.0.0.0/8")
      # Forward to the right-most uplink
      flow_mod = ofp_flow_mod(match=match, actions=[ofp_action_output(port=k)])
      edge._receive_flow_mod(flow_mod)
'''
