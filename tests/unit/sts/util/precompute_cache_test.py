#!/usr/bin/env python

import unittest
import sys
import os.path
import itertools
from copy import copy
import types

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

