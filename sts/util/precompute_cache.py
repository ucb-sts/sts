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


