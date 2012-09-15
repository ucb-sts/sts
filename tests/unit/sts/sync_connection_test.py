#!/usr/bin/env python

import unittest
import sys
import os
import itertools
from copy import copy
import types
import tempfile

from sts.sync_connection import SyncMessage, SyncTime, SyncProtocolSpeaker

sys.path.append(os.path.dirname(__file__) + "/../../..")

class MockIOWorker(object):
  def __init__(self):
    self.sends = []
    self.on_json_received = None
  def send(self, msg):
    self.sends.append(msg)
  def receive(self, msg):
    self.on_json_received(self, msg)


class SyncTimeTest(unittest.TestCase):
  def test_basic(self):
    t = SyncTime(**{ "seconds": 1347830756, "microSeconds": 474865})

class SyncMessageTest(unittest.TestCase):
  basic_hash = {"name":"role","value":"MASTER","fingerPrint":"role=MASTER","type":"ASYNC",
        "time":{ "seconds": 1347830756,"microSeconds": 474865 },
        "xid":1,"messageClass":"StateChange" }

  def test_basic(self):
    m = SyncMessage(**self.basic_hash)

  def changed_hash(self, **changes):
    res = self.basic_hash.copy()
    res.update(changes)
    return res

  def test_invalid_hashes(self):
    for invalid_hash in (
        {},
        self.changed_hash(type="INVALID"),
        self.changed_hash(additionalInvalidAttribute="FOOBAR"),
        self.changed_hash(type=None),
        ):
      self.assertRaises(Exception, SyncMessage, **invalid_hash)

if __name__ == '__main__':
  unittest.main()
