# Copyright 2011-2013 Colin Scott
# Copyright 2011-2013 Andi Wundsam 
# Copyright 2011-2013 Andrew Or
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

from sts.util.console import msg
import logging

log = logging.getLogger("violation_tracker")

class ViolationTracker(object):
  '''
  Tracks all violations and decides whether each one is transient or persistent
  '''

  def __init__(self, count_threshold=1):
    self.count_threshold = count_threshold
    self.violation2count = {}

  def register(self, violations):
    # First, unregister violations that expire
    for v in self.violation2count.keys():
      if v not in violations:
        msg.success("Violation %s turns out to be transient!" % v)
        del self.violation2count[v]
    # Now, register violations observed this round 
    for v in violations:
      if v in self.violation2count.keys():
        self.violation2count[v] += 1
      else:
        self.violation2count[v] = 1
      msg.fail("Violation encountered %d time(s): %s" % (self.violation2count[v], v))
 
  def is_persistent(self, violation):
    return self.violation2count[violation] >= self.count_threshold

  @property
  def persistent_violations(self):
    return [ v for v in self.violation2count.keys() if self.is_persistent(v) ]

