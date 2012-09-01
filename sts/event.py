'''
Classes for tracking replayed events.

Author: sw
'''

import abc

class EventDag(object):
  '''A collection of Event objects. EventDags are primarily used to present a
  view of the underlying events with one external event and all of its
  dependent internal events pruned (see events())
  '''
  def __init__(self, events):
    '''events is a list of EventWatcher objects. Refer to log_parser.parse to
    see how this is assembled.'''
    self.events = events

  def events(self, pruned_event=None):
    '''Return a generator of the events in the DAG with pruned_event and all of its
    internal dependents pruned'''
    if pruned_event is None:
      assert(isinstance(pruned_event,InputEvent))
      pruned_events = set(pruned_event.dependent_events)
      pruned_events.add(pruned_event)
      should_yield = lambda event: event not in pruned_events
    else:
      should_yield = lambda x: True

    for event in self.events:
      if should_yield(event):
        yield event

class EventWatcher(object):
  '''EventWatchers watch events. This class can be used to wrap either
  InternalEvents or ExternalEvents to perform pre and post functionality.'''

  def __init__(self, event):
    self.event = event

  def run(self, simulation):
    self._pre()

    while not self.event.proceed(simulation):
      pass

    self._post()

  def _pre(self):
    pass

  def _post(self):
    pass

class Event(object):
  __metaclass__ = abc.ABCMeta

  def __init__(self, json_hash):
   assert('label' in json_hash)
   assert('class' in json_hash)

  # TODO(cs): uncomment me
  #@abc.abstractmethod
  def proceed(self, simulation):
    '''Returns a boolean that is true if the Replayer may continue to the next round.'''
    pass

# -------------------------------------------------------- #
# Semi-abstract classes for internal and external events   #
# -------------------------------------------------------- #

class InternalEvent(Event):
  '''An InternalEvent is one that happens within the controller(s) under
  simulation. Derivatives of this class verify that the internal event has
  occured in its proceed method before it returns.'''
  def __init__(self, json_hash):
    super(InternalEvent, self).__init__(json_hash)
    # TODO(sw): fingerprinting! this is why we need a separate class for internal events!

class InputEvent(Event):
  '''An event that the simulator injects into the simulation. These events are
  assumed to be causally independent.

  Each InputEvent has a list of dependent InternalEvents that it takes in its
  constructor. This enables the pruning of events.'''
  def __init__(self, json_hash):
    super(InputEvent, self).__init__(json_hash)
    assert('dependent_labels' in json_hash)
    self.dependent_labels = json_hash['dependent_labels']

# --------------------------------- #
#  Concrete classes of InputEvents  #
# --------------------------------- #

def assert_switch(json_hash):
  assert('dpid' in json_hash)

def assert_link(json_hash):
  assert('dpid' in json_hash)
  assert('port_no' in json_hash)

def assert_controller(json_hash):
  assert('uuid' in json_hash)

class SwitchFailure(InputEvent):
  def __init__(self, json_hash):
    super(InputEvent, self).__init__(json_hash)
    assert_switch(json_hash)

class SwitchRecovery(InputEvent):
  def __init__(self, json_hash):
    super(InputEvent, self).__init__(json_hash)
    assert_switch(json_hash)

class LinkFailure(InputEvent):
  def __init__(self, json_hash):
    super(InputEvent, self).__init__(json_hash)
    assert_link(json_hash)

class LinkRecovery(InputEvent):
  def __init__(self, json_hash):
    super(InputEvent, self).__init__(json_hash)
    assert_link(json_hash)

class ControllerFailure(InputEvent):
  def __init__(self, json_hash):
    super(InputEvent, self).__init__(json_hash)
    assert_controller(json_hash)

class ControllerRecovery(InputEvent):
  def __init__(self, json_hash):
    super(InputEvent, self).__init__(json_hash)
    assert_controller(json_hash)

class HostMigration(InputEvent):
  def __init__(self, json_hash):
    super(InputEvent, self).__init__(json_hash)
    assert('old_ingress_dpid' in json_hash)
    assert('old_ingress_port_no' in json_hash)
    assert('new_ingress_dpid' in json_hash)
    assert('new_ingress_port_no' in json_hash)

class PolicyChange(InputEvent):
  def __init__(self, json_hash):
    super(InputEvent, self).__init__(json_hash)
    assert('request_type' in json_hash)

all_input_events = [SwitchFailure, SwitchRecovery, LinkFailure, LinkRecovery,
                    ControllerFailure, ControllerRecovery, HostMigration,
                    PolicyChange]

# ----------------------------------- #
#  Concrete classes of InternalEvents #
# ----------------------------------- #

class MastershipChange(InternalEvent):
  def __init__(self, json_hash):
    super(InternalEvent, self).__init__(json_hash)

class TimerEvent(InternalEvent):
  def __init__(self, json_hash):
    super(InternalEvent, self).__init__(json_hash)

all_internal_events = [MastershipChange, TimerEvent]
