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


import socket
import time
import unittest

from pox.lib.util import connect_socket_with_backoff

from sts.entities.sts_entities import DeferredOFConnection
from sts.openflow_buffer import OpenFlowBuffer
from sts.util.io_master import IOMaster
from sts.util.deferred_io import DeferredIOWorker

from sts.entities.controllers import ControllerConfig
from sts.entities.controllers import ControllerState
from sts.entities.controllers import POXController

from sts.topology.sts_topology import MeshTopology
from sts.topology.connectivity_tracker import ConnectivityTracker

from sts.control_flow.fuzzer_new import IntentsGenerator
from sts.control_flow.fuzzer_new import FuzzerParams
from sts.control_flow.fuzzer_new import Fuzzer

from sts.replay_event import CheckInvariants
from sts.replay_event import NOPInput
from sts.invariant_checker import ViolationTracker


from sts.control_flow.events_exec import EventsExec


class Simulation(object):
  """Simple Mock to carry simulation state"""
  def __init__(self, topology):
    self.topology = topology
    self.violation_tracker = ViolationTracker()


class PlayEventsTest(unittest.TestCase):
  def initialize_io_loop(self):
    io_master = IOMaster()
    io_master.monkey_time_sleep()
    self.io_master = io_master
    return io_master

  def create_connection(self, controller_info, switch,
                        max_backoff_seconds=1024):
    """Connect switches to controllers. May raise a TimeoutError"""
    socket_ctor = socket.socket
    sock = connect_socket_with_backoff(controller_info.config.address,
                                       controller_info.config.port,
                                       max_backoff_seconds=max_backoff_seconds,
                                       socket_ctor=socket_ctor)
    # Set non-blocking
    sock.setblocking(0)
    io_worker = DeferredIOWorker(self.io_master.create_worker_for_socket(sock))
    connection = DeferredOFConnection(io_worker, controller_info.cid,
                                      switch.dpid, self.openflow_buffer)
    return connection

  def setUp(self):
    self.io_master = self.initialize_io_loop()
    self.openflow_buffer = OpenFlowBuffer()
    self.openflow_buffer.set_pass_through()
    # Just make sure that controllers are killed after each test case
    self._controllers = []

  def tearDown(self):
    for controller in self._controllers:
      controller.kill()

  def get_controller_config(self, address='127.0.0.1', port=6633, label=None):
    start_cmd = ("./pox.py --verbose --no-cli forwarding.l2_multi "
                 "openflow.of_01 --address=__address__ --port=__port__")
    '''
    start_cmd = ("./pox.py --verbose --no-cli openflow.discovery sts.syncproto.pox_syncer --blocking=False "
                " forwarding.l2_multi "
                "  "
                " openflow.of_01 --address=__address__ --port=__port__")
    '''
    kill_cmd = ""
    cwd = "pox"
    if label is None:
      label = str(port)
    config = ControllerConfig(start_cmd=start_cmd, kill_cmd=kill_cmd, cwd=cwd,
                              address=address, port=port, cid=port, label=label)
    return config

  def get_controller(self, address='127.0.0.1', port=6633, label=None):
    config = self.get_controller_config(address, port, label)
    from sts.control_flow.base import RecordingSyncCallback
    from sts.syncproto.sts_syncer import STSSyncConnectionManager
    self.sync_callback = RecordingSyncCallback(None, record_deterministic_values=False)
    sync_connection_manager = STSSyncConnectionManager(self.io_master, self.sync_callback)
    ctrl = POXController(controller_config=config, sync_connection_manager=sync_connection_manager)
    self._controllers.append(ctrl)
    return ctrl

  def get_onos_controller(self, label):
    import mock
    from sts.entities.teston_entities import TestONONOSConfig
    from sts.entities.teston_entities import TestONONOSController
    teston_mock = mock.Mock(name="teston_%s" % label)
    teston_mock.status.return_value = 1
    teston_mock.add_intent.return_value = 1
    config = TestONONOSConfig(label=label, address='127.0.0.1', port=6633,
                              intent_ip='127.0.0.1', intent_port=8080,
                              intent_url='/wm/intents')
    return TestONONOSController(config, teston_onos=teston_mock)

  def test_sever_network_links(self):
    """Event: LinkFailure"""
    # Arrange
    topology = MeshTopology(None, 2)
    simulation = Simulation(topology)
    params = FuzzerParams()
    fuzzer = Fuzzer(topology, params)
    params.link_failure_rate = 1
    events = fuzzer.sever_network_links()
    # Act
    events[0].proceed(simulation)
    # Assert
    self.assertEquals(len(topology.patch_panel.cut_network_links), 1)

  def test_repair_network_links(self):
    """Event: LinkRecovery"""
    # Arrange
    topology = MeshTopology(None, 2)
    simulation = Simulation(topology)
    params = FuzzerParams()
    fuzzer = Fuzzer(topology, params)
    for link in topology.patch_panel.live_network_links:
      topology.patch_panel.sever_network_link(link)
    params.link_recovery_rate = 1
    events = fuzzer.repair_network_links()
    # Act
    events[0].proceed(simulation)
    # Assert
    self.assertEquals(len(topology.patch_panel.live_network_links), 1)

  def test_crash_switches(self):
    """Event: SwitchFailure"""
    # Arrange
    topology = MeshTopology(None, 2)
    simulation = Simulation(topology)
    params = FuzzerParams()
    fuzzer = Fuzzer(topology, params)
    params.switch_failure_rate = 1
    events = fuzzer.crash_switches()
    # Act
    events[0].proceed(simulation)
    # Assert
    self.assertEquals(len(topology.switches_manager.failed_switches), 1)
    self.assertEquals(len(topology.switches_manager.live_switches), 1)

  def test_recover_switches(self):
    """Event: SwitchRecovery"""
    # Arrange
    topology = MeshTopology(self.create_connection, 2)
    simulation = Simulation(topology)
    params = FuzzerParams()
    fuzzer = Fuzzer(topology, params)
    c1 = self.get_controller(port=6633)
    c1.start()
    c2 = self.get_controller(port=6644)
    c2.start()
    topology.add_controller(c1)
    topology.add_controller(c2)
    s1 = topology.switches_manager.get_switch('s1')
    s2 = topology.switches_manager.get_switch('s2')
    topology.switches_manager.connect_to_controllers(s1, [c1, c2])
    topology.switches_manager.connect_to_controllers(s2, [c2])
    topology.switches_manager.crash_switch(s1)
    c1.kill()
    topology.switches_manager.crash_switch(s2)
    params.switch_recovery_rate = 1
    events = fuzzer.recover_switches()
    # Act
    events[0].proceed(simulation)
    # Assert

  def test_crash_controllers(self):
    """Event: ControllerFailure"""
    # Arrange
    topology = MeshTopology(self.create_connection, 2)
    simulation = Simulation(topology)
    c1 = self.get_controller(port=6633)
    c1.start()
    c2 = self.get_controller(port=6644)
    c2.start()
    topology.add_controller(c1)
    topology.add_controller(c2)
    params = FuzzerParams()
    fuzzer = Fuzzer(topology, params)
    params.controller_crash_rate = 1
    events = fuzzer.crash_controllers()
    # Act
    events[0].proceed(simulation)
    # Assert
    self.assertEquals(len(topology.controllers_manager.live_controllers), 1)
    self.assertEquals(len(topology.controllers_manager.failed_controllers), 1)

  def test_recover_controllers(self):
    """Event: ControllerRecovery"""
    # Arrange
    topology = MeshTopology(self.create_connection, 2)
    simulation = Simulation(topology)
    c1 = self.get_controller(port=6633)
    c1.start()
    c2 = self.get_controller(port=6644)
    c2.start()
    topology.add_controller(c1)
    topology.add_controller(c2)
    params = FuzzerParams()
    fuzzer = Fuzzer(topology, params)
    topology.controllers_manager.crash_controller(c1)
    topology.controllers_manager.crash_controller(c2)
    params.controller_recovery_rate = 1
    events = fuzzer.recover_controllers()
    # Act
    events[0].proceed(simulation)
    # Assert
    self.assertEquals(len(topology.controllers_manager.live_controllers), 1)
    self.assertEquals(len(topology.controllers_manager.failed_controllers), 1)

  def test_fuzz_traffic(self):
    # Arrange
    topology = MeshTopology(self.create_connection, 1)
    from sts.topology.dp_buffer import DataPathBuffer
    topology._dp_buffer = DataPathBuffer()
    simulation = Simulation(topology)
    c1 = self.get_controller(port=6633)
    c1.start()
    topology.add_controller(c1)
    for switch in topology.switches_manager.switches:
      topology.switches_manager.connect_to_controllers(switch, c1)
      time.sleep(10)
    time.sleep(10)
    params = FuzzerParams()
    fuzzer = Fuzzer(topology, params)
    params.traffic_generation_rate = 1
    events = fuzzer.fuzz_traffic()
    # Act
    events[0].proceed(simulation)
    time.sleep(10)
    time.sleep(10)

  def test_invariant_check_liveness(self):
    """Event: CheckInvariants"""
    # Arrange
    topology = MeshTopology(self.create_connection, 2)
    simulation = Simulation(topology)
    c1 = self.get_controller(port=6633, label='c1')
    c1.start()
    c2 = self.get_controller(port=6644, label='c2')
    c2.start()
    c3 = self.get_controller(port=6655, label='c3')
    c3.start()
    topology.add_controller(c1)
    topology.add_controller(c2)
    topology.add_controller(c3)
    topology.controllers_manager.crash_controller(c2)
    c2.start()
    c3.kill()
    # Act
    event = CheckInvariants(logical_round=10, invariant_check_name='InvariantChecker.check_liveness')
    event.proceed(simulation)
    # Assert
    expected = ['Live Controller (supposed to be down): c2',
                'Dead controllers (supposed to be up): c3']
    self.assertItemsEqual(expected, simulation.violation_tracker.violations)


  def test_invariant_check_loops(self):
    """Event: CheckInvariants"""
    # Arrange
    topology = MeshTopology(self.create_connection, 2)
    simulation = Simulation(topology)
    c1 = self.get_controller(port=6633)
    c1.start()
    topology.add_controller(c1)
    for switch in topology.switches_manager.switches:
      topology.switches_manager.connect_to_controllers(switch, c1)
    # Act
    event = CheckInvariants(logical_round=10, invariant_check_name='InvariantChecker.check_loops')
    event.proceed(simulation)
    # Assert

  def test_events_exec(self):
    # Arrange
    topology = MeshTopology(self.create_connection, 2)
    simulation = Simulation(topology)
    c1 = self.get_controller(port=6633)
    c1.start()
    topology.add_controller(c1)
    for switch in topology.switches_manager.switches:
      topology.switches_manager.connect_to_controllers(switch, c1)

    params = FuzzerParams()
    fuzzer = Fuzzer(topology, params)
    params.link_failure_rate = 0
    params.link_recovery_rate = 0
    params.controller_crash_rate = 0
    params.switch_failure_rate = 0
    # Act
    events_exec = EventsExec(simulation, fuzzer, steps=20, delay=1,
                             check_interval=4,
                             invariant_check_name="InvariantChecker.check_liveness")
    events_exec.simulate()
    # Assert
    for c in topology.controllers_manager.live_controllers:
      c.kill()

  def test_nop_input(self):
    """Event: NOPInput"""
    # Arrange
    topology = MeshTopology(self.create_connection, 2)
    simulation = Simulation(topology)
    event = NOPInput()
    # Act
    event.proceed(simulation)
    # Assert
    pass

  def test_add_intent(self):
    # Arrange
    topology = MeshTopology(self.create_connection, 2,
                            connectivity_tracker=ConnectivityTracker(False))
    topology.controllers_manager.capabilities._can_add_intent = True
    topology.controllers_manager.capabilities._can_remove_intent = True
    simulation = Simulation(topology)
    c1 = self.get_onos_controller('ONOS1')
    c1.state = ControllerState.ALIVE
    topology.add_controller(c1)
    params = FuzzerParams()
    params.policy_change_rate = 1
    intents_gen = IntentsGenerator(add_intent_rate=1, remove_intent_rate=0,
                                   ping_rate=0)
    fuzzer = Fuzzer(topology, params, policy_generator=intents_gen)
    # Act
    events = fuzzer.next_events(1)
    for event in events:
      event.proceed(simulation)
    # Assert
    h1 = topology.hosts_manager.get_host('h1')
    h2 = topology.hosts_manager.get_host('h2')
    self.assertTrue(topology.connectivity_tracker.is_connected(h1, h2))
    self.assertTrue(topology.connectivity_tracker.is_connected(h2, h1))

  def test_remove_intent(self):
    # Arrange
    topology = MeshTopology(self.create_connection, 2,
                            connectivity_tracker=ConnectivityTracker(False))
    topology.controllers_manager.capabilities._can_add_intent = True
    topology.controllers_manager.capabilities._can_remove_intent = True
    simulation = Simulation(topology)
    c1 = self.get_onos_controller('ONOS1')
    c1.state = ControllerState.ALIVE
    topology.add_controller(c1)
    params = FuzzerParams.get_all_zero()
    params.policy_change_rate = 1
    intents_gen = IntentsGenerator(add_intent_rate=1, remove_intent_rate=1,
                                   ping_rate=0)
    fuzzer = Fuzzer(topology, params, policy_generator=intents_gen)
    # First add the intents
    events = fuzzer.next_events(1)
    for event in events:
      event.proceed(simulation)
    intents_gen.add_intent_rate = 0
    # Act
    events = fuzzer.next_events(1)
    for event in events:
      event.proceed(simulation)
    # Assert
    h1 = topology.hosts_manager.get_host('h1')
    h2 = topology.hosts_manager.get_host('h2')
    self.assertFalse(topology.connectivity_tracker.is_connected(h1, h2))
    self.assertFalse(topology.connectivity_tracker.is_connected(h2, h1))
