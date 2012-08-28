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
from configs.experiment_config_lib import Controller
from pox.lib.recoco.recoco import Scheduler

import signal
import sys
import string
import subprocess
import time
import argparse
import logging
logging.basicConfig(level=logging.DEBUG)

log = logging.getLogger("sts")

# We use python as our DSL for specifying experiment configuration
# The module must define the following attribute:
#   controllers     => a list of pox.sts.experiment_config_info.ControllerInfo objects
# The module can optionally define the following attributes:
#   topology        => a sts.topology.Topology object
#                                        defining the switches and links
#   patch_panel     => a sts.topology.PatchPanel class (not object!)
#   control_flow    => a sts.control_flow.ControlModule object
#   dataplane_trace => a path to a dataplane trace file
#                     (e.g. traces/ping_pong_same_subnet.trace)

description = """
Run a debugger experiment.
Example usage:

$ %s -c config/fat_tree.cfg
""" % (sys.argv[0])

parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                 description=description)

parser.add_argument("-c", "--config", required=True,
                    default="configs/fat_tree.cfg",
                    help='experiment config file to load')

args = parser.parse_args()
config = __import__(args.config)

# For instrumenting the controller
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
  topology = config.topology
else:
  # We default to a FatTree with 4 pods
  topology = FatTree()

if hasattr(config, 'control_flow'):
  simulator = config.control_flow
else:
  # We default to a Fuzzer
  simulator = Fuzzer()

if hasattr(config, 'dataplane_trace'):
  dataplane_trace = config.dataplane_trace
else:
  # We default to no dataplane trace
  dataplane_trace = None


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
                          map(lambda(x): string.replace(x, "__address__",
                                                str(c.address)), c.cmdline))
      print command_line_args
      child = popen_filtered("c%d" % i, command_line_args)
      log.info("Launched controller c%d: %s [PID %d]" %
               (i, " ".join(command_line_args), child.pid))
      child_processes.append(child)

    if c.nom_port:
      # Monkey wrench on a socket for pulling down the nom
      # TODO(cs): alternatively, convert the Controller `metadata` object into
      # a Controller `state` object for internal use
      c.nom_socket = connect_socket_with_backoff(c.address, c.nom_port)

  io_loop = RecocoIOLoop()

  scheduler = Scheduler(daemon=True, useEpoll=False)
  scheduler.schedule(io_loop)

  create_worker = lambda(socket): DeferredIOWorker(io_loop.create_worker_for_socket(socket),
                                                   scheduler.callLater)

  topology.connect_to_controllers(controllers, create_worker)

  simulation = Simulation(controllers, topology, patch_panel_class,
                          dataplane_trace=dataplane_trace)

  simulator.simulate(simulation)
finally:
  kill_children()
  kill_scheduler()
