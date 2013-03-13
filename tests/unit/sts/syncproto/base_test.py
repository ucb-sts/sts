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
import os
import itertools
from copy import copy
import types
import tempfile

from sts.syncproto.base import SyncMessage, SyncTime, SyncProtocolSpeaker

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
