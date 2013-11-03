# Copyright 2011-2013 Colin Scott
# Copyright 2011-2013 Andreas Wundsam
# Copyright 2012-2013 Sam Whitlock
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

'''
Classes representing events to be replayed. These events can be serialized to
events.trace JSON files.

Note about the JSON events.trace format:

All events are serialized to JSON with the Event.to_json() method.

All events have a fingerprint field, which is used to compute functional
equivalence between events across different replays of the trace.

The default format of the fingerprint field is a tuple (event class name,).

The specific format of the fingerprint field is documented in each class'
fingerprint() method.

The format of other additional fields is documented in
each event's __init__() method.
'''

from sts.util.convenience import base64_decode_openflow
from sts.util.console import msg
from sts.entities import Link
from sts.openflow_buffer import PendingReceive, PendingSend, OpenFlowBuffer
from sts.dataplane_traces.trace import DataplaneEvent
from sts.fingerprints.messages import *
from config.invariant_checks import name_to_invariant_check
import itertools
import abc
import logging
import time
import marshal
import types
import json
from collections import namedtuple
from sts.syncproto.base import SyncTime
from pox.lib.util import TimeoutError
log = logging.getLogger("events")

def dictify_fingerprint(fingerprint):
  # Hack: convert Fingerprint objects into Fingerprint.to_dict()
  mutable = list(fingerprint)
  for i, e in enumerate(mutable):
    if isinstance(mutable[i], Fingerprint):
      mutable[i] = mutable[i].to_dict()
  return tuple(mutable)

class Event(object):
  ''' Superclass for all event types. '''
  __metaclass__ = abc.ABCMeta

  # Create unique labels for events
  _label_gen = itertools.count(1)
  # Ensure globally unique labels
  _all_label_ids = set()

  def __init__(self, prefix="e", label=None, round=-1, time=None, dependent_labels=None,
               prunable=True):
    if label is None:
      label_id = Event._label_gen.next()
      label = prefix + str(label_id)
      while label_id in Event._all_label_ids:
        label_id = Event._label_gen.next()
        label = prefix + str(label_id)
    if time is None:
      # TODO(cs): compress time for interactive mode?
      time = SyncTime.now()
    self.label = label
    Event._all_label_ids.add(int(label[1:]))
    self.round = round
    self.time = time
    # Add on dependent labels to appease log_processing.superlog_parser.
    # TODO(cs): Replayer shouldn't depend on superlog_parser
    self.dependent_labels = dependent_labels if dependent_labels else []
    # Whether this event should be prunable by MCSFinder. Initialization
    # inputs are not pruned.
    self.prunable = True
    # Whether the (internal) event timed out in the most recent round
    self.timed_out = False

  @property
  def label_id(self):
    return int(self.label[1:])

  @property
  def fingerprint(self):
    ''' All events must have a fingerprint. Fingerprints are used to compute
    functional equivalence. '''
    return (self.__class__.__name__,)

  @abc.abstractmethod
  def proceed(self, simulation):
    '''Executes a single `round'. Returns a boolean that is true if the
    Replayer may continue to the next Event, otherwise proceed() again
    later.'''
    pass

  def to_json(self):
    ''' Convert the event to json format '''
    fields = dict(self.__dict__)
    fields['class'] = self.__class__.__name__
    # fingerprints are accessed through @property, not in __dict__:
    fields['fingerprint'] = dictify_fingerprint(self.fingerprint)
    if '_fingerprint' in fields:
      del fields['_fingerprint']
    return json.dumps(fields)

  def __hash__(self):
    # Assumption: labels are unique
    return self.label.__hash__()

  def __eq__(self, other):
    # Assumption: labels are unique
    if type(self) != type(other):
      return False
    return self.label == other.label

  def __ne__(self, other):
    return not self.__eq__(other)

  def __str__(self):
    return self.__class__.__name__ + ":" + self.label

  def __repr__(self):
    s = self.__class__.__name__ + ":" + self.label \
            + ":" + str(self.fingerprint)
    return s

# -------------------------------------------------------- #
# Semi-abstract classes for internal and external events   #
# -------------------------------------------------------- #

class InternalEvent(Event):
  '''An InternalEvent is one that happens within the controller(s) under
  simulation. Derivatives of this class verify that the internal event has
  occured during replay in its proceed method before it returns.'''
  def __init__(self, label=None, round=-1, time=None, timeout_disallowed=False,
               prunable=False):
    super(InternalEvent, self).__init__(prefix='i', label=label, round=round, time=time,
                                        prunable=prunable)
    self.timeout_disallowed = timeout_disallowed

  def proceed(self, simulation):
    # There might be nothing happening for certain internal events, so default
    # to just doing nothing for proceed (i.e. proceeding automatically).
    pass

  def disallow_timeouts(self):
    self.timeout_disallowed = True

class InputEvent(Event):
  '''An InputEvents is an event that the simulator injects into the simulation.

  Each InputEvent has a list of dependent InternalEvents that it takes in its
  constructor. This enables us to properly prune events.

  `InputEvents' may also be referred to as 'external
  events', elsewhere in documentation or code.'''
  def __init__(self, label=None, round=-1, time=None, dependent_labels=None,
               prunable=True):
    super(InputEvent, self).__init__(prefix='e', label=label, round=round, time=time,
                                     dependent_labels=dependent_labels,
                                     prunable=prunable)

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
  assert_fields_exist(json_hash, 'label', 'time', 'round')
  label = json_hash['label']
  time = SyncTime(json_hash['time'][0], json_hash['time'][1])
  round = json_hash['round']
  return (label, time, round)

class SwitchFailure(InputEvent):
  ''' Crashes a switch, by disconnecting its TCP connection with the
  controller(s).'''
  def __init__(self, dpid, label=None, round=-1, time=None):
    '''
    Parameters:
     - dpid: unique integer identifier of the switch.
     - label: a unique label for this event. Internal event labels begin with 'i'
       and input event labels begin with 'e'.
     - time: the timestamp of when this event occured. Stored as a tuple:
       [seconds since unix epoch, microseconds].
     - round: optional integer. Indicates what simulation round this event occured
       in.
    '''
    super(SwitchFailure, self).__init__(label=label, round=round, time=time)
    self.dpid = dpid

  def proceed(self, simulation):
    software_switch = simulation.topology.get_switch(self.dpid)
    simulation.topology.crash_switch(software_switch)
    return True

  @staticmethod
  def from_json(json_hash):
    (label, time, round) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'dpid')
    dpid = int(json_hash['dpid'])
    return SwitchFailure(dpid, label=label, round=round, time=time)

  @property
  def fingerprint(self):
    ''' Fingerprint tuple format: (class name, dpid) '''
    return (self.__class__.__name__,self.dpid,)

class SwitchRecovery(InputEvent):
  ''' Recovers a crashed switch, by reconnecting its TCP connection with the
  controller(s).'''
  def __init__(self, dpid, label=None, round=-1, time=None):
    '''
    Parameters:
     - dpid: unique integer identifier of the switch.
     - label: a unique label for this event. Internal event labels begin with 'i'
       and input event labels begin with 'e'.
     - time: the timestamp of when this event occured. Stored as a tuple:
       [seconds since unix epoch, microseconds].
     - round: optional integer. Indicates what simulation round this event occured
       in.
    '''
    super(SwitchRecovery, self).__init__(label=label, round=round, time=time)
    self.dpid = dpid

  def proceed(self, simulation):
    software_switch = simulation.topology.get_switch(self.dpid)
    try:
      down_controller_ids = map(lambda c: c.cid,
                                simulation.controller_manager.down_controllers)

      simulation.topology.recover_switch(software_switch,
                                         down_controller_ids=down_controller_ids)
    except TimeoutError:
      # Controller is down... Hopefully control flow will notice soon enough
      log.warn("Timed out on %s" % str(self.fingerprint))
    return True

  @staticmethod
  def from_json(json_hash):
    (label, time, round) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'dpid')
    dpid = int(json_hash['dpid'])
    return SwitchRecovery(dpid, round=round, label=label, time=time)

  @property
  def fingerprint(self):
    ''' Fingerprint tuple format: (class name, dpid) '''
    return (self.__class__.__name__,self.dpid,)

def get_link(link_event, simulation):
  start_software_switch = simulation.topology.get_switch(link_event.start_dpid)
  end_software_switch = simulation.topology.get_switch(link_event.end_dpid)
  link = Link(start_software_switch, link_event.start_port_no,
              end_software_switch, link_event.end_port_no)
  return link

class LinkFailure(InputEvent):
  ''' Cuts a link between switches. This causes the switch to send an
  ofp_port_status message to its parent(s). All packets forwarded over
  this link will be dropped until a LinkRecovery occurs.'''
  def __init__(self, start_dpid, start_port_no, end_dpid, end_port_no,
               label=None, round=-1, time=None):
    '''
    Parameters:
     - start_dpid: unique integer identifier of the first switch connected to the link.
     - start_port_no: integer port number of the start switch's port.
     - end_dpid: unique integer identifier of the second switch connected to the link.
     - end_port_no: integer port number of the end switch's port to be created.
     - label: a unique label for this event. Internal event labels begin with 'i'
       and input event labels begin with 'e'.
     - time: the timestamp of when this event occured. Stored as a tuple:
       [seconds since unix epoch, microseconds].
     - round: optional integer. Indicates what simulation round this event occured
       in.
    '''
    super(LinkFailure, self).__init__(label=label, round=round, time=time)
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
    (label, time, round) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'start_dpid', 'start_port_no', 'end_dpid',
                        'end_port_no')
    start_dpid = int(json_hash['start_dpid'])
    start_port_no = int(json_hash['start_port_no'])
    end_dpid = int(json_hash['end_dpid'])
    end_port_no = int(json_hash['end_port_no'])
    return LinkFailure(start_dpid, start_port_no, end_dpid, end_port_no,
                       round=round, label=label, time=time)

  @property
  def fingerprint(self):
    ''' Fingerprint tuple format:
    (class name, start dpid, start port_no, end dpid, end port_no) '''
    return (self.__class__.__name__,
            self.start_dpid, self.start_port_no,
            self.end_dpid, self.end_port_no)

class LinkRecovery(InputEvent):
  ''' Recovers a failed link between switches. This causes the switch to send an
  ofp_port_status message to its parent(s). '''
  def __init__(self, start_dpid, start_port_no, end_dpid, end_port_no,
               label=None, round=-1, time=None):
    '''
    Parameters:
     - start_dpid: unique integer identifier of the first switch connected to the link.
     - start_port_no: integer port number of the start switch's port.
     - end_dpid: unique integer identifier of the second switch connected to the link.
     - end_port_no: integer port number of the end switch's port to be created.
     - label: a unique label for this event. Internal event labels begin with 'i'
       and input event labels begin with 'e'.
     - time: the timestamp of when this event occured. Stored as a tuple:
       [seconds since unix epoch, microseconds].
     - round: optional integer. Indicates what simulation round this event occured
       in.
    '''
    super(LinkRecovery, self).__init__(label=label, round=round, time=time)
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
    (label, time, round) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'start_dpid', 'start_port_no', 'end_dpid',
                        'end_port_no')
    start_dpid = int(json_hash['start_dpid'])
    start_port_no = int(json_hash['start_port_no'])
    end_dpid = int(json_hash['end_dpid'])
    end_port_no = int(json_hash['end_port_no'])
    return LinkRecovery(start_dpid, start_port_no, end_dpid, end_port_no,
                        round=round, label=label, time=time)

  @property
  def fingerprint(self):
    ''' Fingerprint tuple format:
    (class name, start dpid, start port, end dpid, end port)
    '''
    return (self.__class__.__name__,
            self.start_dpid, self.start_port_no,
            self.end_dpid, self.end_port_no)

class ControllerFailure(InputEvent):
  ''' Kills a controller process with `kill -9`'''
  def __init__(self, controller_id, label=None, round=-1, time=None):
    '''
    Parameters:
     - controller_id: unique string label for the controller to be killed.
     - label: a unique label for this event. Internal event labels begin with 'i'
       and input event labels begin with 'e'.
     - time: the timestamp of when this event occured. Stored as a tuple:
       [seconds since unix epoch, microseconds].
     - round: optional integer. Indicates what simulation round this event occured
       in.
    '''
    super(ControllerFailure, self).__init__(label=label, round=round, time=time)
    self.controller_id = controller_id

  def proceed(self, simulation):
    controller = simulation.controller_manager.get_controller(self.controller_id)
    simulation.controller_manager.kill_controller(controller)
    return True

  @staticmethod
  def from_json(json_hash):
    (label, time, round) = extract_label_time(json_hash)
    assert_fields_exist('controller_id')
    controller_id = json_hash['controller_id']
    return ControllerFailure(controller_id, round=round, label=label, time=time)

  @property
  def fingerprint(self):
    ''' Fingerprint tuple format: (class name, controller id) '''
    return (self.__class__.__name__,self.controller_id)

class ControllerRecovery(InputEvent):
  ''' Reboots a crashed controller by reinvoking its original command line
  parameters'''
  def __init__(self, controller_id, label=None, round=-1, time=None):
    '''
    Parameters:
     - controller_id: unique string label for the controller.
     - label: a unique label for this event. Internal event labels begin with 'i'
       and input event labels begin with 'e'.
     - time: the timestamp of when this event occured. Stored as a tuple:
       [seconds since unix epoch, microseconds].
     - round: optional integer. Indicates what simulation round this event occured
       in.
    '''
    super(ControllerRecovery, self).__init__(label=label, round=round, time=time)
    self.controller_id = controller_id

  def proceed(self, simulation):
    controller = simulation.controller_manager.get_controller(self.controller_id)
    simulation.controller_manager.reboot_controller(controller)
    return True

  @staticmethod
  def from_json(json_hash):
    (label, time, round) = extract_label_time(json_hash)
    assert_fields_exist('controller_id')
    controller_id = json_hash['controller_id']
    return ControllerRecovery(controller_id, round=round, label=label, time=time)

  @property
  def fingerprint(self):
    ''' Fingerprint tuple format: (class name, controller id) '''
    return (self.__class__.__name__,self.controller_id)

class HostMigration(InputEvent):
  ''' Migrates a host from one location in network to another. Creates a new
  virtual port on the new switch, and takes down the old port on the old switch.
  '''
  def __init__(self, old_ingress_dpid, old_ingress_port_no,
               new_ingress_dpid, new_ingress_port_no, host_id, label=None, round=-1, time=None):
    '''
    Parameters:
     - old_ingress_dpid: unique integer identifier of the ingress switch the host is
       moving away from.
     - old_ingress_port_no: integer identifier of the port the host is moving
       away from.
     - new_ingress_dpid: unique integer identifier of the ingress switch the host is
       moving to.
     - new_ingress_port_no: integer identifier of the port the host is moving
       to.
     - host_id: unique integer identifier of the host.
     - label: a unique label for this event. Internal event labels begin with 'i'
       and input event labels begin with 'e'.
     - time: the timestamp of when this event occured. Stored as a tuple:
       [seconds since unix epoch, microseconds].
     - round: optional integer. Indicates what simulation round this event occured
       in.
    '''
    super(HostMigration, self).__init__(label=label, round=round, time=time)
    self.old_ingress_dpid = old_ingress_dpid
    self.old_ingress_port_no = old_ingress_port_no
    self.new_ingress_dpid = new_ingress_dpid
    self.new_ingress_port_no =  new_ingress_port_no
    self.host_id = host_id

  def proceed(self, simulation):
    simulation.topology.migrate_host(self.old_ingress_dpid,
                                     self.old_ingress_port_no,
                                     self.new_ingress_dpid,
                                     self.new_ingress_port_no)
    return True

  @staticmethod
  def from_json(json_hash):
    (label, time, round) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'old_ingress_dpid', 'old_ingress_port_no',
                        'new_ingress_dpid', 'new_ingress_port_no', 'host_id')
    old_ingress_dpid = int(json_hash['old_ingress_dpid'])
    old_ingress_port_no = int(json_hash['old_ingress_port_no'])
    new_ingress_dpid = int(json_hash['new_ingress_dpid'])
    new_ingress_port_no = int(json_hash['new_ingress_port_no'])
    host_id = json_hash['host_id']
    return HostMigration(old_ingress_dpid, old_ingress_port_no,
                         new_ingress_dpid, new_ingress_port_no,
                         host_id, round=round, label=label, time=time)

  @property
  def old_location(self):
    return (self.old_ingress_dpid, self.old_ingress_port_no)

  @property
  def new_location(self):
    return (self.new_ingress_dpid, self.new_ingress_port_no)

  @property
  def fingerprint(self):
    ''' Fingerprint tuple format:
    (class name, old dpid, old port, new dpid, new port, host id) '''
    return (self.__class__.__name__,self.old_ingress_dpid,
            self.old_ingress_port_no, self.new_ingress_dpid,
            self.new_ingress_port_no, self.host_id)

class PolicyChange(InputEvent):
  ''' Not currently supported '''
  def __init__(self, request_type, label=None, round=-1, time=None):
    super(PolicyChange, self).__init__(label=label, round=round, time=time)
    self.request_type = request_type

  def proceed(self, simulation):
    # TODO(cs): implement me, and add PolicyChanges to Fuzzer
    pass

  @staticmethod
  def from_json(json_hash):
    (label, time, round) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'request_type')
    request_type = json_hash['request_type']
    return PolicyChange(request_type, round=round, label=label, time=time)

class TrafficInjection(InputEvent):
  ''' Injects a dataplane packet into the network at the given host's access link '''
  def __init__(self, label=None, dp_event=None, host_id=None, round=-1, time=None, prunable=True):
    '''
    Parameters:
     - dp_event: DataplaneEvent object encapsulating the packet contents and the
       access link.
     - host_id: unique integer label identifying the host that generated the
       packet.
     - label: a unique label for this event. Internal event labels begin with 'i'
       and input event labels begin with 'e'.
     - time: the timestamp of when this event occured. Stored as a tuple:
       [seconds since unix epoch, microseconds].
     - round: optional integer. Indicates what simulation round this event occured
       in.
     - prunable: whether this input event can be pruned during delta
       debugging.
    '''
    super(TrafficInjection, self).__init__(label=label, round=round, time=time,
                                           prunable=prunable)
    self.dp_event = dp_event
    self.host_id = host_id

  def proceed(self, simulation):
    # If dp_event is None, backwards compatibility
    if self.dp_event is None:
      if simulation.dataplane_trace is None:
        raise RuntimeError("No dataplane trace specified!")
      simulation.dataplane_trace.inject_trace_event()
    else:
      host = simulation.topology.link_tracker\
                       .interface2access_link[self.dp_event.interface].host
      host.send(self.dp_event.interface, self.dp_event.packet)
    return True

  @property
  def fingerprint(self):
    ''' Fingerprint tuple format: (class name, dp event, host_id)
    The format of dp event is:
    {"interface": HostInterface.to_json(), "packet": base 64 encoded packet contents}
    See entities.py for the HostInterface json format.
    '''
    return (self.__class__.__name__, self.dp_event, self.host_id)

  def to_json(self):
    fields = {}
    fields = dict(self.__dict__)
    fields['class'] = self.__class__.__name__
    fields['dp_event'] = self.dp_event.to_json()
    fields['fingerprint'] = (self.__class__.__name__, self.dp_event.to_json(), self.host_id)
    fields['host_id'] = self.host_id
    return json.dumps(fields)

  @staticmethod
  def from_json(json_hash):
    (label, time, round) = extract_label_time(json_hash)
    prunable = True
    if 'prunable' in json_hash:
      prunable = json_hash['prunable']
    dp_event = None
    if 'dp_event' in json_hash:
      dp_event = DataplaneEvent.from_json(json_hash['dp_event'])
    host_id = None
    if 'host_id' in json_hash:
      host_id = json_hash['host_id']
    return TrafficInjection(label=label, dp_event=dp_event, host_id=host_id, time=time, round=round, prunable=prunable)

class WaitTime(InputEvent):
  ''' Causes the simulation to sleep for the specified number of seconds.
  Controller processes continue running during this time.'''
  def __init__(self, wait_time, label=None, round=-1, time=None):
    '''
    Parameters:
     - wait_time: float representing how long to sleep in seconds.
     - label: a unique label for this event. Internal event labels begin with 'i'
       and input event labels begin with 'e'.
     - time: the timestamp of when this event occured. Stored as a tuple:
       [seconds since unix epoch, microseconds].
     - round: optional integer. Indicates what simulation round this event occured
       in.
    '''
    super(WaitTime, self).__init__(label=label, round=round, time=time)
    self.wait_time = wait_time

  def proceed(self, simulation):
    log.info("WaitTime: pausing simulation for %f seconds" % (self.wait_time))
    time.sleep(self.wait_time)
    return True

  @staticmethod
  def from_json(json_hash):
    (label, time, round) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'wait_time')
    wait_time = json_hash['wait_time']
    return WaitTime(wait_time, round=round, label=label, time=time)

class CheckInvariants(InputEvent):
  ''' Causes the simulation to pause itself and check the given invariant before
  proceeding. '''
  def __init__(self, label=None, round=-1, time=None,
               invariant_check_name="InvariantChecker.check_correspondence"):
    '''
    Parameters:
     - label: a unique label for this event. Internal event labels begin with 'i'
       and input event labels begin with 'e'.
     - time: the timestamp of when this event occured. Stored as a tuple:
       [seconds since unix epoch, microseconds].
     - round: optional integer. Indicates what simulation round this event occured
       in.
     - invariant_check_name: unique name of the invariant to be checked. See
       config.invariant_checks for an exhaustive list of possible invariant
       checks.
    '''
    super(CheckInvariants, self).__init__(label=label, round=round, time=time)
    # For backwards compatibility.. (invariants used to be specified as
    # marshalled functions, not invariant check names)
    self.legacy_invariant_check = not isinstance(invariant_check_name, basestring)
    if self.legacy_invariant_check:
      self.invariant_check = invariant_check_name
    else:
      # Otherwise, invariant check is specified as a name
      self.invariant_check_name = invariant_check_name
      if invariant_check_name not in name_to_invariant_check:
        raise ValueError('''Unknown invariant check %s.\n'''
                         '''Invariant check name must be defined in config.invariant_checks''',
                         invariant_check_name)
      self.invariant_check = name_to_invariant_check[invariant_check_name]

  def proceed(self, simulation):
    try:
      violations = self.invariant_check(simulation)
      simulation.violation_tracker.track(violations, self.round)
      persistent_violations = simulation.violation_tracker.persistent_violations
    except NameError as e:
      raise ValueError('''Closures are unsupported for invariant check '''
                       '''functions.\n Use dynamic imports inside of your '''
                       '''invariant check code and define all globals '''
                       '''locally.\n NameError: %s''' % str(e))
    if violations != []:
      msg.fail("The following correctness violations have occurred: %s" % str(violations))
      if hasattr(simulation, "fail_to_interactive") and simulation.fail_to_interactive:
        raise KeyboardInterrupt("fail to interactive")
    else:
      msg.success("No correctness violations!")
    if persistent_violations != []:
      msg.fail("Persistent violations detected!: %s" % str(persistent_violations))
      if hasattr(simulation, "fail_to_interactive_on_persistent_violations") and\
        simulation.fail_to_interactive_on_persistent_violations:
        raise KeyboardInterrupt("fail to interactive on persistent violation")
    return True

  def to_json(self):
    fields = dict(self.__dict__)
    fields['class'] = self.__class__.__name__
    if self.legacy_invariant_check:
      fields['invariant_check'] = marshal.dumps(self.invariant_check.func_code)\
                                         .encode('base64')
      fields['invariant_name'] = self.invariant_check.__name__
    else:
      fields['invariant_name'] = self.invariant_check_name
      fields['invariant_check'] = None
    fields['fingerprint'] = "N/A"
    return json.dumps(fields)

  @staticmethod
  def from_json(json_hash):
    (label, time, round) = extract_label_time(json_hash)
    invariant_check_name = "InvariantChecker.check_connectivity"
    if 'invariant_name' in json_hash:
      invariant_check_name  = json_hash['invariant_name']
    elif 'invariant_check' in json_hash:
      # Legacy code (marshalled function)
      # Assumes that the closure is empty
      code = marshal.loads(json_hash['invariant_check'].decode('base64'))
      invariant_check_name = types.FunctionType(code, globals())

    return CheckInvariants(label=label, time=time, round=round,
                           invariant_check_name=invariant_check_name)

class ControlChannelBlock(InputEvent):
  ''' Simulates delay between switches and controllers by temporarily
  queuing all messages sent on the switch<->controller TCP connection. No
  messages will be sent over the connection until a ControlChannelUnblock
  occurs. '''
  def __init__(self, dpid, controller_id, label=None, round=-1, time=None):
    '''
    Parameters:
     - dpid: unique integer identifier of the switch.
     - controller_id: unique string label for the controller.
     - label: a unique label for this event. Internal event labels begin with 'i'
       and input event labels begin with 'e'.
     - time: the timestamp of when this event occured. Stored as a tuple:
       [seconds since unix epoch, microseconds].
     - round: optional integer. Indicates what simulation round this event occured
       in.
    '''
    super(ControlChannelBlock, self).__init__(label=label, round=round, time=time)
    self.dpid = dpid
    self.controller_id = controller_id

  def proceed(self, simulation):
    switch = simulation.topology.get_switch(self.dpid)
    connection = switch.get_connection(self.controller_id)
    if connection.io_worker.currently_blocked:
      raise RuntimeError("Expected channel %s to not be blocked" % str(connection))
    connection.io_worker.block()
    return True

  @property
  def fingerprint(self):
    ''' Fingerprint tuple format: (class name, dpid, controller id)
    '''
    return (self.__class__.__name__,
            self.dpid, self.controller_id)

  @staticmethod
  def from_json(json_hash):
    (label, time, round) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'dpid', 'controller_id')
    dpid = json_hash['dpid']
    controller_id = json_hash['controller_id']
    return ControlChannelBlock(dpid, controller_id, round=round, label=label, time=time)

class ControlChannelUnblock(InputEvent):
  ''' Unblocks the control channel delay triggered by a ControlChannelUnblock.
  All queued messages will be sent.'''
  def __init__(self, dpid, controller_id, label=None, round=-1, time=None):
    '''
    Parameters:
     - dpid: unique integer identifier of the switch.
     - controller_id: unique string label for the controller.
     - label: a unique label for this event. Internal event labels begin with 'i'
       and input event labels begin with 'e'.
     - time: the timestamp of when this event occured. Stored as a tuple:
       [seconds since unix epoch, microseconds].
     - round: optional integer. Indicates what simulation round this event occured
       in.
    '''
    super(ControlChannelUnblock, self).__init__(label=label, round=round, time=time)
    self.dpid = dpid
    self.controller_id = controller_id

  def proceed(self, simulation):
    switch = simulation.topology.get_switch(self.dpid)
    connection = switch.get_connection(self.controller_id)
    if not connection.io_worker.currently_blocked:
      raise RuntimeError("Expected channel %s to be blocked" % str(connection))
    connection.io_worker.unblock()
    return True

  @property
  def fingerprint(self):
    ''' Fingerprint tuple format: (class name, dpid, controller id) '''
    return (self.__class__.__name__,
            self.dpid, self.controller_id)

  @staticmethod
  def from_json(json_hash):
    (label, time, round) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'dpid', 'controller_id')
    dpid = json_hash['dpid']
    controller_id = json_hash['controller_id']
    return ControlChannelUnblock(dpid, controller_id, round=round, label=label, time=time)

class DataplaneDrop(InputEvent):
  ''' Removes an in-flight dataplane packet with the given fingerprint from
  the network. '''
  def __init__(self, fingerprint, label=None, host_id=None, dpid=None, round=-1, time=None, passive=True):
    '''
    Parameters:
     - label: a unique label for this event. Internal event labels begin with 'i'
       and input event labels begin with 'e'.
     - host_id: unique integer label identifying the host that generated the
       packet. May be None.
     - dpid: unique integer identifier of the switch. May be None.
     - time: the timestamp of when this event occured. Stored as a tuple:
       [seconds since unix epoch, microseconds].
     - round: optional integer. Indicates what simulation round this event occured
       in.
     - passive: whether we're using Replayer.DataplaneChecker
    '''
    super(DataplaneDrop, self).__init__(label=label, round=round, time=time)
    # N.B. fingerprint is monkeypatched on to DpPacketOut events by BufferedPatchPanel
    if fingerprint[0] != self.__class__.__name__:
      fingerprint = list(fingerprint)
      fingerprint.insert(0, self.__class__.__name__)
    if type(fingerprint) == list:
      fingerprint = (fingerprint[0], DPFingerprint(fingerprint[1]),
                     fingerprint[2], fingerprint[3])
    self._fingerprint = fingerprint
    # TODO(cs): passive is a bit of a hack, but this was easier.
    self.passive = passive
    self.host_id = host_id
    self.dpid = dpid

  def proceed(self, simulation):
    # Handled by control_flow.replayer.DataplaneChecker
    if self.passive:
      return True
    else:
     dp_event = simulation.patch_panel.get_buffered_dp_event(self.fingerprint[1:])
     if dp_event is not None:
       simulation.patch_panel.drop_dp_event(dp_event)
       return True
     return False

  @property
  def fingerprint(self):
    ''' Fingerprint tuple format:
    (class name, DPFingerprint, switch dpid, port no)
    See fingerprints/messages.py for format of DPFingerprint.
    '''
    return self._fingerprint

  @property
  def dp_fingerprint(self):
    return self.fingerprint[1]

  @staticmethod
  def from_json(json_hash):
    (label, time, round) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'fingerprint')
    fingerprint = json_hash['fingerprint']
    return DataplaneDrop(fingerprint, round=round, label=label, time=time)

  def to_json(self):
    fields = dict(self.__dict__)
    fields['class'] = self.__class__.__name__
    fields['fingerprint'] = (self.fingerprint[0], self.fingerprint[1].to_dict(),
                             self.fingerprint[2], self.fingerprint[3])
    del fields['_fingerprint']
    return json.dumps(fields)

class BlockControllerPair(InputEvent):
  ''' '''
  def __init__(self, cid1, cid2, label=None, round=-1, time=None):
    super(BlockControllerPair, self).__init__(label=label, round=round, time=time)
    self.cid1 = cid1
    self.cid2 = cid2

  def proceed(self, simulation):
    # if there is a controller patch panel configured, us it, otherwise use
    # iptables.
    if simulation.controller_patch_panel is not None:
      simulation.controller_patch_panel.block_controller_pair(self.cid1, self.cid2)
    else:
      (c1, c2) = [ simulation.controller_manager.get_controller(cid)
                    for cid in [self.cid1, self.cid2] ]
      c1.block_peer(c2)
    return True

  @property
  def fingerprint(self):
    ''' Fingerprint tuple format:
    (class name, cid1, cid2)
    '''
    return (self.__class__.__name__, self.cid1, self.cid2)

  @staticmethod
  def from_json(json_hash):
    (label, time, round) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'cid1', 'cid2')
    cid1 = json_hash['cid1']
    cid2 = json_hash['cid2']
    return BlockControllerPair(cid1, cid2, round=round, label=label, time=time)

class UnblockControllerPair(InputEvent):
  def __init__(self, cid1, cid2, label=None, round=-1, time=None):
    super(UnblockControllerPair, self).__init__(label=label, round=round, time=time)
    self.cid1 = cid1
    self.cid2 = cid2

  def proceed(self, simulation):
    # if there is a controller patch panel configured, us it, otherwise use
    # iptables.
    if simulation.controller_patch_panel is not None:
      simulation.controller_patch_panel.unblock_controller_pair(self.cid1, self.cid2)
    else:
      (c1, c2) = [ simulation.controller_manager.get_controller(cid)
                    for cid in [self.cid1, self.cid2] ]
      c1.unblock_peer(c2)
    return True

  @property
  def fingerprint(self):
    ''' Fingerprint tuple format:
    (class name, cid1, cid2)
    '''
    return (self.__class__.__name__, self.cid1, self.cid2)

  @staticmethod
  def from_json(json_hash):
    (label, time, round) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'cid1', 'cid2')
    cid1 = json_hash['cid1']
    cid2 = json_hash['cid2']
    return UnblockControllerPair(cid1, cid2, round=round, label=label, time=time)

# TODO(cs): Temporary hack until we figure out determinism
class LinkDiscovery(InputEvent):
  ''' Deprecated '''
  def __init__(self, controller_id, link_attrs, label=None, round=-1, time=None):
    super(LinkDiscovery, self).__init__(label=label, round=round, time=time)
    self._fingerprint = (self.__class__.__name__,
                        controller_id, tuple(link_attrs))
    self.controller_id = controller_id
    self.link_attrs = link_attrs

  def proceed(self, simulation):
    controller = simulation.controller_manager.get_controller(self.controller_id)
    controller.sync_connection.send_link_notification(self.link_attrs)
    return True

  @property
  def fingerprint(self):
    return self._fingerprint

  @staticmethod
  def from_json(json_hash):
    (label, time, round) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'controller_id', 'link_attrs')
    controller_id = json_hash['controller_id']
    link_attrs = json_hash['link_attrs']
    return LinkDiscovery(controller_id, link_attrs, round=round, label=label, time=time)

all_input_events = [SwitchFailure, SwitchRecovery, LinkFailure, LinkRecovery,
                    ControllerFailure, ControllerRecovery, HostMigration,
                    PolicyChange, TrafficInjection, WaitTime, CheckInvariants,
                    ControlChannelBlock, ControlChannelUnblock,
                    DataplaneDrop, BlockControllerPair, UnblockControllerPair,
                    LinkDiscovery]

# ----------------------------------- #
#  Concrete classes of InternalEvents #
# ----------------------------------- #

def extract_base_fields(json_hash):
  (label, time, round) = extract_label_time(json_hash)
  timeout_disallowed = False
  if 'timeout_disallowed' in json_hash:
    timeout_disallowed = json_hash['timeout_disallowed']
  return (label, time, round, timeout_disallowed)

class ControlMessageBase(InternalEvent):
  '''
  Logged whenever an OpenFlowBuffer decides to allow a switch to receive or
  send an openflow packet.
  '''
  def __init__(self, dpid, controller_id, fingerprint, b64_packet="", label=None, round=-1, time=None, timeout_disallowed=False):
    '''
    Parameters:
     - dpid: unique integer identifier of the switch.
     - controller_id: unique string label for the controller.
     - b64_packet: base64 encoded packed openflow message.
     - label: a unique label for this event. Internal event labels begin with 'i'
       and input event labels begin with 'e'.
     - time: the timestamp of when this event occured. Stored as a tuple:
       [seconds since unix epoch, microseconds].
     - round: optional integer. Indicates what simulation round this event occured
       in.
     - timeout_disallowed: whether the replayer should wait indefinitely for
       this event to occur. Defaults to False.
    '''
    # If constructed directly (not from json), fingerprint is the
    # OFFingerprint, not including dpid and controller_id
    super(ControlMessageBase, self).__init__(label=label, round=round, time=time, timeout_disallowed=timeout_disallowed)
    self.dpid = dpid
    self.controller_id = controller_id
    self.b64_packet = b64_packet
    if type(fingerprint) == list:
      fingerprint = (fingerprint[0], OFFingerprint(fingerprint[1]),
                     fingerprint[2], tuple(fingerprint[3]))
    if type(fingerprint) == dict or type(fingerprint) != tuple:
      fingerprint = (self.__class__.__name__, OFFingerprint(fingerprint),
                     dpid, controller_id)

    self._fingerprint = fingerprint
    self.ignore_whitelisted_packets = False

  def get_packet(self):
    # Avoid serialization exceptions, but we still want to memoize.
    if not hasattr(self, "_packet"):
      self._packet = base64_decode_openflow(self.b64_packet)
    return self._packet

  @property
  def fingerprint(self):
    ''' Fingerprint tuple format:
    (class name, OFFingerprint, dpid, controller id)
    See fingerprints/messages.py for OFFingerprint format.
    '''
    return self._fingerprint

class ControlMessageReceive(ControlMessageBase):
  '''
  Logged whenever the GodScheduler decides to allow a switch to receive an
  openflow message.
  '''
  def proceed(self, simulation):
    pending_receive = self.pending_receive
    if self.ignore_whitelisted_packets and OpenFlowBuffer.in_whitelist(pending_receive.fingerprint):
      return True
    message_waiting = simulation.openflow_buffer.message_receipt_waiting(pending_receive)
    if message_waiting:
      simulation.openflow_buffer.schedule(pending_receive)
      return True
    return False

  @property
  def pending_receive(self):
    # TODO(cs): inefficient to keep reconrstructing this tuple.
    return PendingReceive(self.dpid, self.controller_id, self.fingerprint[1])

  def manually_inject(self, simulation):
    switch = simulation.topology.get_switch(self.dpid)
    conn = switch.get_connection(self.controller_id)
    conn.read(self.get_packet())

  def __str__(self):
    return "ControlMessageReceive:%s c %s -> s %s [%s]" % (self.label, self.controller_id, self.dpid, self.fingerprint[1].human_str())

  @staticmethod
  def from_json(json_hash):
    (label, time, round, timeout_disallowed) = extract_base_fields(json_hash)
    assert_fields_exist(json_hash, 'dpid', 'controller_id', 'fingerprint')
    dpid = json_hash['dpid']
    controller_id = json_hash['controller_id']
    fingerprint = json_hash['fingerprint']
    b64_packet = ""
    if 'b64_packet' in json_hash:
      b64_packet = json_hash['b64_packet']
    return ControlMessageReceive(dpid, controller_id, fingerprint, b64_packet=b64_packet,
                                 round=round, label=label, time=time, timeout_disallowed=timeout_disallowed)

class ControlMessageSend(ControlMessageBase):
  '''
  Logged whenever the GodScheduler decides to allow a switch to send an
  openflow message.
  '''
  def proceed(self, simulation):
    pending_send = self.pending_send
    if self.ignore_whitelisted_packets and OpenFlowBuffer.in_whitelist(pending_send.fingerprint):
      return True
    message_waiting = simulation.openflow_buffer.message_send_waiting(pending_send)
    if message_waiting:
      simulation.openflow_buffer.schedule(pending_send)
      return True
    return False

  @property
  def pending_send(self):
    # TODO(cs): inefficient to keep reconrstructing this tuple.
    return PendingSend(self.dpid, self.controller_id, self.fingerprint[1])

  def __str__(self):
    return "ControlMessageSend:%s c %s -> s %s [%s]" % (self.label, self.dpid, self.controller_id, self.fingerprint[1].human_str())

  @staticmethod
  def from_json(json_hash):
    (label, time, round, timeout_disallowed) = extract_base_fields(json_hash)
    assert_fields_exist(json_hash, 'dpid', 'controller_id', 'fingerprint')
    dpid = json_hash['dpid']
    controller_id = json_hash['controller_id']
    fingerprint = json_hash['fingerprint']
    b64_packet = ""
    if 'b64_packet' in json_hash:
      b64_packet = json_hash['b64_packet']
    return ControlMessageSend(dpid, controller_id, fingerprint, round=round,
                              b64_packet=b64_packet, label=label, time=time,
                              timeout_disallowed=timeout_disallowed)

# TODO(cs): move me?
class PendingStateChange(namedtuple('PendingStateChange',
                                ['controller_id', 'time', 'fingerprint',
                                 'name', 'value'])):
  def __new__(cls, controller_id, time, fingerprint, name, value):
    controller_id = controller_id
    if type(time) == list:
      time = tuple(time)
    if type(fingerprint) == list:
      fingerprint = tuple(fingerprint)
    if type(value) == list:
      value = tuple(value)
    return super(cls, PendingStateChange).__new__(cls, controller_id, time,
                                                  fingerprint, name, value)

  def _get_regex(self):
    # TODO(cs): if we add varargs to the signature, this needs to be changed
    if type(self.fingerprint) == tuple:
      # Skip over the class name
      return self.fingerprint[1]
    return self.fingerprint

  def __hash__(self):
    # TODO(cs): may need to add more context into the fingerprint to avoid
    # ambiguity
    return self._get_regex().__hash__() + self.controller_id.__hash__()

  def __eq__(self, other):
    if type(other) != type(self):
      return False
    return (self._get_regex() == other._get_regex() and
            self.controller_id == other.controller_id)

  def __ne__(self, other):
    # NOTE: __ne__ in python does *NOT* by default delegate to eq
    return not self.__eq__(other)


class ControllerStateChange(InternalEvent):
  '''
  Logged for any (visible) state change in the controller (e.g.
  mastership change). Visibility into controller state changes is obtained
  via syncproto.
  '''
  def __init__(self, controller_id, fingerprint, name, value, label=None, round=-1, time=None, timeout_disallowed=False):
    '''
    Parameters:
     - controller_id: unique string label for the controller.
     - name: The format string passed to the controller's logging library.
     - value: An array of values for the format string.
     - label: a unique label for this event. Internal event labels begin with 'i'
       and input event labels begin with 'e'.
     - time: the timestamp of when this event occured. Stored as a tuple:
       [seconds since unix epoch, microseconds].
     - round: optional integer. Indicates what simulation round this event occured
       in.
     - timeout_disallowed: whether the replayer should wait indefinitely for
       this event to occur. Defaults to False.
    '''
    super(ControllerStateChange, self).__init__(label=label, round=round, time=time, timeout_disallowed=timeout_disallowed)
    self.controller_id = controller_id
    if type(fingerprint) == str or type(fingerprint) == unicode:
      fingerprint = (self.__class__.__name__, fingerprint)
    if type(fingerprint) == list:
      fingerprint = tuple(fingerprint)
    self._fingerprint = fingerprint
    self.name = name
    if type(value) == list:
      value = tuple(value)
    self.value = value

  def proceed(self, simulation):
    observed_yet = simulation.controller_sync_callback\
                             .state_change_pending(self.pending_state_change)
    if observed_yet:
      simulation.controller_sync_callback\
                .ack_pending_state_change(self.pending_state_change)
      return True
    return False

  @property
  def pending_state_change(self):
    return PendingStateChange(self.controller_id, self.time,
                              self._get_message_fingerprint(),
                              self.name, self.value)

  def _get_message_fingerprint(self):
    return self._fingerprint[1]

  @property
  def fingerprint(self):
    ''' Fingerprint tuple format:
    (class name, PendingStateChange.fingerprint, controller id)
    PendingStateChange.fingerprint is the format string passed to the
    controller's logging library (without interpolated values)
    '''
    # Somewhat confusing: the StateChange's fingerprint is self._fingerprint,
    # but the overall fingerprint of this event needs to include the controller
    # id
    return tuple(list(self._fingerprint) + [self.controller_id])

  @staticmethod
  def from_pending_state_change(state_change):
    return ControllerStateChange(state_change.controller_id,
            state_change.fingerprint, state_change.name, state_change.value,
            time=state_change.time)

  @staticmethod
  def from_json(json_hash):
    (label, time, round, timeout_disallowed) = extract_base_fields(json_hash)
    assert_fields_exist(json_hash, 'controller_id', 'fingerprint',
                        'name', 'value')
    controller_id = json_hash['controller_id']
    fingerprint = json_hash['fingerprint']
    name = json_hash['name']
    value = json_hash['value']
    return ControllerStateChange(controller_id, fingerprint, name, value,
                                 round=round, label=label, time=time,
                                 timeout_disallowed=timeout_disallowed)

class DeterministicValue(InternalEvent):
  '''
  Logged whenever the controller asks for a deterministic value (e.g.
  gettimeofday()
  '''
  def __init__(self, controller_id, name, value, label=None, round=-1, time=None, timeout_disallowed=False):
    '''
    Parameters:
     - controller_id: unique string label for the controller.
     - name: name of the DeterministicValue request, e.g. "gettimeofday"
     - value: the return value of the DeterministicValue request.
     - label: a unique label for this event. Internal event labels begin with 'i'
       and input event labels begin with 'e'.
     - time: the timestamp of when this event occured. Stored as a tuple:
       [seconds since unix epoch, microseconds].
     - round: optional integer. Indicates what simulation round this event occured
       in.
     - timeout_disallowed: whether the replayer should wait indefinitely for
       this event to occur. Defaults to False.
    '''
    super(DeterministicValue, self).__init__(label=label, round=round, time=time, timeout_disallowed=timeout_disallowed)
    self.controller_id = controller_id
    self.name = name
    if name == "gettimeofday":
      value = SyncTime(seconds=value[0], microSeconds=value[1])
    elif type(value) == list:
      value = tuple(value)
    self.value = value

  def proceed(self, simulation):
    if simulation.controller_sync_callback\
                 .pending_deterministic_value_request(self.controller_id):
      simulation.controller_sync_callback.send_deterministic_value(self.controller_id,
                                                                   self.value)
      return True
    return False

  @staticmethod
  def from_json(json_hash):
    (label, time, round, timeout_disallowed) = extract_base_fields(json_hash)
    assert_fields_exist(json_hash, 'controller_id',
                        'name', 'value')
    controller_id = json_hash['controller_id']
    name = json_hash['name']
    value = json_hash['value']
    return DeterministicValue(controller_id, name, value, round=round,
                              label=label, time=time, timeout_disallowed=timeout_disallowed)

# TODO(cs): this should really be an input event. But need to make sure that
# it can be pruned safely
class ConnectToControllers(InternalEvent):
  ''' Logged at the beginning of the execution. Causes all switches to open
  TCP connections their their parent controller(s).
  '''
  def proceed(self, simulation):
    simulation.connect_to_controllers()
    return True

  @staticmethod
  def from_json(json_hash):
    (label, time, round, timeout_disallowed) = extract_base_fields(json_hash)
    return ConnectToControllers(label=label, time=time, round=round,
                                timeout_disallowed=timeout_disallowed)

class DataplanePermit(InternalEvent):
  ''' DataplanePermit allows a packet to move from one port to another in the
  dataplane. We basically just keep this around for bookkeeping purposes. During
  replay, this let's us know which packets to let through, and which to drop.
  '''
  def __init__(self, fingerprint, label=None, round=-1, time=None,
               passive=True):
    '''
    Parameters:
     - label: a unique label for this event. Internal event labels begin with 'i'
       and input event labels begin with 'e'.
     - time: the timestamp of when this event occured. Stored as a tuple:
       [seconds since unix epoch, microseconds].
     - round: optional integer. Indicates what simulation round this event occured
       in.
     - passive: whether we're using Replayer.DataplaneChecker
    '''
    # N.B. fingerprint is monkeypatched onto DpPacketOut events by
    # BufferedPatchPanel
    super(DataplanePermit, self).__init__(label=label, round=round, time=time, )
    if fingerprint[0] != self.__class__.__name__:
      fingerprint = list(fingerprint)
      fingerprint.insert(0, self.__class__.__name__)
    if type(fingerprint) == list:
      fingerprint = (fingerprint[0], DPFingerprint(fingerprint[1]),
                     fingerprint[2], fingerprint[3])
    self._fingerprint = fingerprint
    # TODO(cs): passive is a bit of a hack, but this was easier.
    self.passive = passive

  def proceed(self, simulation):
    if self.passive:
      return True
    else:
      dp_event = simulation.patch_panel.get_buffered_dp_event(self.fingerprint[1:])
      if dp_event is not None:
        simulation.patch_panel.permit_dp_event(dp_event)
        return True
      return False

  @property
  def fingerprint(self):
    ''' Fingerprint tuple format:
    (class name, DPFingerprint, switch dpid, port no)
    See fingerprints/messages.py for format of DPFingerprint.
    '''
    return self._fingerprint

  @property
  def dp_fingerprint(self):
    return self.fingerprint[1]

  @staticmethod
  def from_json(json_hash):
    (label, time, round) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'fingerprint')
    fingerprint = json_hash['fingerprint']
    return DataplanePermit(fingerprint, label=label, round=round, time=time)

  def to_json(self):
    fields = dict(self.__dict__)
    fields['class'] = self.__class__.__name__
    fields['fingerprint'] = (self.fingerprint[0], self.fingerprint[1].to_dict(),
                             self.fingerprint[2], self.fingerprint[3])
    del fields['_fingerprint']
    return json.dumps(fields)

class ProcessFlowMod(ControlMessageBase):
  ''' Logged whenever the network-wide OpenFlowBuffer decides to allow buffered (local
  to each switch) OpenFlow FlowMod message through and be processed by the switch '''
  # TODO(jl): Update visualization tool to recognize this replay event

  def proceed(self, simulation):
    switch = simulation.topology.get_switch(self.dpid)
    message_waiting = switch.openflow_buffer.message_receipt_waiting(self.pending_receive)
    if message_waiting:
      switch.openflow_buffer.schedule(self.pending_receive)
      return True
    return False

  @property
  def pending_receive(self):
    # TODO(cs): inefficient to keep reconrstructing this tuple.
    return PendingReceive(self.dpid, self.controller_id, self.fingerprint[1])

  @staticmethod
  def from_json(json_hash):
    (label, time, round, timeout_disallowed) = extract_base_fields(json_hash)
    assert_fields_exist(json_hash, 'dpid', 'controller_id', 'fingerprint')
    dpid = json_hash['dpid']
    controller_id = json_hash['controller_id']
    fingerprint = json_hash['fingerprint']
    b64_packet = ""
    if 'b64_packet' in json_hash:
      b64_packet = json_hash['b64_packet']
    return ProcessFlowMod(dpid, controller_id, fingerprint, b64_packet=b64_packet,
                          round=round, label=label, time=time,
                          timeout_disallowed=timeout_disallowed)

  def __str__(self):
    return "ProcessFlowMod:%s c %s -> s %s [%s]" % (self.label, self.controller_id, self.dpid, self.fingerprint[1].human_str())

all_internal_events = [ControlMessageReceive, ControlMessageSend,
                       ConnectToControllers, ControllerStateChange,
                       DeterministicValue, DataplanePermit, ProcessFlowMod]

# Special events:

class SpecialEvent(Event):
  def proceed(self, _):
    raise RuntimeError("Should never be called!")

class InvariantViolation(SpecialEvent):
  ''' Class for logging violations as json dicts '''
  def __init__(self, violations, label=None, round=-1, time=None, persistent=False):
    '''
    Parameters:
     - violations: an array of strings specifying the invariant violation
       fingerprints. Format of the strings depends on the invariant check.
       Empty array means there were no violations.
     - label: a unique label for this event. Internal event labels begin with 'i'
       and input event labels begin with 'e'.
     - time: the timestamp of when this event occured. Stored as a tuple:
       [seconds since unix epoch, microseconds].
     - round: optional integer. Indicates what simulation round this event occured
       in.
    '''
    Event.__init__(self, label=label, round=round, time=time)
    if len(violations) == 0:
      raise ValueError("Must have at least one violation string")
    self.violations = [ str(v) for v in violations ]
    self.persistent = persistent

  @staticmethod
  def from_json(json_hash):
    (label, time, round) = extract_label_time(json_hash)
    assert_fields_exist(json_hash, 'violations', 'persistent')
    violations = json_hash['violations']
    persistent = json_hash['persistent']
    return InvariantViolation(violations, label=label, round=round, time=time, persistent=persistent)

all_special_events = [InvariantViolation]

all_events = all_input_events + all_internal_events + all_special_events

dp_events = set([DataplanePermit, DataplaneDrop])
