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


import inspect
import unittest

from sts.util.capability import Capabilities


class SimpleTestCapabilities(Capabilities):
  """
  Just a simple capabilities for testing purposes.
  """
  can_create_x = True
  can_add_x = True
  can_remove_x = True

  def __init__(self, can_create_x, can_create_y, can_add_x, can_add_y,
               can_remove_x, can_remove_y):
    super(SimpleTestCapabilities, self).__init__()
    self.can_create_x = can_create_x
    self._can_create_y = can_create_y
    self.can_add_x = can_add_x
    self._can_add_y = can_add_y
    self.can_remove_x = can_remove_x
    self._can_remove_y = can_remove_y

  @property
  def can_create_y(self):
    return self._can_create_y

  @property
  def can_add_y(self):
    return self._can_add_y

  @property
  def can_remove_y(self):
    return self._can_remove_y


class CapabilitiesTest(unittest.TestCase):
  def test_set_create_policy(self):
    # Arrange
    policy1 = SimpleTestCapabilities(True, True, True, True, True, True)
    policy2 = SimpleTestCapabilities(False, False, False, False, False, False)
    # Act
    policy1.set_create_policy(False)
    policy2.set_create_policy(False)
    # Assert
    self.assertFalse(policy1.can_create_x)
    self.assertFalse(policy1.can_create_y)
    self.assertFalse(policy2.can_create_x)
    self.assertFalse(policy2.can_create_y)

  def test_set_add_policy(self):
    # Arrange
    policy1 = SimpleTestCapabilities(True, True, True, True, True, True)
    policy2 = SimpleTestCapabilities(False, False, False, False, False, False)
    # Act
    policy1.set_add_policy(False)
    policy2.set_add_policy(False)
    # Assert
    self.assertFalse(policy1.can_add_x)
    self.assertFalse(policy1.can_add_y)
    self.assertFalse(policy2.can_add_x)
    self.assertFalse(policy2.can_add_y)

  def test_set_remove_policy(self):
    # Arrange
    policy1 = SimpleTestCapabilities(True, True, True, True, True, True)
    policy2 = SimpleTestCapabilities(False, False, False, False, False, False)
    # Act
    policy1.set_remove_policy(False)
    policy2.set_remove_policy(False)
    # Assert
    self.assertFalse(policy1.can_remove_x)
    self.assertFalse(policy1.can_remove_y)
    self.assertFalse(policy2.can_remove_x)
    self.assertFalse(policy2.can_remove_y)

  def test_to_json(self):
    # Arrange
    policy1 = SimpleTestCapabilities(True, True, True, True, True, True)
    policy2 = SimpleTestCapabilities(False, False, False, False, False, False)
    # Act
    json1 = policy1.to_json()
    json2 = policy2.to_json()
    # Assert
    print json1
    self.assertEquals(json1, dict(can_create_x=True, can_create_y=True,
                                  can_add_x=True, can_add_y=True,
                                  can_remove_x=True, can_remove_y=True))
    self.assertEquals(json2, dict(can_create_x=False, can_create_y=False,
                                  can_add_x=False, can_add_y=False,
                                  can_remove_x=False, can_remove_y=False))


class CapabilitiesGenericTest(unittest.TestCase):
  """
  This is a generic test case that can be extended to test specific Capabilities
  classes. Just need to override setUp to point to the right class.
  """
  def setUp(self):
    self._capabilities_cls = SimpleTestCapabilities

  def _get_properties(self, policy, default_value=True):
    """
    Returns a dict of the capabilities properties in capabilities and the value is
    set to the default_value.
    """
    properties_dict = {}
    for name, _ in inspect.getmembers(policy,
                                          lambda a: not inspect.isroutine(a)):
      if name.startswith('_'):
        continue
      properties_dict[name] = default_value
    print properties_dict
    return properties_dict

  def test_set_all_false(self):
    # Arrange
    properties_dict = self._get_properties(self._capabilities_cls, False)
    # Act
    policy = self._capabilities_cls(**properties_dict)
    # Assert
    for name in properties_dict:
      self.assertFalse(getattr(policy, name))

  def test_set_one_false(self):
    # Arrange
    properties_dict = self._get_properties(self._capabilities_cls, True)
    # Act
    for prop in properties_dict:
      new_properties = properties_dict.copy()
      new_properties[prop] = False
      policy = self._capabilities_cls(**new_properties)
      for name in properties_dict:
        if name == prop:
          self.assertFalse(getattr(policy, name), prop)
        else:
          self.assertTrue(getattr(policy, name), name)

  def test_set_one_true(self):
     # Arrange
    properties_dict = self._get_properties(self._capabilities_cls, False)
    # Act
    for prop in properties_dict:
      new_properties = properties_dict.copy()
      new_properties[prop] = True
      policy = self._capabilities_cls(**new_properties)
      for name in properties_dict:
        if name == prop:
          self.assertTrue(getattr(policy, name), prop)
        else:
          self.assertFalse(getattr(policy, name))
