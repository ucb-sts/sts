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

from sts.debugger import FuzzTester
from sts.deferred_io import DeferredIOWorker
from sts.procutils import kill_procs, popen_filtered

import sts.topology_generator as default_topology
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
# The module can define the following functions:
#   controllers(command_line_args=[]) => returns a list of pox.sts.experiment_config_info.ControllerInfo objects
#   switches()                        => returns a list of pox.sts.experiment_config_info.Switch objects

description = """
Run a debugger experiment.
Example usage:

$ %s ./pox/pox.py --no-cli openflow.of_01 --address=__address__ --port=__port__
""" % (sys.argv[0])

parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
             description=description)
parser.add_argument("-n", "--non-interactive", help='run debugger non-interactively',
                    action="store_false", dest="interactive", default=True)

parser.add_argument("-C", "--check-interval", type=int,
                    help='Run correspondence checking every C timesteps (assume -n)',
                    dest="check_interval", default=35)

# TODO: add argument for trace injection interval

parser.add_argument("-D", "--delay", type=float, metavar="time",
                    default=0.1,
                    help="delay in seconds for non-interactive simulation steps")

parser.add_argument("-R", "--random-seed", type=float, metavar="rnd",
                    help="Seed for the pseduo random number generator", default=0.0)

parser.add_argument("-s", "--steps", type=int, metavar="nsteps",
                    help="number of steps to simulate", default=None)

parser.add_argument("-p", "--port", type=int, metavar="port",
                    help="base port to use for controllers", default=6633)

parser.add_argument("-f", "--fuzzer-params", default="fuzzer_params.cfg",
                    help="optional parameters for the fuzzer (e.g. fail rate)")

parser.add_argument("-t", "--trace-file", default=None,
                    help="optional dataplane trace file (see trace_generator.py)")

parser.add_argument("-N", "--num-switches", type=int, default=2,
                    help="number of switches to create in the network")

parser.add_argument("-c", "--config", help='optional experiment config file to load')
parser.add_argument('controller_args', metavar='controller arg', nargs=argparse.REMAINDER,
                   help='arguments to pass to the controller(s)')
#parser.disable_interspersed_args()
args = parser.parse_args()

if not args.controller_args:
    print >> sys.stderr, "Warning: no controller arguments given"

# We use python as our DSL for specifying experiment configuration  
# The module can define the following functions:
#   controllers(command_line_args=[]) => returns a list of pox.sts.experiment_config_info.ControllerInfo objects
#   switches()                        => returns a list of pox.sts.experiment_config_info.Switch objects
if args.config:
  config = __import__(args.config_file)
else:
  config = object()

boot_controllers = False

if hasattr(config, 'controllers'):
  boot_controllers = True
  controllers = config.controllers(args.controller_args)
else:
  controllers = [Controller(args.controller_args, port=args.port)]

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
  if boot_controllers:
    for c in controllers:
      command_line_args = map(lambda(x): string.replace(x, "__port__", str(c.port)),
                          map(lambda(x): string.replace(x, "__address__", str(c.address)), c.cmdline))
      print command_line_args
      child = subprocess.Popen(command_line_args)
      logger.info("Launched controller c%d: %s [PID %d]" % (i, " ".join(command_line_args), child.pid))
      child_processes.append(child)

  io_loop = RecocoIOLoop()
  
  scheduler = Scheduler(daemon=True, useEpoll=False)
  scheduler.schedule(io_loop)

  #if hasattr(config, 'switches'):
  #  pass
  create_worker = lambda(socket): DeferredIOWorker(io_loop.create_worker_for_socket(socket), scheduler.callLater)

  # TODO: need a better way to choose FatTree vs. Mesh vs. whatever
  # Also, abusing the "num_switches" command line arg -> num_pods
  (panel,
   switch_impls,
   network_links,
   hosts,
   access_links) = default_topology.populate_fat_tree(controllers,
                                             create_worker,
                                             num_pods=args.num_switches)

  # For instrumenting the controller
  control_socket = connect_socket_with_backoff('', 6634)

  simulator = FuzzTester(fuzzer_params=args.fuzzer_params, interactive=args.interactive,
                        check_interval=args.check_interval,
                        random_seed=args.random_seed, delay=args.delay,
                        dataplane_trace=args.trace_file, control_socket=control_socket)
  simulator.simulate(panel, switch_impls, network_links, hosts, access_links, steps=args.steps)
finally:
  kill_children()
  kill_scheduler()
