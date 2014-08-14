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
A simple tracker of connectivity policies.
"""

import logging
from collections import defaultdict
from collections import namedtuple


ConnectedHosts = namedtuple('ConnectedHosts',
                            ['src_host', 'src_interface', 'dst_host',
                            'dst_interface'])


class ConnectivityTracker(object):
  """
  Track connected and disconnect hosts based on external policies
  """
  def __init__(self, default_connected=True):
    self.connected_pairs = defaultdict(lambda: defaultdict(list))
    self.disconnected_pairs = defaultdict(lambda: defaultdict(list))
    self.policies = dict()
    self.default_connected = default_connected
    self.log = logging.getLogger(__name__ + '.ConnectivityTracker')

  def is_connected(self, src_host, dst_host):
    """
    Returns True is src_host and dst_host are connected by explicit or
    default policy.
    """
    # Check if explicitly connected by a policy
    if self.connected_pairs.get(src_host, {}).get(dst_host, None):
      return True
    # Check if explicitly disconnected by a policy
    elif self.disconnected_pairs.get(src_host, {}).get(dst_host, None):
      return False
    # Default connected state
    else:
      return self.default_connected

  def add_connected_hosts(self, src_host, src_interface, dst_host,
                          dst_interface, policy):
    """
    Add a policy connecting two hosts.
    """
    self.log.info("Adding %s<->%s to the set of connected hosts",
                  src_host, dst_host)
    self.connected_pairs[src_host][dst_host].append(
      (policy, src_interface, dst_interface))
    self.policies[policy] = ConnectedHosts(
      src_host=src_host, src_interface=src_interface, dst_host=dst_host,
      dst_interface=dst_interface)

  def add_disconnected_hosts(self, src_host, src_interface, dst_host,
                             dst_interface, policy):
    """
    Add a policy blocking connectivity between two hosts.
    """
    self.log.info("Adding %s<->%s to the set of connected hosts",
                  src_host, dst_host)
    self.disconnected_pairs[src_host][dst_host].append(
      (policy, src_interface, dst_interface))
    self.policies[policy] = ConnectedHosts(
      src_host=src_host, src_interface=src_interface, dst_host=dst_host,
      dst_interface=dst_interface)

  def remove_policy(self, policy):
    """
    Removes a policy.
    """
    assert policy in self.policies
    info = self.policies[policy]
    for tmp in self.connected_pairs[info.src_host][info.dst_host]:
      if tmp[0] == policy:
        self.connected_pairs[info.src_host][info.dst_host].remove(tmp)
    for tmp in self.disconnected_pairs[info.src_host][info.dst_host]:
      if tmp[0] == policy:
        self.disconnected_pairs[info.src_host][info.dst_host].remove(tmp)
    del self.policies[policy]

  def remove_connected_hosts(self, src_host, src_interface, dst_host,
                             dst_interface, remove_policies=True):
    """
    Removes host pairs from the list of connected hosts.
    If remove_policies is True all related policies will be removed as well.
    """
    self.log.info("Removing %s<->%s from the set of connected hosts",
                  src_host, dst_host)
    info = self.connected_pairs[src_host][dst_host]
    for tmp in info:
    # To deal with wildcarding interfaces
      tmp_src = src_interface if src_interface is None else tmp.src_interface
      tmp_dst = dst_interface if dst_interface is None else tmp.dst_interface
      if not (tmp_src == src_interface and tmp_dst == dst_interface):
        continue
      if remove_policies:
        policy = tmp[0]
        self.remove_policy(policy)
      self.connected_pairs[src_host][dst_host].remove(tmp)

  def remove_disconnected_hosts(self, src_host, src_interface, dst_host,
                             dst_interface, remove_policies=True):
    """
    Removes host pairs from the list of disconnected hosts.
    If remove_policies is True all related policies will be removed as well.
    """
    self.log.info("Removing %s<->%s from the set of disconnected hosts",
                  src_host, dst_host)
    info = self.disconnected_pairs[src_host][dst_host]
    for tmp in info:
      # To deal with wildcarding interfaces
      tmp_src = src_interface if src_interface is None else tmp.src_interface
      tmp_dst = dst_interface if dst_interface is None else tmp.dst_interface
      if not (tmp_src == src_interface and tmp_dst == dst_interface):
        continue
      if remove_policies:
        policy = tmp[0]
        self.remove_policy(policy)
      self.disconnected_pairs[src_host][dst_host].remove(tmp)
