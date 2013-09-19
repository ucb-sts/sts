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

  def check_match(self, match):
    ''' Return whether this fingerprint matches the pattern in match.

    match must be of the form (key, value, nested_match), where key and value
    are members of self._field2value to match on, and nested_match is either
    None or a tuple (nest_key, match pattern) to match on recursively.

    This method differs from __eq__ in that it will return True if a
    subset (specified in match)  of fields are equal, whereas __eq__ requires
    every field to match.

    # TODO(cs): an arguably cleaner way to implement this would be to support
    # wildcarded fields in __eq__.
    '''
    (key, value, nested_match) = match
    if key not in self._field2value:
      return False
    if value != self._field2value[key]:
      return False
    if nested_match is None:
      return True
    (nested_key, match) = nested_match
    nested_fingerprint = self._field2value[nested_key]
    if nested_fingerprint == ():
      return True
    return nested_fingerprint.check_match(match)

  @abc.abstractmethod
  def __hash__(self):
    pass

  @abc.abstractmethod
  def __eq__(self, other):
    pass

  def __getitem__(self, key):
    return self._field2value[key]

  def __ne__(self, other):
    # NOTE: __ne__ in python does *NOT* by default delegate to eq
    return not self.__eq__(other)

  def __str__(self):
    return str(self._field2value)

  def __repr__(self):
    return self.__class__.__name__ + str(self._field2value)

