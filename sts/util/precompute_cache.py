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

from collections import defaultdict
import itertools

class PrecomputePowerSetCache(object):
  sequence_id = itertools.count(1)
  def __init__(self):
    self.element2id = defaultdict(lambda: set())
  def already_done(self, input_sequence):
    return len(reduce(lambda left, new: left & new if not left is None else new,
                 (self.element2id[elem] for elem in input_sequence ))
                 ) != 0

  def update(self, input_sequence):
    id = self.sequence_id.next()
    for elem in input_sequence:
      self.element2id[elem].add(id)

class PrecomputeCache(object):
  def __init__(self):
    self.done_sequences = set()
  def already_done(self, input_sequence):
    return input_sequence in self.done_sequences
  def update(self, input_sequence):
    self.done_sequences.add(input_sequence)


