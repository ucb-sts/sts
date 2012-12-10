#!/usr/bin/env python2.7

from sts.util.procutils import kill_procs
from sts.topology import FatTree, BufferedPatchPanel
from sts.control_flow import Fuzzer
from sts.invariant_checker import InvariantChecker
from sts.simulation_state import SimulationConfig
import sts.snapshot as snapshot
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

description = """
Run a simulation.
Example usage:

$ %s -c config.fat_tree
""" % (sys.argv[0])

parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                 description=description)

parser.add_argument('-c', '--config',
                    default='config.fuzz_pox_fattree',
                    help='''experiment config module in the config/ '''
                         '''subdirectory, e.g. config.fat_tree''')

args = parser.parse_args()
# Allow configs to be specified as paths as well as module names
if args.config.endswith('.py'):
  args.config = args.config[:-3].replace("/", ".")

try:
  config = __import__(args.config, globals(), locals(), ["*"])
except ImportError:
  # try again, but prepend config module path
  config = __import__("config.%s" % args.config, globals(), locals(), ["*"])

# For booting controllers
if hasattr(config, 'controllers'):
  controller_configs = config.controllers
else:
  raise RuntimeError("Must specify controllers in config file")

# For forwarding packets
if hasattr(config, 'patch_panel_class'):
  patch_panel_class = config.patch_panel_class
else:
  # We default to a BufferedPatchPanel
  patch_panel_class = BufferedPatchPanel

# For tracking the edges and vertices in our network
if hasattr(config, 'topology_class'):
  topology_class = config.topology_class
else:
  # We default to a FatTree
  topology_class = FatTree

# For constructing the topology object
if hasattr(config, 'topology_params'):
  topology_params = config.topology_params
else:
  # We default to no parameters
  topology_params = ""

# For controlling the simulation
if hasattr(config, 'control_flow'):
  simulator = config.control_flow
else:
  # We default to a Fuzzer
  simulator = Fuzzer()

# For snapshotting the controller's view of the network configuration
snapshot_service = snapshot.get_snapshotservice(controller_configs)

# For injecting dataplane packets into the simulated network
if hasattr(config, 'dataplane_trace') and config.dataplane_trace:
  dataplane_trace_path = config.dataplane_trace
else:
  # We default to no dataplane trace
  dataplane_trace_path = None

# Optionally wait N seconds after booting the switches, but before starting
# the simulation.
if hasattr(config, 'switch_init_sleep_seconds'):
  switch_init_sleep_seconds = config.switch_init_sleep_seconds
else:
  # We default to no waiting
  switch_init_sleep_seconds = False

# Set an interrupt handler
def handle_int(signal, frame):
  print >> sys.stderr, "Caught signal %d, stopping sdndebug" % signal
  if (simulation_cfg is not None and
      simulation_cfg.current_simulation is not None):
    simulation_cfg.current_simulation.clean_up()
  sys.exit(0)

simulation_cfg = None

signal.signal(signal.SIGINT, handle_int)
signal.signal(signal.SIGTERM, handle_int)

# Start the simulation
try:
  simulation_cfg = SimulationConfig(controller_configs, topology_class,
                                    topology_params, patch_panel_class,
                                    dataplane_trace_path=dataplane_trace_path,
                                    switch_init_sleep_seconds=switch_init_sleep_seconds,
                                    snapshot_service=snapshot_service)
  simulator.simulate(simulation_cfg)
finally:
  if (simulation_cfg is not None and
      simulation_cfg.current_simulation is not None):
    simulation_cfg.current_simulation.clean_up()
