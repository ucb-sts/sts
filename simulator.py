#!/usr/bin/env python2.7

from sts.util.procutils import kill_procs
from sts.control_flow import Fuzzer
from sts.simulation_state import SimulationConfig

import signal
import sys
import argparse
import logging
import logging.config

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

parser.add_argument('-v', '--verbose', action="count", default=0,
                    help='''increase verbosity''')

parser.add_argument('-L', '--log-config',
                    metavar="FILE", dest="log_config",
                    help='''choose a python log configuration file''')

args = parser.parse_args()

if args.log_config:
  logging.config.fileConfig(args.log_config)
else:
  logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

log = logging.getLogger("sts")

# Allow configs to be specified as paths as well as module names
if args.config.endswith('.py'):
  args.config = args.config[:-3].replace("/", ".")

try:
  config = __import__(args.config, globals(), locals(), ["*"])
except ImportError:
  # try again, but prepend config module path
  config = __import__("config.%s" % args.config, globals(), locals(), ["*"])

# For controlling the simulation
if hasattr(config, 'control_flow'):
  simulator = config.control_flow
else:
  # We default to a Fuzzer
  simulator = Fuzzer(SimulationConfig())

# Set an interrupt handler
def handle_int(signal, frame):
  print >> sys.stderr, "Caught signal %d, stopping sdndebug" % signal
  if (simulator.simulation_cfg.current_simulation is not None):
    simulator.simulation_cfg.current_simulation.clean_up()
  sys.exit(13)

signal.signal(signal.SIGINT, handle_int)
signal.signal(signal.SIGTERM, handle_int)

# Start the simulation
try:
  res = simulator.simulate()
  # TODO(cs); temporary hack: replayer returns self.simulation no a return
  # code
  if type(res) != int:
    res = 0
finally:
  if (simulator.simulation_cfg.current_simulation is not None):
    simulator.simulation_cfg.current_simulation.clean_up()

sys.exit(res)
