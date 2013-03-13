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

from tests.unit.sts.sync_connection_test import MockIOWorker, SyncMessageTest
from sts.syncproto.base import SyncTime
from sts.syncproto.sts_syncer import STSSyncProtocolSpeaker

class MockStateMaster(object):
  def __init__(self):
    self.changes = []
  def state_change(self, controller, time, fingerprint, name, value):
    self.changes.append( (controller, time, fingerprint, name, value) )

sys.path.append(os.path.dirname(__file__) + "/../../..")

class STSSyncProtocolSpeakerTest(unittest.TestCase):
  def test_log_state_change(self):
    _eq = self.assertEquals
    h = SyncMessageTest.basic_hash

    state_master = MockStateMaster()
    worker = MockIOWorker()
    controller = "c1"
    speaker = STSSyncProtocolSpeaker(controller=controller, state_master=state_master, json_io_worker=worker)

    worker.receive(h)
    _eq(1, len(state_master.changes))
    _eq( (controller, SyncTime(**h['time']), h['fingerPrint'], h['name'], h['value']), state_master.changes[0])

if __name__ == '__main__':
  unittest.main()
