import logging
import pox.lib.revent
from pox.lib.revent import EventMixin
from sts.replay_event import ControllerStateChange, PendingStateChange
from sts.syncproto.base import SyncTime
from sts.syncproto.sts_syncer import STSSyncCallback

from collections import Counter

log = logging.getLogger("control_flow")

class ControlFlow(object):
  ''' Superclass of ControlFlow types '''
  def __init__(self, simulation_cfg):
    self.simulation_cfg = simulation_cfg
    self.sync_callback = None

  def simulate(self):
    ''' Move the simulation forward!'''
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

  def __init__(self, get_interpolated_time):
    self.get_interpolated_time = get_interpolated_time
    # TODO(cs): move buffering functionality into the GodScheduler? Or a
    # separate class?
    # Python's Counter object is effectively a multiset
    self._pending_state_changes = Counter()
    self.log = logging.getLogger("synccallback")

  def _pass_through_handler(self, state_change_event):
    state_change = state_change_event.pending_state_change
    # Pass through
    self.gc_pending_state_change(state_change)
    # Record
    replay_event = ControllerStateChange(tuple(state_change.controller_id),
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

  def gc_pending_state_change(self, pending_state_change):
    ''' Garbage collect the PendingStateChange from our buffer'''
    self._pending_state_changes[pending_state_change] -= 1
    if self._pending_state_changes[pending_state_change] <= 0:
      del self._pending_state_changes[pending_state_change]

  def flush(self):
    ''' Remove any pending state changes '''
    num_pending_state_changes = len(self._pending_state_changes)
    if num_pending_state_changes > 0:
      self.log.info("Flushing %d pending state changes" %
                    num_pending_state_changes)
    self._pending_state_changes = Counter()

  def state_change(self, controller, time, fingerprint, name, value):
    # TODO(cs): unblock the controller after processing the state change?
    pending_state_change = PendingStateChange(controller.uuid, time,
                                              fingerprint, name, value)
    self._pending_state_changes[pending_state_change] += 1
    self.raiseEvent(StateChange(pending_state_change))

  def pending_state_changes(self):
    ''' Return any pending state changes '''
    return self._pending_state_changes.keys()

  def get_deterministic_value(self, controller, name):
    if name == "gettimeofday":
      # Note: not a method, but a bound function
      value = self.get_interpolated_time()
      # TODO(cs): implement Andi's improved gettime heuristic
    else:
      raise ValueError("unsupported deterministic value: %s" % name)
    return value


class RecordingSyncCallback(STSSyncCallback):
  def __init__(self, input_logger):
    self.input_logger = input_logger

  def state_change(self, controller, time, fingerprint, name, value):
    if self.input_logger is not None:
      self.input_logger.log_input_event(ControllerStateChange(tuple(controller.uuid),
                                                              fingerprint,
                                                              name, value,
                                                              time=time))

  def get_deterministic_value(self, controller, name):
    value = None
    if name == "gettimeofday":
      value = SyncTime.now()
    else:
      raise ValueError("unsupported deterministic value: %s" % name)

    # TODO(cs): implement Andi's improved gettime heuristic, and uncomment
    #           the following statement
    #self.input_logger.log_input_event(klass="DeterministicValue",
    #                                  controller_id=controller.uuid,
    #                                  time=time, fingerprint="null",
    #                                  name=name, value=value)
    return value
