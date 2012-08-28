#!/bin/bash -

# If you have PyPy 1.6+ in a directory called pypy alongside pox.py, we
# use it.
# Otherwise, we try to use a Python interpreter called python2.7, which
# is a good idea if you're using Python from MacPorts, for example.
# We fall back to just "python" and hope that works.

''''echo -n
export OPT="-O"
export FLG=""
if [[ "$(basename $0)" == "debug-pox.py" ]]; then
  export OPT=""
  export FLG="--debug"
fi

if [ -x pypy/bin/pypy ]; then
  exec pypy/bin/pypy $OPT "$0" $FLG "$@"
fi

if [ "$(type -P python2.7)" != "" ]; then
  exec python2.7 $OPT "$0" $FLG "$@"
fi
exec python $OPT "$0" $FLG "$@"
'''

from sts.deferred_io import DeferredIOWorker
from sts.procutils import kill_procs, popen_filtered

from sts.topology import FatTree
from sts.control_flow import Fuzzer
from pox.lib.ioworker.io_worker import RecocoIOLoop
from pox.lib.util import connect_socket_with_backoff
from sts.experiment_config_lib import Controller
from pox.lib.recoco.recoco import Scheduler

import signal
import sys
import string
import subprocess
import time
import argparse
import logging
logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger("sts")

# We use python as our DSL for specifying experiment configuration  
# The module must define the following attribute:
#   controllers    => a list of pox.sts.experiment_config_info.ControllerInfo objects
# The module can optionally define the following attributes:
#   topology       => a sts.topology.Topology object
#                                        defining the switches and links
#   patch_panel    => a sts.topology.PatchPanel class
#   control_flow   => a sts.control_flow.ControlModule class

description = """
Run a debugger experiment.
Example usage:

$ %s -c config/fat_tree.cfg
""" % (sys.argv[0])

parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                 description=description)

# TODO(cs): move the next two to config file
parser.add_argument("-l", "--snapshotport", type=int, metavar="snapshotport",
                    help="port to use for controllers for snapshotting", default=6634)

# Major TODO: need to type-check trace file (i.e., every host in the trace must be present in the network!)
#              this has already wasted several hours of time...
parser.add_argument("-t", "--trace-file", default=None,
                    help="optional dataplane trace file (see trace_generator.py)")

parser.add_argument("-c", "--config", required=True,
                    default="configs/fat_tree.cfg", help='experiment config file to load')

args = parser.parse_args()
config = __import__(args.config)

# For instrumenting the controller
# TODO(aw): This ugly hack has to be cleaned up ASAP ASAP
control_socket = None #connect_socket_with_backoff('', 6634)

if hasattr(config, 'controllers'):
  controllers = config.controllers
else:
  raise RuntimeError("Must specify controllers in config file")

if hasattr(config, 'patch_panel'):
  patch_panel_class = config.patch_panel
else:
  # We default to a BufferedPatchPanel
  patch_panel_class = BufferedPatchPanel

if hasattr(config, 'topology'):
  topology = config.topology(patch_panel_class)
else:
  # We default to a FatTree with 4 pods
  topology = FatTree(patch_panel_class)

if hasattr(config, 'control_flow'):
  simulator = config.control_flow(topology, control_socket)
else:
  # We default to a Fuzzer
  simulator = Fuzzer(topology, control_socket)

child_processes = []
scheduler = None
def kill_children():
  global child_processes
  kill_procs(child_processes)

def kill_scheduler():
  if scheduler and not scheduler._hasQuit:
    sys.stderr.write("Stopping Recoco Scheduler...")
    scheduler.quit()
    sys.stderr.write(" OK\n")

def handle_int(signal, frame):
  print >> sys.stderr, "Caught signal %d, stopping sdndebug" % signal
  kill_children()
  kill_scheduler()
  sys.exit(0)

signal.signal(signal.SIGINT, handle_int)
signal.signal(signal.SIGTERM, handle_int)

try:
  # Boot the controllers
  for (i, c) in enumerate(controllers):
    if c.needs_boot:
      command_line_args = map(lambda(x): string.replace(x, "__port__", str(c.port)),
                          map(lambda(x): string.replace(x, "__address__", str(c.address)), c.cmdline))
      print command_line_args
      child = popen_filtered("c%d" % i, command_line_args)
      logger.info("Launched controller c%d: %s [PID %d]" % (i, " ".join(command_line_args), child.pid))
      child_processes.append(child)

  io_loop = RecocoIOLoop()
  
  scheduler = Scheduler(daemon=True, useEpoll=False)
  scheduler.schedule(io_loop)

  create_worker = lambda(socket): DeferredIOWorker(io_loop.create_worker_for_socket(socket), scheduler.callLater)

  topology.connect_to_controllers(controllers, create_worker)
  
  simulator.simulate()
finally:
  kill_children()
  kill_scheduler()
