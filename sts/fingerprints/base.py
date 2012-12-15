
import abc

class Fingerprint(object):
  __metaclass__ = abc.ABCMeta

  # This should really be a protected constructor
  def __init__(self, field2value):
    # Make sure to convert arrays to tuples, since we need __hash__()
    for field, value in field2value.iteritems():
      if type(value) == list:
        field2value[field] = tuple(value)
    self._field2value = field2value

  def to_dict(self):
    flattened = {}
    for field, value in self._field2value.iteritems():
      if 'to_dict' in dir(value):
        flattened[field] = value.to_dict()
      else:
        flattened[field] = value
    return flattened

  @abc.abstractmethod
  def __hash__(self):
    pass

  @abc.abstractmethod
  def __eq__(self, other):
    pass

  def __str__(self):
    return str(self._field2value)

  def __repr__(self):
    return self.__class__.__name__ + str(self._field2value)

