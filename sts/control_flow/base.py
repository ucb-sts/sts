# Copyright 2011-2013 Colin Scott
# Copyright 2011-2013 Andreas Wundsam
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

import logging
import pox.lib.revent
import abc
from pox.lib.revent import EventMixin
from sts.replay_event import ControllerStateChange, PendingStateChange, DeterministicValue
from sts.syncproto.base import SyncTime
from sts.syncproto.sts_syncer import STSSyncCallback
from sts.controller_manager import ControllerManager
from functools import partial

from collections import Counter

log = logging.getLogger("control_flow")

class ControlFlow(object):
  ''' Superclass of ControlFlow types '''
  __metaclass__ = abc.ABCMeta

  def __init__(self, simulation_cfg):
    self.simulation_cfg = simulation_cfg
    self.sync_callback = None
    self.invariant_check_name = None

  @abc.abstractmethod
  def simulate(self):
    ''' Move the simulation forward!'''
    pass

  def init_results(self, results_dir):
    ''' Set up event log files'''
    pass

  def get_sync_callback(self):
    return self.sync_callback

# ---------------------------------------- #
#  Callbacks for controller sync messages  #
# ---------------------------------------- #

class StateChange(pox.lib.revent.Event):
  def __init__(self, pending_state_change):
    super(StateChange, self).__init__()
    self.pending_state_change = pending_state_change

class ReplaySyncCallback(STSSyncCallback, EventMixin):

  _eventMixin_events = set([StateChange])

  def __init__(self, get_interpolated_time=None):
    ''' If get_interpolated_time is None, will always wait on deterministic
    values. If not None, will always invoke get_interpolated_time and respond
    immediately'''
    self.get_interpolated_time = get_interpolated_time
    # TODO(cs): move buffering functionality into the GodScheduler? Or a
    # separate class?
    # Python's Counter object is effectively a multiset
    self._pending_state_changes = Counter()
    # Each controller can have at most one outstanding state change (since
    # it's blocked)
    # { controller id -> function to send ACK message }
    self.cid2ack = {}
    # { controller id -> function to send deterministic value responses }
    self.cid2deterministic_value = {}
    self.log = logging.getLogger("synccallback")

  def _pass_through_handler(self, state_change_event):
    state_change = state_change_event.pending_state_change
    # Pass through
    self.ack_pending_state_change(state_change)
    # Record
    replay_event = ControllerStateChange(state_change.controller_id,
                                         state_change.fingerprint,
                                         state_change.name,
                                         state_change.value,
                                         time=state_change.time)
    self.passed_through_events.append(replay_event)

  def set_pass_through(self):
    '''Cause all pending state changes to pass through without being buffered'''
    self.passed_through_events = []
    self.addListener(StateChange, self._pass_through_handler)

  def unset_pass_through(self):
    '''Unset pass through mode, and return any events that were passed through
    since pass through mode was set'''
    self.removeListener(self._pass_through_handler)
    passed_events = self.passed_through_events
    self.passed_through_events = []
    return passed_events

  def state_change_pending(self, pending_state_change):
    ''' Return whether the PendingStateChange has been observed '''
    return self._pending_state_changes[pending_state_change] > 0

  def ack_pending_state_change(self, pending_state_change):
    ''' ACK the pending state change, and collect the PendingStateChange from our buffer'''
    self._pending_state_changes[pending_state_change] -= 1
    if self._pending_state_changes[pending_state_change] <= 0:
      del self._pending_state_changes[pending_state_change]
    if pending_state_change.controller_id in self.cid2ack:
      # Send an ACK to the controller to let it proceed
      self.cid2ack[pending_state_change.controller_id]()
      del self.cid2ack[pending_state_change.controller_id]

  def flush(self):
    ''' ACK any pending state changes '''
    num_pending_state_changes = len(self._pending_state_changes)
    if num_pending_state_changes > 0:
      self.log.info("Flushing %d pending state changes" %
                    num_pending_state_changes)
    self._pending_state_changes = Counter()
    for _, ack in self.cid2ack.iteritems():
      ack()
    self.cid2ack = {}

  def state_change(self, sync_type, xid, controller, time, fingerprint, name, value):
    # TODO(cs): xid arguably shouldn't be known to STS
    pending_state_change = PendingStateChange(controller.cid, time,
                                              fingerprint, name, value)
    self._pending_state_changes[pending_state_change] += 1
    if sync_type == "SYNC":
      cid = controller.cid
      if cid in self.cid2ack:
        raise RuntimeError("More than one outstanding ACKs for %s" %
                           str(cid))
      self.cid2ack[cid] =\
            partial(controller.sync_connection.ack_sync_notification,
                    "StateChange", xid)
    self.raiseEvent(StateChange(pending_state_change))

  def pending_state_changes(self):
    ''' Return any pending state changes '''
    return self._pending_state_changes.keys()

  def pending_state_changes_with_counts(self):
    ''' Return any pending state changes '''
    return self._pending_state_changes

  def get_deterministic_value(self, controller, name, xid):
    # TODO(cs): xid arguably shouldn't be known to STS
    if name != "gettimeofday":
      raise ValueError("unsupported deterministic value: %s" % name)

    # TODO(cs): need to dynamically set get_interpolated_time to not None for
    # peek()
    if self.get_interpolated_time is not None:
      value = self.get_interpolated_time()
      controller.sync_connection.send_deterministic_value(xid, value)
    else:
      self.cid2deterministic_value[controller.cid] =\
          partial(controller.sync_connection.send_deterministic_value, xid)

  def pending_deterministic_value_request(self, controller_id):
    return controller_id in self.cid2deterministic_value

  def send_deterministic_value(self, controller_id, value):
    self.cid2deterministic_value[controller_id](value)
    del self.cid2deterministic_value[controller_id]

class RecordingSyncCallback(STSSyncCallback):
  def __init__(self, input_logger, record_deterministic_values=False):
    self.input_logger = input_logger
    self.record_deterministic_values = record_deterministic_values

  def state_change(self, sync_type, xid, controller, time, fingerprint, name, value):
    # TODO(cs): xid arguably shouldn't be known to STS
    if self.input_logger is not None:
      self.input_logger.log_input_event(ControllerStateChange(controller.cid,
                                                              fingerprint,
                                                              name, value,
                                                              time=time))
    if sync_type == "SYNC":
      controller.sync_connection.ack_sync_notification("StateChange", xid)

  def get_deterministic_value(self, controller, name, xid):
    # TODO(cs): xid arguably shouldn't be known to STS
    value = None
    if name == "gettimeofday":
      value = SyncTime.now()
    else:
      raise ValueError("unsupported deterministic value: %s" % name)

    # TODO(cs): implement Andi's improved gettime heuristic
    if self.record_deterministic_values:
      self.input_logger.log_input_event(DeterministicValue(controller.cid,
                                                           name, value,
                                                           time=value))
    controller.sync_connection.send_deterministic_value(xid, value)

