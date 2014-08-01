# Copyright 2011-2013 Colin Scott
# Copyright 2011-2013 Andreas Wundsam
# Copyright 2012-2013 Sam Whitlock
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


from sts.traffic_generator import TrafficGenerator

from sts.replay_event import ControllerFailure
from sts.replay_event import ControllerRecovery
from sts.replay_event import LinkFailure
from sts.replay_event import LinkRecovery
from sts.replay_event import SwitchFailure
from sts.replay_event import SwitchRecovery
from sts.replay_event import TrafficInjection
from sts.replay_event import AddIntent
from sts.replay_event import RemoveIntent
from sts.replay_event import PingEvent

from sts.util.capability import check_capability

import random
import sys
from sts.invariant_checker import ViolationTracker


class Simulation(object):
  def __init__(self, topology):
    self.topology = topology
    self.violation_tracker = ViolationTracker()


class FuzzerParams(object):
  def __init__(self):
    self.link_failure_rate = 0.1
    self.link_recovery_rate = 0.1
    self.switch_failure_rate = 0.1
    self.switch_recovery_rate = 0.1
    self.controller_crash_rate = 0.1
    self.controller_recovery_rate = 0.1
    self.traffic_generation_rate = 0.1
    self.dataplane_drop_rate = 0
    self.policy_change_rate = 0


class EventsGenerator(object):
  def __init__(self, topology):
    self.topology = topology

  def generate_events(self):
    raise NotImplementedError()


from itertools import count


class IntentsGenerator():
  _intent_id = count(1)
  def __init__(self, add_intent_rate, remove_intent_rate, ping_rate, bidir=True):
    self.add_intent_rate = add_intent_rate
    self.remove_intent_rate = remove_intent_rate
    self.ping_rate = ping_rate
    self.bidir = bidir
    self.intents = {}

  def has_intent(self, intent):
    intent_id = intent.get('intent_id', None)
    if intent_id in self.intents:
      return True
    for local_intent in self.intents.itervalues():
      intent['intent_id'] = local_intent['intent_id']
      if intent == local_intent:
        # Restore intent ID
        if intent_id is not None:
          intent['intent_id'] = intent_id
        return True
    return False

  def _generate_intent(self, fuzzer):
    intent_id = IntentsGenerator._intent_id.next()
    src_host = fuzzer.random.choice(
      list(fuzzer.topology.hosts_manager.live_hosts))
    dst_host = fuzzer.random.choice(
      list(fuzzer.topology.hosts_manager.live_hosts - set([src_host])))
    src_iface = fuzzer.random.choice(src_host.interfaces)
    dst_iface = fuzzer.random.choice(dst_host.interfaces)
    src_switch, src_port = fuzzer.topology.patch_panel.get_other_side(src_host,
                                                                      src_iface)
    dst_switch, dst_port = fuzzer.topology.patch_panel.get_other_side(dst_host,
                                                                      dst_iface)
    controllers = [c for c in
                   fuzzer.topology.controllers_manager.live_controllers
                   if not c.config.intent_ip is None]
    if not controllers:
      # no controller is alive
      return None
    controller = fuzzer.random.choice(controllers)
    intent = {}
    intent['cid'] = controller.cid
    intent['intent_id'] = str(intent_id)
    intent['src_dpid'] = str(src_switch.dpid)
    intent['dst_dpid'] = str(dst_switch.dpid)
    intent['src_port'] = src_port.port_no
    intent['dst_port'] = dst_port.port_no
    intent['src_mac'] = str(src_iface.hw_addr)
    intent['dst_mac'] = str(dst_iface.hw_addr)
    # Fixed values from now
    intent['intent_type'] = 'SHORTEST_PATH'
    intent['static_path'] = False
    intent['intent_ip'] = controller.config.intent_ip
    intent['intent_port'] = controller.config.intent_port
    intent['intent_url'] = controller.config.intent_url
    self.intents[intent['intent_id']] = intent
    return intent

  def generate_remove_intent(self, fuzzer):
    assert check_capability(fuzzer.topology.controllers_manager,
                            'can_remove_intent')
    events = []
    for intent_id, intent in self.intents.iteritems():
      if fuzzer.random.random() < self.remove_intent_rate:
        event = RemoveIntent(cid=intent['cid'], intent_id=intent['intent_id'],
                             intent_ip=intent['intent_ip'],
                             intent_port=intent['intent_port'],
                             intent_url=intent['intent_url'])
        events.append(event)
    return events

  def generate_add_intent(self, fuzzer):
    assert check_capability(fuzzer.topology.controllers_manager,
                            'can_add_intent')
    events = []
    if fuzzer.random.random() < self.add_intent_rate:
      intent = self._generate_intent(fuzzer)
      if intent is None:
        return events
      event = AddIntent(**intent)
      events.append(event)
      if self.bidir:
        reverse_intent = intent.copy()
        reverse_intent['intent_id'] = IntentsGenerator._intent_id.next()
        reverse_intent['dst_dpid'] = intent['src_dpid']
        reverse_intent['src_dpid'] = intent['dst_dpid']
        reverse_intent['dst_port'] = intent['src_port']
        reverse_intent['src_port'] = intent['dst_port']
        reverse_intent['dst_mac'] = intent['src_mac']
        reverse_intent['src_mac'] = intent['dst_mac']
        events.append(AddIntent(**reverse_intent))
    return events

  def fuzz_ping(self, fuzzer):
    events = []
    for _, intent in self.intents.iteritems():
      src_host = [h for h in fuzzer.topology.hosts_manager.live_hosts
                  if str(h.interfaces[0].hw_addr) == intent['src_mac']][0]
      dst_host = [h for h in fuzzer.topology.hosts_manager.live_hosts
                  if str(h.interfaces[0].hw_addr) == intent['dst_mac']][0]
      if fuzzer.random.random() < self.ping_rate:
        events.append(PingEvent(src_host_id=src_host.name,
                                dst_host_id=dst_host.name))
    return events

  def generate_events(self, fuzzer):
    events = []
    events.extend(self.fuzz_ping(fuzzer))
    events.extend(self.generate_remove_intent(fuzzer))
    events.extend(self.generate_add_intent(fuzzer))
    return events


class Fuzzer(object):
  def __init__(self, topology, params, random_seed=None, initialization_rounds=0,
               policy_generator=None):
    """
    Args:
      - topology: sts.topology.base.Topology instance to fuzz on.
      - params: FuzzerParams instance
      - random_seed: optionally set the seed of the random number generator
      - initialization_rounds: if non-zero, will wait the specified rounds to
                              let the controller discover the topology before
                              injecting inputs.
    """
    if random_seed is None:
      random_seed = random.randint(0, sys.maxint)

    self.random_seed = random_seed
    self.random = random.Random(random_seed)

    self.topology = topology
    self.traffic_generator = TrafficGenerator(self.random)
    self.traffic_generator.set_topology(self.topology)
    self.params = params
    self.logical_time = 0
    self.initialization_rounds = initialization_rounds
    self.policy_generator = policy_generator

  def sever_network_links(self):
    """
    Returns list of LinkFailure events.
    """
    if self.params.link_failure_rate > 0:
      assert self.topology.patch_panel.capabilities.can_sever_network_link
    events = []
    for link in self.topology.patch_panel.live_network_links:
      if self.random.random() < self.params.link_failure_rate:
        if hasattr(link, 'node1'):
          event = LinkFailure(link.node1.dpid, link.port1.port_no,
                              link.node2.dpid, link.port2.port_no)
        else:
          event = LinkFailure(link.start_node.dpid, link.start_port.port_no,
                              link.end_node.dpid, link.end_port.port_no)
        events.append(event)
    return events

  def repair_network_links(self):
    """
    Returns set of links to be failed.
    """
    if self.params.link_recovery_rate > 0:
      assert self.topology.patch_panel.capabilities.can_repair_network_link
    events = []
    for link in self.topology.patch_panel.cut_network_links:
      if self.random.random() < self.params.link_recovery_rate:
        if hasattr(link, 'node1'):
          event = LinkRecovery(link.node1.dpid, link.port1.port_no,
                               link.node2.dpid, link.port2.port_no)
        else:
          event = LinkRecovery(link.start_node.dpid, link.start_port.port_no,
                               link.end_node.dpid, link.end_port.port_no)
        events.append(event)
    return events

  def crash_switches(self):
    if self.params.switch_failure_rate > 0:
      assert self.topology.switches_manager.capabilities.can_crash_switch
    events = []
    for software_switch in self.topology.switches_manager.live_switches:
      if self.random.random() < self.params.switch_failure_rate:
        events.append(SwitchFailure(software_switch.dpid))
    return events

  def recover_switches(self):
    if self.params.switch_recovery_rate > 0:
      assert self.topology.switches_manager.capabilities.can_recover_switch
    events = []
    for software_switch in self.topology.switches_manager.failed_switches:
      if self.random.random() < self.params.switch_recovery_rate:
        events.append(SwitchRecovery(software_switch.dpid))
    return events

  def crash_controllers(self):
    if self.params.controller_crash_rate > 0:
      assert self.topology.controllers_manager.capabilities.can_crash_controller
    events = []
    for controller in self.topology.controllers_manager.live_controllers:
      if self.random.random() < self.params.controller_crash_rate:
        events.append(ControllerFailure(controller.cid))
    return events

  def recover_controllers(self):
    if self.params.controller_recovery_rate > 0:
      assert self.topology.controllers_manager.capabilities.can_recover_controller
    events = []
    for controller in self.topology.controllers_manager.failed_controllers:
      if self.random.random() < self.params.controller_recovery_rate:
        events.append(ControllerRecovery(controller.cid))
    return events


  def fuzz_traffic(self):
    events = []
    for host in self.topology.hosts_manager.live_hosts:
      if self.random.random() < self.params.traffic_generation_rate:
        if len(host.interfaces) > 0:
          traffic_type = "icmp_ping"
          (dp_event, send) = self.traffic_generator.generate(traffic_type, host, send_to_self=True)
          events.append(TrafficInjection(dp_event=dp_event))
    return events

  def next_events(self, logical_time):
    events = []
    self.logical_time = logical_time
    if self.logical_time < self.initialization_rounds:
      return []
    #events.extend(self.check_dataplane())
    events.extend(self.crash_switches())
    events.extend(self.recover_switches())
    events.extend(self.sever_network_links())
    events.extend(self.repair_network_links())
    if self.params.policy_change_rate > 0:
      events.extend(self.policy_generator.generate_events(self))
    #events.extend(self.fuzz_traffic())
    #events.extend(self.fuzz_ping())
    events.extend(self.crash_controllers())
    events.extend(self.recover_controllers())
    return events
    """
    #self.check_dataplane()
    self.check_tcp_connections()
    self.check_pending_messages()
    self.check_pending_commands()
    #self.check_switch_crashes()
    #self.check_link_failures()
    #self.fuzz_traffic()
    #self.check_controllers()
    self.check_migrations()
    self.check_intracontroller_blocks()
    """
