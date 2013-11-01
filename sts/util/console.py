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

import sys

BEGIN = '\033[1;'
END = '\033[1;m'

class color(object):
  GRAY, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, CRIMSON = map(lambda num : BEGIN + str(num) + "m", range(30, 39))
  B_GRAY, B_RED, B_GREEN, B_YELLOW, B_BLUE, B_MAGENTA, B_CYAN, B_WHITE, B_CRIMSON =  map(lambda num: BEGIN + str(num) + "m", range(40, 49))
  NORMAL = END

class msg():
  global_io_master = None

  BEGIN = '\033[1;'
  END = '\033[1;m'

  GRAY, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, CRIMSON = map(lambda num: str(num) + "m", range(30, 39))
  B_BLACK, B_RED, B_GREEN, B_YELLOW, B_BLUE, B_MAGENTA, B_CYAN, B_GRAY, B_CRIMSON =  map(lambda num: str(num) + "m", range(40, 49))

  @staticmethod
  def interactive(message):
    # todo: would be nice to simply give logger a color arg, but that doesn't exist...
    print msg.BEGIN + msg.WHITE + message + msg.END

  @staticmethod
  def event(message):
    print msg.BEGIN + msg.CYAN + message + msg.END

  @staticmethod
  def openflow_event(message):
    print msg.BEGIN + msg.BLUE + message + msg.END

  @staticmethod
  def special_event(message):
    print msg.BEGIN + msg.MAGENTA + message + msg.END

  @staticmethod
  def replay_event_success(message):
    print msg.BEGIN + msg.CYAN + msg.BEGIN + msg.B_BLUE + message + msg.END

  @staticmethod
  def replay_event_timeout(message):
    print msg.BEGIN + msg.MAGENTA + msg.BEGIN + msg.B_RED + message + msg.END

  @staticmethod
  def mcs_event(message):
    print msg.BEGIN + msg.B_MAGENTA + message + msg.END

  @staticmethod
  def raw_input(message):
    prompt = msg.BEGIN + msg.WHITE + message + msg.END
    if msg.global_io_master:
      s = msg.global_io_master.raw_input(prompt)
    else:
      s = raw_input(prompt)

    if s == "debug":
      import pdb
      pdb.set_trace()
    return s

  @staticmethod
  def success(message):
    print msg.BEGIN + msg.B_GREEN + msg.BEGIN + msg.WHITE + message + msg.END

  @staticmethod
  def fail(message):
    print msg.BEGIN + msg.B_RED + msg.BEGIN + msg.WHITE + message + msg.END

  @staticmethod
  def set_io_master(io_master):
    msg.global_io_master = io_master

  @staticmethod
  def unset_io_master():
    msg.global_io_master = None

class Tee(object):
  def __init__(self, target):
    self.target = target
    self.orig_stdout = None
    self.orig_stderr = None

  def tee_src(self, src):
    _self = self
    class DoubleIO(object):
      def write(self, s):
        src.write(s)
        _self.target.write(s)
        _self.target.flush()
    return DoubleIO()

  def tee_stdout(self):
    self.orig_stdout = sys.stdout
    if not hasattr(sys, "_orig_stdout"):
      sys._orig_stdout = sys.stdout
    sys.stdout = self.tee_src(sys.stdout)

  def tee_stderr(self):
    self.orig_stderr = sys.stderr
    sys.stderr = self.tee_src(sys.stderr)

  def close(self):
    self.target.close()
    if self.orig_stdout:
      sys.stdout = self.orig_stdout
    if self.orig_stderr:
      sys.stderr = self.orig_stderr

