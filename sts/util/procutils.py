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

import subprocess
import threading
import os
import sys
import time
import traceback

from sts.util.console import color

def split_up(f, l):
  trues = []
  falses = []
  for elem in l:
    if(f(elem)):
      trues.append(elem)
    else:
      falses.append(elem)
  return (trues, falses)

def kill_procs(child_processes, kill=None, verbose=True, timeout=5,
               close_fds=True):
  child_processes = filter(lambda e: e is not None, child_processes)
  def msg(msg):
    if(verbose):
      sys.stderr.write(msg)

  if kill == None:
    if hasattr(kill_procs,"already_run"):
      kill = True
    else:
      kill = False
      kill_procs.already_run = True

  if len(child_processes) == 0:
    return

  msg("%s child controllers..." % ("Killing" if kill else "Terminating"))
  for child in child_processes:
    if kill:
      child.kill()
    else:
      child.terminate()

  start_time = time.time()
  last_dot = start_time
  all_dead = []
  while True:
    (child_processes, new_dead) = split_up(lambda child: child.poll() is None, child_processes)
    all_dead += new_dead
    if len(child_processes) == 0:
      break
    if hasattr(time, "_orig_sleep"):
      time._orig_sleep(0.1)
    else:
      time.sleep(0.1)
    now = time.time()
    if (now - last_dot) > 1:
      msg(".")
      last_dot = now
    if (now - start_time) > timeout:
      if kill:
        break
      else:
        msg(' FAILED (timeout)!\n')
        kill_procs(child_processes, kill=True)
        break

  if close_fds:
    for child in all_dead:
      for attr_name in "stdin", "stdout", "stderr":
        if hasattr(child, attr_name):
          try:
            attr = getattr(child, attr_name)
            if attr:
              attr.close()
          except IOError:
            msg("close() called on %s during concurrent operation\n" % attr_name)
          except:
            msg("Error closing child io.\n")
            tb = traceback.format_exc()
            msg(tb)

  if len(child_processes) == 0:
    msg(' OK\n')

printlock = threading.Lock()
def _prefix_thread(f, func):
  def run():
    while not f.closed:
      line = f.readline()
      if not line:
        break
      with printlock:
        print func(line)
    try:
      sys.stderr.write("Closing fd %d\n" % f)
      f.close() # idempotent, in case the f.closed broke out of the while loop
    except:
      # well, we tried
      pass
  t = threading.Thread(target=run)
  t.daemon = True
  t.start()
  return t

def popen_filtered(name, args, cwd=None, env=None, redirect_output=True,
                   shell=False):
  if shell and type(args) == list:
    args = ' '.join(args)
  try:
    cmd = subprocess.Popen(args, stdout=subprocess.PIPE, shell=shell,
                           stderr=subprocess.PIPE, stdin=sys.stdin, cwd=cwd, env=env,
                           preexec_fn=lambda: os.setsid())
  except OSError as e:
    raise OSError("Error launching %s in directory %s: %s (error %d)" % (args, cwd, e.strerror, e.errno))
  if redirect_output:
    cmd._stdout_thread = _prefix_thread(cmd.stdout, lambda l: "%s%s %s%s\n" % (color.YELLOW, name, l.rstrip(), color.NORMAL))
    cmd._stderr_thread = _prefix_thread(cmd.stderr, lambda l: "%s%s %s%s\n" % (color.B_RED + color.YELLOW, name, l.rstrip(), color.NORMAL))
  return cmd

