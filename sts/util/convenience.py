# Copyright 2011-2013 Colin Scott
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

import time

def is_sorted(l):
  return all(l[i] <= l[i+1] for i in xrange(len(l)-1))

def is_strictly_sorted(l):
  return all(l[i] < l[i+1] for i in xrange(len(l)-1))

def timestamp_string():
  return time.strftime("%Y_%m_%d_%H_%M_%S", time.localtime())

def find(f, seq):
  """Return first item in sequence where f(item) == True."""
  for item in seq:
    if f(item):
      return item

def find_index(f, seq):
  """Return the index of the first item in sequence where f(item) == True."""
  for index, item in enumerate(seq):
    if f(item):
      return index


def check_heap(max_kB=3.0*10**6):
  ''' If we're using more than max kB of RAM, pop into an interactive
  shell. Note: assumes linux.

  Great for tracking down memory leaks. See:
      http://www.smira.ru/wp-content/uploads/2011/08/heapy.html'''
  mem_usage = 0
  with open("/proc/self/status") as proc:
    for line in proc.readlines():
      if line.startswith("VmHWM"):
        mem_usage = int(line.split()[1])

  if mem_usage > max_kB:
    print "Entering Console..."
    from guppy import hpy
    hp = hpy()
    h = hp.heap()
    import code
    code.interact(local=locals())
