#!/usr/bin/python

from debugger.debugger import FuzzTester
from debugger.deferred_io import DeferredIOWorker
import debugger.topology_generator as default_topology
from pox.lib.ioworker.io_worker import RecocoIOLoop
from debugger.experiment_config_lib import Controller
from pox.lib.recoco.recoco import Scheduler

import signal
import sys
import string
import subprocess
import argparse
import logging
logging.basicConfig(level=logging.DEBUG)

# We use python as our DSL for specifying experiment configuration  
# The module can define the following functions:
#   controllers(command_line_args=[]) => returns a list of pox.debugger.experiment_config_info.ControllerInfo objects
#   switches()                        => returns a list of pox.debugger.experiment_config_info.Switch objects

# TODO: merge with Mininet
parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
             description="Run a debugger experiment.\n"+
                "Note: must precede controller args with --\n"+
                "Example usage:\n"+
                "$ %s -- ./pox/pox.py --no-cli openflow.of_01 --address=__address__ --port=__port__" % (sys.argv[0]) )
parser.add_argument("--config_file", help='optional experiment config file to load')
parser.add_argument('controller_args', metavar='controller arg', nargs='*',
                   help='arguments to pass to the controller(s)')
args = parser.parse_args()
  
if args.config_file:
  config = __import__(args.config_file)
else:
  config = object()

if hasattr(config, 'controllers'):
  controllers = config.controllers(args.controller_args)
else:
  controllers = [Controller(args.controller_args)]

child_processes = []
scheduler = None
def kill_children(signal, frame):
  global child_processes
  global scheduler

  print >> sys.stderr, "Caught signal %d, stopping sdndebug" % signal
  print >> sys.stderr, "Killing child controllers..."
  for child in child_processes:
    # SIGTERM for now
    child.terminate()
  print >> sys.stderr, "Stopping Recoco Scheduler..."
  if scheduler:
      scheduler.quit()
  sys.exit(0)

signal.signal(signal.SIGINT, kill_children)
signal.signal(signal.SIGTERM, kill_children)

# Boot the controllers
for c in controllers:
  command_line_args = map(lambda(x): string.replace(x, "__port__", str(c.port)),
                      map(lambda(x): string.replace(x, "__address__", str(c.address)), c.cmdline))
  print command_line_args
  child = subprocess.Popen(command_line_args)
  child_processes.append(child)
  
io_loop = RecocoIOLoop()

#if hasattr(config, 'switches'):
#  switches = config.switches()
#else:
#  switches = []
# HACK
create_worker = lambda(socket): DeferredIOWorker(io_loop.create_worker_for_socket(socket))

(panel, switch_impls) = default_topology.populate(controllers,
                                                   create_worker,
                                                   io_loop.remove_worker,
                                                   num_switches=1)
  
scheduler = Scheduler(daemon=True)
scheduler.schedule(io_loop)

# TODO: allow user to configure the fuzzer parameters, e.g. drop rate
debugger = FuzzTester(child_processes)
debugger.start(panel, switch_impls)
