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

import unittest
import sys
import os.path

sys.path.append(os.path.dirname(__file__) + "/../../..")

from sts.util.precompute_cache import *

class precompute_cache_test(unittest.TestCase):

  def test_simple(self):
    p = PrecomputeCache()
    p.update( (1,2,3) )
    self.assertTrue(p.already_done( (1,2,3)))
    self.assertFalse(p.already_done( (1,2)))
    self.assertFalse(p.already_done( (1,)))
    p.update( (1,2) )
    self.assertTrue(p.already_done( (1,2,3)))
    self.assertTrue(p.already_done( (1,2)))
    self.assertFalse(p.already_done( (1,)))
    self.assertFalse(p.already_done( (1,2,3,4)))

  def test_power(self):
    p = PrecomputePowerSetCache()
    p.update( (1,2,3) )
    self.assertTrue(p.already_done( (1,2,3)))
    self.assertTrue(p.already_done( (1,2)))
    self.assertTrue(p.already_done( (1,)))
    self.assertTrue(p.already_done( (2,3)))
    self.assertFalse(p.already_done( (1,2,3,4)))
    self.assertFalse(p.already_done( (1,2,4)))
    p.update( (1,2) )
    self.assertTrue(p.already_done( (1,2,3)))
    self.assertTrue(p.already_done( (1,2)))
    self.assertTrue(p.already_done( (1,)))
    self.assertFalse(p.already_done( (1,2,3,4)))
    p.update( (3,4) )
    self.assertTrue(p.already_done( (1,2)))
    self.assertTrue(p.already_done( (3,4)))
    self.assertFalse(p.already_done( (2,4)))
    self.assertTrue(p.already_done( (4,)))
    self.assertFalse(p.already_done( (1,2,3,4)))

