'''
Classes for tracking replayed events.

Author: sw
'''

import abc

class EventWatcher(object):
  '''EventWatchers watch events. This class can be used to wrap either
  InternalEvents or ExternalEvents to do pre and post functionality.'''

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

  def __init__(self, event_id):
    self.event_id = event_id

  @abc.abstractmethod
  def proceed(self, simulation):
    '''Returns a boolean that is true if the Replayer may continue to the next round.'''
    pass

# TODO(sw): box this comment!
# Semi-abstract classes for internal and external events

class InternalEvent(Event):
  '''An InternalEvent is one that happens within the controller(s) under
  simulation. Derivatives of this class verify that the internal event has
  occured in its proceed method before it returns.'''

  # TODO(sw): fingerprinting! this is why we need a separate class for internal events!
  pass

class InputEvent(Event):
   '''An event that the simulator injects into the simulation. These events are
   assumed to be causally independent.

   Each InputEvent has a list of dependent InternalEvents that it takes in its
  constructor. This enables the pruning of events.'''
  def __init__(self, event_id, dependent_events):
    super(InputEvent, self).__init__(event_id)
    self.dependent_events = dependent_events

class Event_DAG(object): # TODO(sw): change to CamelCase
  '''A set of events that have a total order (e.g. a list).'''
  def __init__(self, events):
    '''events is a list of EventWatcher objects. Refer to log_parser.parse to
    see how this is assembled.'''
    self.events = events

  def events(self, pruned_event=None):
    if pruned_event is None:
      assert(isinstance(pruned_event,InputEvent))
      pruned_events = set(pruned_event.dependant_events)
      pruned_events.add(pruned_event)
      should_yield = lambda event: event not in pruned_events
    else:
      should_yield = lambda x: True

    for event in self.events:
      if should_yield(event):
        yield event

# TODO(sw): box this comment!
# Concrete classes of InputEvents

class SwitchFailure(InputEvent):
  def __init__(self, event_id, dependent_events, dpid):
    InputEvent.__init__(event_id, dependent_events)

class SwitchRecovery(InputEvent):
  def __init__(self, event_id, dependent_events, dpid):
    InputEvent.__init__(event_id, dependent_events)

class LinkFailure(InputEvent):
  def __init__(self, event_id, dependent_events, dpid, port_no):
    InputEvent.__init__(event_id, dependent_events)

class LinkRecovery(InputEvent):
  def __init__(self, event_id, dependent_events, dpid, port_no):
    InputEvent.__init__(event_id, dependent_events)

class ControllerFailure(InputEvent):
  def __init__(self, event_id, dependent_events, pid):
    InputEvent.__init__(event_id, dependent_events)

class ControllerRecovery(InputEvent):
  def __init__(self, event_id, dependent_events, pid):
    InputEvent.__init__(event_id, dependent_events)

class HostMigration(InputEvent):
  pass

class PolicyChange(InputEvent):
  pass

all_input_events = [SwitchFailure, SwitchRecovery, LinkFailure, LinkRecovery,
                    ControllerFailure, ControllerRecover, HostMigration,
                    PolicyChange]

# Concrete classes of InternalEvents
class MastershipChange(InternalEvent):
  pass

class TimerEvent(InternalEvent):
  pass

all_internal_events = [MastershipChange, TimerEvent]
