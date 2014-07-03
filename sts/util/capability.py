# Copyright 2014      Ahmed El-Hassany
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

"""
Helper class to create specific Capabilities classes.

A capabilities class contains a set of properties, the name of each property
starts with 'can_' and then the capability name. For example: can_add_x,
can_remove_x, can_create_x, etc...
"""

import inspect


class Capabilities(object):
  """
  Expresses a simple capabilities of what can/cannot it be do done by a given object.

  This parent class is very simple and only provides basic functionality to
  set a collection of policies in one call.
  """
  def __init__(self):
    super(Capabilities, self).__init__()

  def set_create_policy(self, policy):
    """Helper method to change capabilities for everything that can be created."""
    for name, _ in inspect.getmembers(self,
                                          lambda a: not inspect.isroutine(a)):
      if name.startswith('can_create') and not hasattr(self, '_' + name):
        setattr(self, name, policy)
      elif name.startswith('_can_create'):
        setattr(self, name, policy)

  def set_add_policy(self, policy):
    """Helper method to change capabilities for everything that can be added."""
    for name, _ in inspect.getmembers(self,
                                          lambda a: not inspect.isroutine(a)):
      if name.startswith('can_add') and not hasattr(self, '_' + name):
        setattr(self, name, policy)
      elif name.startswith('_can_add'):
        setattr(self, name, policy)

  def set_remove_policy(self, policy):
    """Helper method to change capabilities for everything that can be removed."""
    for name, _ in inspect.getmembers(self,
                                          lambda a: not inspect.isroutine(a)):
      if name.startswith('can_remove') and not hasattr(self, '_' + name):
        setattr(self, name, policy)
      elif name.startswith('_can_remove'):
        setattr(self, name, policy)

  def to_json(self):
    """Returns a dict of the policies and its values"""
    policy = {}
    for name, _ in inspect.getmembers(self,
                                        lambda a: not inspect.isroutine(a)):
      if name.startswith('can_'):
        policy[name] = getattr(self, name)
    return policy
