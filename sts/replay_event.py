'''
Classes for tracking replayed events.

Author: sw
'''

from sts.entities import Link
from sts.god_scheduler import PendingReceive
from sts.input_traces.fingerprints import *
import itertools
import abc
import logging
import time
import json
from collections import namedtuple
from sts.syncproto.base import SyncTime
log = logging.getLogger("events")


class EventDag(object):
  '''A collection of Event objects. EventDags are primarily used to present a
  view of the underlying events with one external event and all of its
  dependent internal events pruned (see events())
  '''
  def __init__(self, events):
    '''events is a list of EventWatcher objects. Refer to log_parser.parse to
    see how this is assembled.'''
    # we need to the events to be ordered, so we keep a copy of the list
    self._events = events
    self.label2event = {
      event.label : event
      for event in events
    }

  def events(self, pruned_event_or_label=None):
    '''Return a generator of the events in the DAG with pruned event and all of its
    internal dependents pruned'''
    if pruned_event_or_label is not None:
      if type(pruned_event_or_label) == str:
        assert(pruned_label in self.label2event)
        pruned_event = self.label2event[pruned_event_or_label]
        pruned_label = pruned_event_or_label
      else:
        assert(isinstance(pruned_event_or_label,Event))
        pruned_event = pruned_event_or_label
        pruned_label = pruned_event.label
      if not hasattr(pruned_event, 'dependent_labels'):
        raise RuntimeError("Pruned Event %s does not specify dependent_labels" %
                           str(pruned_event))
      pruned_labels = set(pruned_event.dependent_labels)
      pruned_labels.add(pruned_label)
      should_yield = lambda event: event.label not in pruned_labels
    else:
      should_yield = lambda x: True

    for event in self._events:
      if should_yield(event):
        yield event

  def event_watchers(self, pruned_event_or_label=None):
    '''Return a generator of the EventWatchers in the DAG with pruned event and
    all of its internal dependents pruned'''
    for event in self.events(pruned_event_or_label):
      yield EventWatcher(event)

class EventWatcher(object):
  '''EventWatchers watch events. This class can be used to wrap either
  InternalEvents or ExternalEvents to perform pre and post functionality.'''

  def __init__(self, event):
    self.event = event

  def run(self, simulation):
    self._pre()

    while not self.event.proceed(simulation):
      time.sleep(0.05)
      log.debug(".")

    self._post()

  def _pre(self):
    log.debug("Executing %s" % str(self.event))

  def _post(self):
    log.debug("Finished Executing %s" % str(self.event))

class Event(object):
  __metaclass__ = abc.ABCMeta

  # Create unique labels for events
  _label_gen = itertools.count(1)

  def __init__(self, label=None, time=None):
    if label is None:
      label = 'e' + str(Event._label_gen.next())
    if time is None:
      # TODO(cs): compress time for interactive mode?
      time = SyncTime.now()
    self.label = label
    self.time = time
    # Add on dependent labels to appease log_processing.superlog_parser.
    # TODO(cs): Replayer shouldn't depend on superlog_parser
    self.dependent_labels = []

  @abc.abstractmethod
  def proceed(self, simulation):
    '''Executes a single `round'. Returns a boolean that is true if the
    Replayer may continue to the next Event, otherwise proceed() again
    later.'''
    pass

  def to_json(self):
    fields = dict(self.__dict__)
    fields['class'] = self.__class__.__name__
    return json.dumps(fields)

  def __str__(self):
    return self.__class__.__name__ + ":" + self.label

# -------------------------------------------------------- #
# Semi-abstract classes for internal and external events   #
# -------------------------------------------------------- #

class InternalEvent(Event):
  '''An InternalEvent is one that happens within the controller(s) under
  simulation. Derivatives of this class verify that the internal event has
  occured in its proceed method before it returns.'''
  def __init__(self, label=None, time=None):
    super(InternalEvent, self).__init__(label=label, time=time)

  def proceed(self, simulation):
     # There might be nothing happening for certain internal events, so default
     # to just doing nothing for proceed (i.e. proceeding automatically).
    pass

class InputEvent(Event):
  '''An event that the simulator injects into the simulation. These events are
  assumed to be causally independent.

  Each InputEvent has a list of dependent InternalEvents that it takes in its
  constructor. This enables the pruning of events.

  This class also conceptually models (because it is equivalent to) 'external
  events', which is a term that may be used elsewhere in documentation or
  code.'''
  def __init__(self, label=None, time=None, dependent_labels=None):
    super(InputEvent, self).__init__(label=label, time=time)
    self.dependent_labels = dependent_labels

# --------------------------------- #
#  Concrete classes of InputEvents  #
# --------------------------------- #

def assert_fields_exist(json_hash, *args):
  ''' assert that the fields exist in json_hash '''
  fields = args
  for field in fields:
    if field not in json_hash:
      raise ValueError("Field %s not in json_hash %s" % (field, str(json_hash)))

def extract_label_time(json_hash):
  assert_fields_exist(json_hash, 'label', 'time')
  label = json_hash['label']
  time = SyncTime(json_hash['time'][0], json_hash['time'][1])
  return (label, time)

class SwitchFailure(InputEvent):
  def __init__(self, dpid, label=None, time=None):
    super(SwitchFailure, self).__init__(label=label, time=time)
    self.dpid = dpid

  def proceed(self, simulation):
    software_switch = simulation.topology.get_switch(self.dpid)
    simulation.topology.crash_switch(software_switch)
    return True

  @staticmethod
  def from_json(json_hash):
    (label, time) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'dpid')
    dpid = int(json_hash['dpid'])
    return SwitchFailure(dpid, label=label, time=time)

class SwitchRecovery(InputEvent):
  def __init__(self, dpid, label=None, time=None):
    super(SwitchRecovery, self).__init__(label=label, time=time)
    self.dpid = dpid

  def proceed(self, simulation):
    software_switch = simulation.topology.get_switch(self.dpid)
    simulation.topology.recover_switch(software_switch)
    return True

  @staticmethod
  def from_json(json_hash):
    (label, time) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'dpid')
    dpid = int(json_hash['dpid'])
    return SwitchRecovery(dpid, label=label, time=time)

def get_link(link_event, simulation):
  start_software_switch = simulation.topology.get_switch(link_event.start_dpid)
  end_software_switch = simulation.topology.get_switch(link_event.end_dpid)
  link = Link(start_software_switch, link_event.start_port_no,
              end_software_switch, link_event.end_port_no)
  return link

class LinkFailure(InputEvent):
  def __init__(self, start_dpid, start_port_no, end_dpid, end_port_no,
               label=None, time=None):
    super(LinkFailure, self).__init__(label=label, time=time)
    self.start_dpid = start_dpid
    self.start_port_no = start_port_no
    self.end_dpid = end_dpid
    self.end_port_no = end_port_no

  def proceed(self, simulation):
    link = get_link(self, simulation)
    simulation.topology.sever_link(link)
    return True

  @staticmethod
  def from_json(json_hash):
    (label, time) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'start_dpid', 'start_port_no', 'end_dpid',
                        'end_port_no')
    start_dpid = int(json_hash['start_dpid'])
    start_port_no = int(json_hash['start_port_no'])
    end_dpid = int(json_hash['end_dpid'])
    end_port_no = int(json_hash['end_port_no'])
    return LinkFailure(start_dpid, start_port_no, end_dpid, end_port_no,
                       label=label, time=time)

class LinkRecovery(InputEvent):
  def __init__(self, start_dpid, start_port_no, end_dpid, end_port_no,
               label=None, time=None):
    super(LinkRecovery, self).__init__(label=label, time=time)
    self.start_dpid = start_dpid
    self.start_port_no = start_port_no
    self.end_dpid = end_dpid
    self.end_port_no = end_port_no

  def proceed(self, simulation):
    link = get_link(self, simulation)
    simulation.topology.repair_link(link)
    return True

  @staticmethod
  def from_json(json_hash):
    (label, time) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'start_dpid', 'start_port_no', 'end_dpid',
                        'end_port_no')
    start_dpid = int(json_hash['start_dpid'])
    start_port_no = int(json_hash['start_port_no'])
    end_dpid = int(json_hash['end_dpid'])
    end_port_no = int(json_hash['end_port_no'])
    return LinkRecovery(start_dpid, start_port_no, end_dpid, end_port_no,
                        label=label, time=time)

class ControllerFailure(InputEvent):
  def __init__(self, controller_id, label=None, time=None):
    super(ControllerFailure, self).__init__(label=label, time=time)
    self.controller_id = controller_id

  def proceed(self, simulation):
    controller = simulation.controller_manager.get_controller(self.controller_id)
    simulation.controller_manager.kill_controller(controller)
    return True

  @staticmethod
  def from_json(json_hash):
    (label, time) = extract_label_time(json_hash)
    assert_fields_exist('controller_id')
    controller_id = json_hash['controller_id']
    controller_id = (controller_id[0], int(controller_id[1]))
    return ControllerFailure(controller_id, label=label, time=time)

class ControllerRecovery(InputEvent):
  def __init__(self, controller_id, label=None, time=None):
    super(ControllerRecovery, self).__init__(label=label, time=time)
    self.controller_id = controller_id

  def proceed(self, simulation):
    controller = simulation.controller_manager.get_controller(self.controller_id)
    simulation.controller_manager.reboot_controller(controller)
    return True

  @staticmethod
  def from_json(json_hash):
    (label, time) = extract_label_time(json_hash)
    assert_fields_exist('controller_id')
    controller_id = json_hash['controller_id']
    controller_id = (controller_id[0], int(controller_id[1]))
    return ControllerFailure(controller_id, label=label, time=time)

class HostMigration(InputEvent):
  def __init__(self, old_ingress_dpid, old_ingress_port_no,
               new_ingress_dpid, new_ingress_port_no, label=None, time=None):
    super(HostMigration, self).__init__(label=label, time=time)
    self.old_ingress_dpid = old_ingress_dpid
    self.old_ingress_port_no = old_ingress_port_no
    self.new_ingress_dpid = new_ingress_dpid
    self.new_ingress_port_no =  new_ingress_port_no

  def proceed(self, simulation):
    simulation.topology.migrate_host(self.old_ingress_dpid,
                                     self.old_ingress_port_no,
                                     self.new_ingress_dpid,
                                     self.new_ingress_port_no)
    return True

  @staticmethod
  def from_json(json_hash):
    (label, time) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'old_ingress_dpid', 'old_ingress_port_no',
                        'new_ingress_dpid', 'new_ingress_port_no')
    old_ingress_dpid = int(json_hash['old_ingress_dpid'])
    old_ingress_port_no = int(json_hash['old_ingress_port_no'])
    new_ingress_dpid = int(json_hash['new_ingress_dpid'])
    new_ingress_port_no = int(json_hash['new_ingress_port_no'])
    return HostMigration(old_ingress_dpid, old_ingress_port_no,
                         new_ingress_dpid, new_ingress_port_no,
                         label=label, time=time)

class PolicyChange(InputEvent):
  def __init__(self, request_type, label=None, time=None):
    super(PolicyChange, self).__init__(label=label, time=time)
    self.request_type = request_type

  def proceed(self, simulation):
    # TODO(cs): implement me, and add PolicyChanges to Fuzzer
    pass

  @staticmethod
  def from_json(json_hash):
    (label, time) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'request_type')
    request_type = json_hash['request_type']
    return PolicyChange(request_type, label=label, time=time)

class TrafficInjection(InputEvent):
  def __init__(self, label=None, time=None):
    super(TrafficInjection, self).__init__(label=label, time=time)

  def proceed(self, simulation):
    if simulation.dataplane_trace is None:
      raise RuntimeError("No dataplane trace specified!")
    simulation.dataplane_trace.inject_trace_event()
    return True

  @staticmethod
  def from_json(json_hash):
    (label, time) = extract_label_time(json_hash)
    return TrafficInjection(label, time)

class WaitTime(InputEvent):
  def __init__(self, wait_time, label=None, time=None):
    super(WaitTime, self).__init__(label=label, time=time)
    self.wait_time = wait_time

  def proceed(self, simulation):
    log.info("WaitTime: pausing simulation for %f seconds" % (self.wait_time))
    time.sleep(self.wait_time)
    return True

  @staticmethod
  def from_json(json_hash):
    (label, time) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'wait_time')
    wait_time = json_hash['wait_time']
    return WaitTime(wait_time, label=label, time=time)

all_input_events = [SwitchFailure, SwitchRecovery, LinkFailure, LinkRecovery,
                    ControllerFailure, ControllerRecovery, HostMigration,
                    PolicyChange, TrafficInjection, WaitTime]

# ----------------------------------- #
#  Concrete classes of InternalEvents #
# ----------------------------------- #

# Simulator's internal events:

class DataplaneDrop(InternalEvent):
  def __init__(self, fingerprint, label=None, time=None):
    super(DataplaneDrop, self).__init__(label=label, time=time)
    self.fingerprint = fingerprint

  def proceed(self, simulation):
    dp_event = simulation.patch_panel.get_buffered_dp_event(self.fingerprint)
    if dp_event is not None:
      simulation.patch_panel.drop_dp_event(dp_event)
      return True
    return False

  @staticmethod
  def from_json(json_hash):
    (label, time) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'fingerprint')
    fingerprint = json_hash['fingerprint']
    return DataplaneDrop(fingerprint, label=label, time=time)

class DataplanePermit(InternalEvent):
  def __init__(self, fingerprint, label=None, time=None):
    super(DataplanePermit, self).__init__(label=label, time=time)
    self.fingerprint = fingerprint

  def proceed(self, simulation):
    dp_event = simulation.patch_panel.get_buffered_dp_event(self.fingerprint)
    if dp_event is not None:
      simulation.patch_panel.permit_dp_event(dp_event)
      return True
    return False

  @staticmethod
  def from_json(json_hash):
    (label, time) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'fingerprint')
    fingerprint = json_hash['fingerprint']
    return DataplanePermit(fingerprint, label=label, time=time)

class ControlChannelBlock(InternalEvent):
  def __init__(self, dpid, controller_id, label=None, time=None):
    super(ControlChannelBlock, self).__init__(label=label, time=time)
    self.dpid = dpid
    self.controller_id = controller_id

  def proceed(self, simulation):
    switch = simulation.topology.get_switch(self.dpid)
    connection = switch.get_connection(self.controller_id)
    if connection.currently_blocked:
      raise RuntimeError("Expected channel %s to not be blocked" % str(connection))
    connection.block()
    return True

  @staticmethod
  def from_json(json_hash):
    (label, time) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'dpid', 'controller_id')
    dpid = json_hash['dpid']
    controller_id = tuple(json_hash['controller_id'])
    return ControlChannelBlock(dpid, controller_id, label=label, time=time)

class ControlChannelUnblock(InternalEvent):
  def __init__(self, dpid, controller_id, label=None, time=None):
    super(ControlChannelUnblock, self).__init__(label=label, time=time)
    self.dpid = dpid
    self.controller_id = controller_id

  def proceed(self, simulation):
    switch = simulation.topology.get_switch(self.dpid)
    connection = switch.get_connection(self.controller_id)
    if not connection.currently_blocked:
      raise RuntimeError("Expected channel %s to be blocked" % str(connection))
    connection.unblock()
    return True

  @staticmethod
  def from_json(json_hash):
    (label, time) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'dpid', 'controller_id')
    dpid = json_hash['dpid']
    controller_id = tuple(json_hash['controller_id'])
    return ControlChannelUnblock(dpid, controller_id, label=label, time=time)

class ControlMessageReceive(InternalEvent):
  '''
  Logged whenever the GodScheduler decides to allow a switch to see an
  openflow packet.
  '''
  def __init__(self, dpid, controller_id, fingerprint, label=None, time=None):
    super(ControlMessageReceive, self).__init__(label=label, time=time)
    self.dpid = dpid
    self.controller_id = controller_id
    self.fingerprint = fingerprint

  def proceed(self, simulation):
   pending_receive = PendingReceive(self.dpid, self.controller_id,
                                    self.fingerprint)
   message_waiting = simulation.god_scheduler.message_waiting(pending_receive)
   if message_waiting:
     simulation.god_scheduler.schedule(pending_receive)
     return True
   return False

  @staticmethod
  def from_json(json_hash):
    (label, time) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'dpid', 'controller_id', 'fingerprint')
    dpid = json_hash['dpid']
    controller_id = tuple(json_hash['controller_id'])
    fingerprint = OFFingerprint(json_hash['fingerprint'])
    return ControlMessageReceive(dpid, controller_id, fingerprint, label=label, time=time)

# Controllers' internal events:

# TODO(cs): move me?
PendingStateChange = namedtuple('PendingStateChange',
                                ['controller_id', 'time', 'fingerprint',
                                 'name', 'value'])

class ControllerStateChange(InternalEvent):
  '''
  Logged for any relevent kind of state change in the controller (e.g.
  mastership change)
  '''
  def __init__(self, controller_id, fingerprint, name, value, label=None, time=None):
    super(ControllerStateChange, self).__init__(label=label, time=time)
    self.controller_id = controller_id
    self.fingerprint = fingerprint
    self.name = name
    self.value = value

  def proceed(self, simulation):
    pending_state_change = PendingStateChange(self.controller_id, self.time,
                                              self.fingerprint, self.name, self.value)
    observed_yet = simulation.controller_sync_callback\
                             .state_change_pending(pending_state_change)
    if observed_yet:
      simulation.controller_sync_callback\
                .gc_pending_state_change(pending_state_change)
      return True
    return False

  @staticmethod
  def from_json(json_hash):
    (label, time) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'dpid', 'controller_id', 'fingerprint',
                        'name', 'value')
    controller_id = tuple(json_hash['controller_id'])
    fingerprint = json_hash['fingerprint']
    name = json_hash['name']
    value = json_hash['value']
    return ControllerStateChange(controller_id, fingerprint, name, value, label=label, time=time)

class DeterministicValue(InternalEvent):
  '''
  Logged whenever the controller asks for a deterministic value (e.g.
  gettimeofday()
  '''
  pass

all_internal_events = [DataplaneDrop, DataplanePermit, ControlChannelBlock,
                       ControlChannelUnblock, ControlMessageReceive,
                       ControllerStateChange, DeterministicValue]
