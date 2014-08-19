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


import json
import mock
import unittest

from pox.lib.addresses import EthAddr
from pox.lib.util import TimeoutError

import sts.replay_event
from sts.replay_event import AddIntent
from sts.replay_event import RemoveIntent
from sts.replay_event import CheckInvariants
from sts.replay_event import ControllerFailure
from sts.replay_event import ControllerRecovery
from sts.replay_event import LinkFailure
from sts.replay_event import LinkRecovery
from sts.replay_event import SwitchFailure
from sts.replay_event import SwitchRecovery
from sts.replay_event import NOPInput
from sts.replay_event import InvariantViolation


class ConnectToControllersTest(unittest.TestCase):

  def test_proceed(self):
    pass


class CheckInvariantsTest(unittest.TestCase):
  def test_proceed(self):
    # Arrange
    name = 'mock_invariant'
    check = mock.Mock(name='InvarCheck')
    check.return_value = []
    sts.replay_event.name_to_invariant_check = {name: check}
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    simulation = mock.Mock(name='Simulation')
    simulation = mock.Mock(name='Simulation')
    simulation.fail_to_interactive = False
    simulation.fail_to_interactive_on_persistent_violations = False
    simulation.violation_tracker.persistent_violations = []
    # Act
    event = CheckInvariants(invariant_check_name=name, label=label,
                            logical_round=logical_round, event_time=event_time)
    ret_val = event.proceed(simulation)
    # Assert
    self.assertTrue(ret_val)

  def test_to_json(self):
    # Arrange
    name = 'mock_invariant'
    check = mock.Mock(name='InvarCheck')
    check.return_value = []
    sts.replay_event.name_to_invariant_check = {name: check}
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    expected = dict(invariant_name=name, invariant_check=None,
                    invariant_check_name=name,
                    legacy_invariant_check=False,
                    label=label, event_time=event_time,
                    logical_round=logical_round, dependent_labels=[],
                    prunable=True, timed_out=False,
                    fingerprint="N/A")
    expected['class'] = "CheckInvariants"
    # Act
    event = CheckInvariants(invariant_check_name=name, label=label,
                            logical_round=logical_round, event_time=event_time)
    json_dump = event.to_json()
    # Assert
    self.assertEquals(expected, json.loads(json_dump))

  def test_from_json(self):
    # Arrange
    name = 'mock_invariant'
    check = mock.Mock(name='InvarCheck')
    check.return_value = []
    sts.replay_event.name_to_invariant_check = {name: check}
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    json_dict = dict(invariant_name=name, invariant_check=None,
                     invariant_check_name=name,
                     legacy_invariant_check=False,
                     label=label, event_time=event_time,
                     logical_round=logical_round, dependent_labels=[],
                     prunable=True, timed_out=False,
                     fingerprint="N/A")
    json_dict['class'] = "CheckInvariants"
    expected_event = CheckInvariants(invariant_check_name=name, label=label,
                                     logical_round=logical_round,
                                     event_time=event_time)
    # Act
    event = CheckInvariants.from_json(json_dict)
    # Assert
    self.assertEquals(expected_event, event)


class SwitchFailureTest(unittest.TestCase):
  def test_proceed(self):
    # Arrange
    dpid = 1
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    simulation = mock.Mock(name='Simulation')
    switch = mock.Mock(name='Switch')
    simulation.topology.switches_manager.get_switch_dpid.return_value = switch
    # Act
    event = SwitchFailure(dpid=dpid, label=label, logical_round=logical_round,
                          event_time=event_time)
    ret_val = event.proceed(simulation)
    # Assert
    self.assertTrue(ret_val)
    sw_mgm = simulation.topology.switches_manager
    sw_mgm.crash_switch.assert_called_once_with(switch)

  def test_to_json(self):
    # Arrange
    dpid = 1
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    expected = dict(label=label, dpid=dpid, event_time=event_time,
                    logical_round=logical_round, dependent_labels=[],
                    prunable=True, timed_out=False,
                    fingerprint=["SwitchFailure", 1])
    expected['class'] = "SwitchFailure"
    # Act
    event = SwitchFailure(dpid=dpid, label=label, logical_round=logical_round,
                          event_time=event_time)
    json_dump = event.to_json()
    # Assert

    self.assertEquals(expected, json.loads(json_dump))

  def test_from_json(self):
    # Arrange
    dpid = 1
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    json_dict = dict(label=label, dpid=dpid, event_time=event_time,
                     logical_round=logical_round, dependent_labels=[],
                     prunable=True, timed_out=False,
                     fingerprint=["SwitchFailure", 1])
    json_dict['class'] = "SwitchFailure"
    expected_event = SwitchFailure(dpid=dpid, label=label,
                                   logical_round=logical_round,
                                   event_time=event_time)
    # Act
    event = SwitchFailure.from_json(json_dict)
    # Assert
    self.assertEquals(expected_event, event)


class SwitchRecoveryTest(unittest.TestCase):
  def test_proceed(self):
    # Arrange
    dpid = 1
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    simulation = mock.Mock(name='Simulation')
    switch = mock.Mock(name='Switch')
    sw_mgm = simulation.topology.switches_manager
    sw_mgm.get_switch_dpid.return_value = switch
    def raise_error(x):
      raise TimeoutError()
    # Act
    event = SwitchRecovery(dpid=dpid, label=label, logical_round=logical_round,
                           event_time=event_time)
    event2 = SwitchRecovery(dpid=dpid, label='e2', logical_round=logical_round,
                            event_time=event_time)
    ret_val = event.proceed(simulation)
    # Test timeouts
    sw_mgm.recover_switch.side_effect = raise_error
    timeout_event = event2.proceed(simulation)
    # Assert
    self.assertTrue(ret_val)
    self.assertFalse(timeout_event)
    sw_mgm.recover_switch.assert_called_with(switch)

  def test_to_json(self):
    # Arrange
    dpid = 1
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    expected = dict(label=label, dpid=dpid, event_time=event_time,
                    logical_round=logical_round, dependent_labels=[],
                    prunable=True, timed_out=False,
                    fingerprint=["SwitchRecovery", 1])
    expected['class'] = "SwitchRecovery"
    # Act
    event = SwitchRecovery(dpid=dpid, label=label, logical_round=logical_round,
                           event_time=event_time)
    json_dump = event.to_json()
    # Assert
    self.assertEquals(expected, json.loads(json_dump))

  def test_from_json(self):
    # Arrange
    dpid = 1
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    json_dict = dict(label=label, dpid=dpid, event_time=event_time,
                     logical_round=logical_round, dependent_labels=[],
                     prunable=True, timed_out=False,
                     fingerprint=["SwitchRecovery", 1])
    json_dict['class'] = "SwitchRecovery"
    expected_event = SwitchRecovery(dpid=dpid, label=label,
                                    logical_round=logical_round,
                                    event_time=event_time)
    # Act
    event = SwitchRecovery.from_json(json_dict)
    # Assert
    self.assertEquals(expected_event, event)


class LinkFailureTest(unittest.TestCase):
  def test_proceed(self):
    # Arrange
    start_dpid, end_dpid = 1, 2
    start_port_no, end_port_no = 10, 20
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    simulation = mock.Mock(name='Simulation')
    sw1 = mock.Mock(name='Switch1')
    sw2 = mock.Mock(name='Switch2')
    sw1.ports = {start_port_no: mock.Mock(name='s1-1')}
    sw2.ports = {end_port_no: mock.Mock(name='s2-1')}
    link = mock.Mock(name='Link')

    def get_sw(dpid):
      return sw1 if dpid == start_dpid else sw2

    simulation.topology.switches_manager.get_switch_dpid.side_effect = get_sw
    simulation.topology.patch_panel.query_network_links.return_value = [link]
    # Act
    event = LinkFailure(start_dpid=start_dpid, start_port_no=start_port_no,
                        end_dpid=end_dpid, end_port_no=end_port_no, label=label,
                        logical_round=logical_round, event_time=event_time)
    ret_val = event.proceed(simulation)
    # Assert
    self.assertTrue(ret_val)
    patch_panel = simulation.topology.patch_panel
    patch_panel.sever_network_link.assert_called_once_with(link)

  def test_to_json(self):
    # Arrange
    start_dpid, end_dpid = 1, 2
    start_port_no, end_port_no = 10, 20
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    expected = dict(label=label, start_dpid=start_dpid,
                    start_port_no=start_port_no, end_dpid=end_dpid,
                    end_port_no=end_port_no, event_time=event_time,
                    logical_round=logical_round, dependent_labels=[],
                    prunable=True, timed_out=False,
                    fingerprint=["LinkFailure", start_dpid, start_port_no,
                                 end_dpid, end_port_no])
    expected['class'] = "LinkFailure"
    # Act
    event = LinkFailure(start_dpid=start_dpid, start_port_no=start_port_no,
                        end_dpid=end_dpid, end_port_no=end_port_no, label=label,
                        logical_round=logical_round, event_time=event_time)
    json_dump = event.to_json()
    # Assert
    self.assertEquals(expected, json.loads(json_dump))

  def test_from_json(self):
    # Arrange
    start_dpid, end_dpid = 1, 2
    start_port_no, end_port_no = 10, 20
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    json_dict = dict(label=label, start_dpid=start_dpid,
                     start_port_no=start_port_no, end_dpid=end_dpid,
                     end_port_no=end_port_no, event_time=event_time,
                     logical_round=logical_round, dependent_labels=[],
                     prunable=True, timed_out=False,
                     fingerprint=["LinkFailure", start_dpid, start_port_no,
                                  end_dpid, end_port_no])
    json_dict['class'] = "LinkFailure"
    expected_event = LinkFailure(start_dpid=start_dpid,
                                 start_port_no=start_port_no,
                                 end_dpid=end_dpid,
                                 end_port_no=end_port_no,
                                 label=label,
                                 logical_round=logical_round,
                                 event_time=event_time)
    # Act
    event = LinkFailure.from_json(json_dict)
    # Assert
    self.assertEquals(expected_event, event)


class LinkRecoveryTest(unittest.TestCase):
  def test_proceed(self):
    # Arrange
    start_dpid, end_dpid = 1, 2
    start_port_no, end_port_no = 10, 20
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    simulation = mock.Mock(name='Simulation')
    sw1 = mock.Mock(name='Switch1')
    sw2 = mock.Mock(name='Switch2')
    sw1.ports = {start_port_no: mock.Mock(name='s1-1')}
    sw2.ports = {end_port_no: mock.Mock(name='s2-1')}
    link = mock.Mock(name='Link')

    def get_sw(dpid):
      return sw1 if dpid == start_dpid else sw2

    simulation.topology.switches_manager.get_switch_dpid.side_effect = get_sw
    simulation.topology.patch_panel.query_network_links.return_value = [link]
    # Act
    event = LinkRecovery(start_dpid=start_dpid, start_port_no=start_port_no,
                         end_dpid=end_dpid, end_port_no=end_port_no, label=label,
                         logical_round=logical_round, event_time=event_time)
    ret_val = event.proceed(simulation)
    # Assert
    self.assertTrue(ret_val)
    patch_panel = simulation.topology.patch_panel
    patch_panel.repair_network_link.assert_called_once_with(link)

  def test_to_json(self):
    # Arrange
    start_dpid, end_dpid = 1, 2
    start_port_no, end_port_no = 10, 20
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    expected = dict(label=label, start_dpid=start_dpid,
                    start_port_no=start_port_no, end_dpid=end_dpid,
                    end_port_no=end_port_no, event_time=event_time,
                    logical_round=logical_round, dependent_labels=[],
                    prunable=True, timed_out=False,
                    fingerprint=["LinkRecovery", start_dpid, start_port_no,
                                 end_dpid, end_port_no])
    expected['class'] = "LinkRecovery"
    # Act
    event = LinkRecovery(start_dpid=start_dpid, start_port_no=start_port_no,
                         end_dpid=end_dpid, end_port_no=end_port_no, label=label,
                         logical_round=logical_round, event_time=event_time)
    json_dump = event.to_json()
    # Assert
    self.assertEquals(expected, json.loads(json_dump))

  def test_from_json(self):
    # Arrange
    start_dpid, end_dpid = 1, 2
    start_port_no, end_port_no = 10, 20
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    json_dict = dict(label=label, start_dpid=start_dpid,
                     start_port_no=start_port_no, end_dpid=end_dpid,
                     end_port_no=end_port_no, event_time=event_time,
                     logical_round=logical_round, dependent_labels=[],
                     prunable=True, timed_out=False,
                     fingerprint=["LinkRecovery", start_dpid, start_port_no,
                                  end_dpid, end_port_no])
    json_dict['class'] = "LinkRecovery"
    expected_event = LinkRecovery(start_dpid=start_dpid,
                                  start_port_no=start_port_no,
                                  end_dpid=end_dpid,
                                  end_port_no=end_port_no,
                                  label=label,
                                  logical_round=logical_round,
                                  event_time=event_time)
    # Act
    event = LinkRecovery.from_json(json_dict)
    # Assert
    self.assertEquals(expected_event, event)


class ControllerFailureTest(unittest.TestCase):
  def test_proceed(self):
    # Arrange
    cid = 1
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    simulation = mock.Mock(name='Simulation')
    c1 = mock.Mock(name='Controller')
    simulation.topology.controllers_manager.get_controller.return_value = c1
    # Act
    event = ControllerFailure(controller_id=cid, label=label,
                              logical_round=logical_round,
                              event_time=event_time)
    ret_val = event.proceed(simulation)
    # Assert
    self.assertTrue(ret_val)
    c_mgm = simulation.topology.controllers_manager
    c_mgm.crash_controller.assert_called_once_with(c1)

  def test_to_json(self):
    # Arrange
    cid = 1
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    expected = dict(controller_id=cid, label=label, event_time=event_time,
                    logical_round=logical_round, dependent_labels=[],
                    prunable=True, timed_out=False,
                    fingerprint=["ControllerFailure", cid])
    expected['class'] = "ControllerFailure"
    # Act
    event = ControllerFailure(controller_id=cid, label=label,
                              logical_round=logical_round,
                              event_time=event_time)
    json_dump = event.to_json()
    # Assert
    self.assertEquals(expected, json.loads(json_dump))

  def test_from_json(self):
    # Arrange
    cid = 1
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    json_dict = dict(controller_id=cid, label=label, event_time=event_time,
                     logical_round=logical_round, dependent_labels=[],
                     prunable=True, timed_out=False,
                     fingerprint=["ControllerFailure", cid])
    json_dict['class'] = "ControllerFailure"
    expected_event = ControllerFailure(controller_id=cid, label=label,
                                       logical_round=logical_round,
                                       event_time=event_time)
    # Act
    event = ControllerFailure.from_json(json_dict)
    # Assert
    self.assertEquals(expected_event, event)


class ControllerRecoveryTest(unittest.TestCase):
  def test_proceed(self):
    # Arrange
    cid = 1
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    simulation = mock.Mock(name='Simulation')
    c1 = mock.Mock(name='Controller')
    simulation.topology.controllers_manager.get_controller.return_value = c1
    # Act
    event = ControllerRecovery(controller_id=cid, label=label,
                               logical_round=logical_round,
                               event_time=event_time)
    ret_val = event.proceed(simulation)
    # Assert
    self.assertTrue(ret_val)
    c_mgm = simulation.topology.controllers_manager
    c_mgm.recover_controller.assert_called_once_with(c1)

  def test_to_json(self):
    # Arrange
    cid = 1
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    expected = dict(controller_id=cid, label=label, event_time=event_time,
                    logical_round=logical_round, dependent_labels=[],
                    prunable=True, timed_out=False,
                    fingerprint=["ControllerRecovery", cid])
    expected['class'] = "ControllerRecovery"
    # Act
    event = ControllerRecovery(controller_id=cid, label=label,
                               logical_round=logical_round,
                               event_time=event_time)
    json_dump = event.to_json()
    # Assert
    self.assertEquals(expected, json.loads(json_dump))

  def test_from_json(self):
    # Arrange
    cid = 1
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    json_dict = dict(controller_id=cid, label=label, event_time=event_time,
                     logical_round=logical_round, dependent_labels=[],
                     prunable=True, timed_out=False,
                     fingerprint=["ControllerRecovery", cid])
    json_dict['class'] = "ControllerRecovery"
    expected_event = ControllerRecovery(controller_id=cid, label=label,
                                        logical_round=logical_round,
                                        event_time=event_time)
    # Act
    event = ControllerRecovery.from_json(json_dict)
    # Assert
    self.assertEquals(expected_event, event)


class NOPEventTest(unittest.TestCase):
  def test_proceed(self):
    # Arrange
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    simulation = mock.Mock(name='Simulation')
    # Act
    event = NOPInput(label=label, logical_round=logical_round,
                     event_time=event_time)
    ret_val = event.proceed(simulation)
    # Assert
    self.assertTrue(ret_val)

  def test_to_json(self):
    # Arrange
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    expected = dict(label=label, event_time=event_time,
                    logical_round=logical_round, dependent_labels=[],
                    prunable=True, timed_out=False,
                    fingerprint=["NOPInput"])
    expected['class'] = "NOPInput"
    # Act
    event = NOPInput(label=label, logical_round=logical_round,
                     event_time=event_time)
    json_dump = event.to_json()
    # Assert
    self.assertEquals(expected, json.loads(json_dump))

  def test_from_json(self):
    # Arrange
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    json_dict = dict(label=label, event_time=event_time,
                     logical_round=logical_round, dependent_labels=[],
                     prunable=True, timed_out=False,
                     fingerprint=["NOPInput"])
    json_dict['class'] = "NOPInput"
    expected_event = NOPInput(label=label, logical_round=logical_round,
                              event_time=event_time)
    # Act
    event = NOPInput.from_json(json_dict)
    # Assert
    self.assertEquals(expected_event, event)


class InvariantViolationTest(unittest.TestCase):
  def test_proceed(self):
    # Arrange
    violations = ["Mock Violation"]
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    simulation = mock.Mock(name='Simulation')
    # Act
    event = InvariantViolation(violations=violations, label=label,
                               logical_round=logical_round,
                               event_time=event_time, persistent=False)
    ret_val = lambda: event.proceed(simulation)
    invalid_violation = lambda: InvariantViolation(violations=[])
    str_violations = InvariantViolation(violations=violations[0])
    # Assert
    self.assertRaises(ValueError, invalid_violation)
    self.assertRaises(RuntimeError, ret_val)
    self.assertFalse(event.persistent)
    self.assertEquals(event.violations, violations)
    self.assertEquals(str_violations.violations, violations)

  def test_to_json(self):
    # Arrange
    violations = ["Mock Violation"]
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    expected = dict(violations=violations, label=label, event_time=event_time,
                    logical_round=logical_round, dependent_labels=[],
                    prunable=True, timed_out=False, persistent=False,
                    fingerprint=["InvariantViolation"])
    expected['class'] = "InvariantViolation"
    # Act
    event = InvariantViolation(violations=violations, label=label,
                               logical_round=logical_round,
                               event_time=event_time, persistent=False)
    json_dump = event.to_json()
    # Assert
    self.assertEquals(expected, json.loads(json_dump))

  def test_from_json(self):
    # Arrange
    violations = ["Mock Violation"]
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    json_dict = dict(violations=violations, label=label, event_time=event_time,
                     logical_round=logical_round, dependent_labels=[],
                     prunable=True, timed_out=False, persistent=False,
                     fingerprint=["InvariantViolation"])
    json_dict['class'] = "NOPInput"
    expected_event = InvariantViolation(violations=violations, label=label,
                                        logical_round=logical_round,
                                        event_time=event_time, persistent=False)
    # Act
    event = InvariantViolation.from_json(json_dict)
    # Assert
    self.assertEquals(expected_event, event)


class AddIntentEventTest(unittest.TestCase):
  def test_proceed(self):
    # Arrange
    cid = 1
    intent_id = 100
    src_dpid, dst_dpid = 201, 202
    src_port, dst_port = 301, 302
    src_mac = EthAddr('00:00:00:00:00:01')
    dst_mac = EthAddr('00:00:00:00:00:02')
    static_path = ''
    intent_type = 'SHORTEST_PATH'
    intent_ip, intent_port, intent_url = '127.0.0.1', 8080, 'wm/intents'
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    simulation = mock.Mock(name='Simulation')
    c1 = mock.Mock(name='Controller')
    c1.add_intent.return_value = True
    simulation.topology.controllers_manager.get_controller.return_value = c1
    h1 = mock.Mock(name='h1')
    h1_eth1 = mock.Mock(name='h1-eth1')
    h1_eth1.hw_addr = src_mac
    h1.interfaces = [h1_eth1]
    h2 = mock.Mock(name='h2')
    h2_eth1 = mock.Mock(name='h2-eth1')
    h2_eth1.hw_addr = dst_mac
    h2.interfaces = [h2_eth1]
    simulation.topology.hosts_manager.hosts = [h1, h2]

    # Act
    event = AddIntent(cid=cid, intent_id=intent_id, src_dpid=src_dpid,
                      dst_dpid=dst_dpid, src_port=src_port,
                      dst_port=dst_port, src_mac=src_mac, dst_mac=dst_mac,
                      static_path=static_path, intent_type=intent_type,
                      intent_ip=intent_ip, intent_port=intent_port,
                      intent_url=intent_url, label=label,
                      logical_round=logical_round, event_time=event_time)
    ret_val = event.proceed(simulation)
    # Assert
    self.assertTrue(ret_val)
    track = simulation.topology.connectivity_tracker
    track.add_connected_hosts.assert_called_once_with(h1, h1_eth1, h2, h2_eth1,
                                                      intent_id)

  def test_to_json(self):
    # Arrange
    cid = 1
    intent_id = 100
    src_dpid, dst_dpid = 201, 202
    src_port, dst_port = 301, 302
    src_mac = str(EthAddr('00:00:00:00:00:01'))
    dst_mac = str(EthAddr('00:00:00:00:00:02'))
    static_path = ''
    intent_type = 'SHORTEST_PATH'
    intent_ip, intent_port, intent_url = '127.0.0.1', 8080, 'wm/intents'
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    expected = dict(cid=cid, intent_id=intent_id, src_dpid=src_dpid,
                    dst_dpid=dst_dpid, src_port=src_port,
                    dst_port=dst_port, src_mac=src_mac, dst_mac=dst_mac,
                    static_path=static_path, intent_type=intent_type,
                    intent_ip=intent_ip, intent_port=intent_port,
                    intent_url=intent_url, label=label, event_time=event_time,
                    logical_round=logical_round, dependent_labels=[],
                    prunable=True, timed_out=False, request_type='AddIntent',
                    fingerprint=["AddIntent", cid, intent_id, src_dpid,
                                 dst_dpid, src_port, dst_port, src_mac, dst_mac,
                                 static_path, intent_type, intent_ip,
                                 intent_port, intent_url])
    expected['class'] = "AddIntent"
    # Act
    event = AddIntent(cid=cid, intent_id=intent_id, src_dpid=src_dpid,
                      dst_dpid=dst_dpid, src_port=src_port,
                      dst_port=dst_port, src_mac=src_mac, dst_mac=dst_mac,
                      static_path=static_path, intent_type=intent_type,
                      intent_ip=intent_ip, intent_port=intent_port,
                      intent_url=intent_url, label=label,
                      logical_round=logical_round, event_time=event_time)
    json_dump = event.to_json()
    # Assert
    self.assertEquals(expected, json.loads(json_dump))

  def test_from_json(self):
    # Arrange
    cid = 1
    intent_id = 100
    src_dpid, dst_dpid = 201, 202
    src_port, dst_port = 301, 302
    src_mac = str(EthAddr('00:00:00:00:00:01'))
    dst_mac = str(EthAddr('00:00:00:00:00:02'))
    static_path = ''
    intent_type = 'SHORTEST_PATH'
    intent_ip, intent_port, intent_url = '127.0.0.1', 8080, 'wm/intents'
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    json_dict = dict(cid=cid, intent_id=intent_id, src_dpid=src_dpid,
                     dst_dpid=dst_dpid, src_port=src_port,
                     dst_port=dst_port, src_mac=src_mac, dst_mac=dst_mac,
                     static_path=static_path, intent_type=intent_type,
                     intent_ip=intent_ip, intent_port=intent_port,
                     intent_url=intent_url, label=label, event_time=event_time,
                     logical_round=logical_round, dependent_labels=[],
                     prunable=True, timed_out=False, request_type='AddIntent',
                     fingerprint=["AddIntent", cid, intent_id, src_dpid,
                                  dst_dpid, src_port, dst_port, src_mac,
                                  dst_mac, static_path, intent_type, intent_ip,
                                  intent_port, intent_url])
    json_dict['class'] = "AddIntent"
    expected_event = AddIntent(cid=cid, intent_id=intent_id, src_dpid=src_dpid,
                               dst_dpid=dst_dpid, src_port=src_port,
                               dst_port=dst_port, src_mac=src_mac,
                               dst_mac=dst_mac, static_path=static_path,
                               intent_type=intent_type, intent_ip=intent_ip,
                               intent_port=intent_port, intent_url=intent_url,
                               label=label, logical_round=logical_round,
                               event_time=event_time)
    # Act
    event = AddIntent.from_json(json_dict)
    # Assert
    self.assertEquals(expected_event, event)
    self.assertEquals(expected_event.src_mac, src_mac)


class RemoveIntentEventTest(unittest.TestCase):
  def test_proceed(self):
    # Arrange
    cid = 1
    intent_id = 100
    intent_ip, intent_port, intent_url = '127.0.0.1', 8080, 'wm/intents'
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    simulation = mock.Mock(name='Simulation')
    c1 = mock.Mock(name='Controller')
    c1.remove_intent.return_value = True
    simulation.topology.controllers_manager.get_controller.return_value = c1
    # Act
    event = RemoveIntent(cid=cid, intent_id=intent_id, intent_ip=intent_ip,
                         intent_port=intent_port, intent_url=intent_url,
                         label=label, logical_round=logical_round,
                         event_time=event_time)
    ret_val = event.proceed(simulation)
    # Assert
    self.assertTrue(ret_val)
    track = simulation.topology.connectivity_tracker
    track.remove_policy.assert_called_once_with(intent_id)

  def test_to_json(self):
    # Arrange
    cid = 1
    intent_id = 100
    request_type = 'RemoveIntent'
    intent_ip, intent_port, intent_url = '127.0.0.1', 8080, 'wm/intents'
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    expected = dict(cid=cid, intent_id=intent_id, intent_ip=intent_ip,
                    intent_port=intent_port, intent_url=intent_url, label=label,
                    event_time=event_time, logical_round=logical_round,
                    dependent_labels=[], prunable=True, timed_out=False,
                    request_type=request_type,
                    fingerprint=['RemoveIntent', cid, intent_id, intent_ip,
                                 intent_port, intent_url])
    expected['class'] = "RemoveIntent"
    # Act
    event = RemoveIntent(cid=cid, intent_id=intent_id, intent_ip=intent_ip,
                         intent_port=intent_port, intent_url=intent_url,
                         label=label, logical_round=logical_round,
                         event_time=event_time)
    json_dump = event.to_json()
    # Assert
    self.assertEquals(expected, json.loads(json_dump))

  def test_from_json(self):
    # Arrange
    cid = 1
    intent_id = 100
    request_type = 'RemoveIntent'
    intent_ip, intent_port, intent_url = '127.0.0.1', 8080, 'wm/intents'
    label = 'e1'
    logical_round = 1
    event_time = [1, 1]
    json_dict = dict(cid=cid, intent_id=intent_id, intent_ip=intent_ip,
                     intent_port=intent_port, intent_url=intent_url, label=label,
                     event_time=event_time, logical_round=logical_round,
                     dependent_labels=[], prunable=True, timed_out=False,
                     request_type=request_type,
                     fingerprint=['RemoveIntent', cid, intent_id, intent_ip,
                                  intent_port, intent_url])
    json_dict['class'] = "RemoveIntent"
    expected_event = RemoveIntent(cid=cid, intent_id=intent_id, intent_ip=intent_ip,
                                  intent_port=intent_port, intent_url=intent_url,
                                  label=label, logical_round=logical_round,
                                  event_time=event_time)
    # Act
    event = RemoveIntent.from_json(json_dict)
    # Assert
    self.assertEquals(expected_event, event)
