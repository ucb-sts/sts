import abc

# HACK(sam) most of this stuff can be done with partial functions. I'm just
# trying to make this understandable!

class ExternalEvent(object):
  __metaclass__ = abc.ABCMeta

  @abc.abstractmethod
  def inject(self): # TODO this needs more args from the topology
    '''Inject the effects of this external event into the simulation.'''
    pass

# things to subclass external event with: switch failure, controller failure, link failure

class InternalEvent(object):
  '''An internal event. This is an event that happens
  as a result of an external event. Simply, these are events that happen as a
  result of an external event being fed into the system. Right now this just
  depends on a single external event. In the future, it is feasible that
  external events.'''
  __metaclass__ = abc.ABCMeta

  def __init__(self, external_event):
    self.dependency = external_event

  def wait(self, external_events): # TODO this needs more arguments for later
    if self.dependency in external_events:
      self.operate()

  @abc.abstractmethod
  def operate(self):
    '''Check whether the internal event has happend already. This method may
    block until it is ready.'''
    pass
