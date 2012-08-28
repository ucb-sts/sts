'''
Classes for tracking replayed events.

Author: sw
'''

import abc

class EventWatcher(object): # TODO(sw): docstrings for class
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

class InternalEvent(Event):
  # TODO(sw): docstring
  # TODO(sw): fingerprinting! this is why we need a separate class for internal events!
  pass

class ExternalEvent(Event):
   # TODO(sw): docstring
  def __init__(self, event_id, dependent_events):
    super(ExternalEvent, self).__init__(event_id)
    self.dependent_events = dependent_events

class Event_DAG(object):
  # TODO(sw): docstring
  def __init__(self, events):
    # TODO(sw): docstring
    self.events = events # events is just a list of EventWatcher objecs

  def events(self, pruned_event=None):
    if pruned_event is None:
      assert(isinstance(pruned_event,ExternalEvent))
      pruned_events = set(pruned_event.dependant_events)
      pruned_events.add(pruned_event)
      should_yield = lambda event: event not in pruned_events
    else:
      should_yield = lambda x: True

    for event in self.events:
      if should_yield(event):
        yield event
