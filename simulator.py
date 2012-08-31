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
from sts.procutils import kill_procs

from sts.topology import FatTree
from sts.control_flow import Fuzzer
from sts.simulation import Simulation
from pox.lib.ioworker.io_worker import RecocoIOLoop
from pox.lib.util import connect_socket_with_backoff
from config.experiment_config_lib import ControllerConfig
from pox.lib.recoco.recoco import Scheduler
from sts.entities import Controller
from traces.trace import Trace

import signal
import sys
import string
import subprocess
import time
import argparse
import logging
logging.basicConfig(level=logging.DEBUG)

log = logging.getLogger("sts")

description = """
Run a simulation.
Example usage:

$ %s -c config/fat_tree.cfg
""" % (sys.argv[0])

parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                 description=description)

parser.add_argument('-c', '--config',
                    default='config.fat_tree',
                    help='''experiment config module in the config/ '''
                         '''subdirectory, e.g. config.fat_tree''')

args = parser.parse_args()
config = __import__(args.config, globals(), locals(), ["*"])

# For instrumenting the controller
if hasattr(config, 'controllers'):
  controller_configs = config.controllers
else:
  raise RuntimeError("Must specify controllers in config file")

# For forwarding packets
if hasattr(config, 'patch_panel'):
  patch_panel_class = config.patch_panel
else:
  # We default to a BufferedPatchPanel
  patch_panel_class = BufferedPatchPanel

# For tracking the edges and vertices in our network
if hasattr(config, 'topology'):
  topology = config.topology
else:
  # We default to a FatTree with 4 pods
  topology = FatTree()

# For controlling the simulation
if hasattr(config, 'control_flow'):
  simulator = config.control_flow
else:
  # We default to a Fuzzer
  simulator = Fuzzer()

# For injecting dataplane packets into the simulated network
if hasattr(config, 'dataplane_trace') and config.dataplane_trace:
  dataplane_trace = Trace(config.dataplane_trace, topology)
else:
  # We default to no dataplane trace
  dataplane_trace = None

scheduler = None
def kill_scheduler():
  if scheduler and not scheduler._hasQuit:
    sys.stderr.write("Stopping Recoco Scheduler...")
    scheduler.quit()
    sys.stderr.write(" OK\n")

def kill_active_processes():
  Controller.kill_active_procs()

def handle_int(signal, frame):
  print >> sys.stderr, "Caught signal %d, stopping sdndebug" % signal
  kill_scheduler()
  sys.exit(0)

signal.signal(signal.SIGINT, handle_int)
signal.signal(signal.SIGTERM, handle_int)

try:
  # Boot the controllers
  controllers = []
  for c in controller_configs:
    controller = Controller(c)
    log.info("Launched controller c%s: %s [PID %d]" %
             (str(c.uuid), " ".join(c.cmdline), controller.pid))
    controllers.append(controller)

  io_loop = RecocoIOLoop()

  scheduler = Scheduler(daemon=True, useEpoll=False)
  scheduler.schedule(io_loop)

  create_worker = lambda(socket): DeferredIOWorker(io_loop.create_worker_for_socket(socket),
                                                   scheduler.callLater)

  topology.connect_to_controllers(controller_configs, create_worker)

  simulation = Simulation(controllers, topology, patch_panel_class,
                          dataplane_trace=dataplane_trace)

  simulator.simulate(simulation)
finally:
  for c in controllers:
    c.kill()

  kill_scheduler()
