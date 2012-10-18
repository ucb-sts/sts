import subprocess
import threading
import sys
import time

from sts.util.console import color

def kill_procs(child_processes, kill=None, verbose=True, timeout=5):
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
  while True:
    child_processes = [ child for child in child_processes if child.poll() is None ]
    if len(child_processes) == 0:
      break
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
        return kill_procs(child_processes, kill=True)
  msg(' OK\n')

printlock = threading.Lock()
def _prefix_thread(f, func):
  def run():
    while True:
      line = f.readline()
      if not line:
        break
      printlock.acquire()
      print func(line),
      printlock.release()
  t = threading.Thread(target=run)
  t.daemon = True
  t.start()

def popen_filtered(name, args, cwd=None, env=None):
  try:
    cmd = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, env=env)
  except OSError as e:
    raise OSError("Error launching %s in directory %s: %s (error %d)" % (args, cwd, e.strerror, e.errno))
  _prefix_thread(cmd.stdout, lambda l: "%s%s [%d] %s%s\n" % (color.YELLOW, name, cmd.pid, l.rstrip(), color.NORMAL))
  _prefix_thread(cmd.stderr, lambda l: "%s%s [%d] %s%s\n" % (color.B_RED + color.YELLOW, name, cmd.pid, l.rstrip(), color.NORMAL))
  return cmd
