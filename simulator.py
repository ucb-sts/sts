#!/usr/bin/env python2.7

from sts.util.procutils import kill_procs
from sts.control_flow import Fuzzer
from sts.simulation_state import SimulationConfig
import sts.experiments.setup as experiment_setup
import sts.experiments.lifecycle as exp_lifecycle

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

parser.add_argument('-n', '--exp-name', dest="exp_name",
                    default=None,
                    help='''experiment name''')

parser.add_argument('-t', '--timestamp-results', dest="timestamp_results",
                    default=None, nargs=1, action="store",
                    type=lambda s: s.lower() in ('y', 'yes', 'on', 't', 'true', '1', 'yeay', 'ja', 'jepp'),
                    help='''whether to time stamp the result directory''')

parser.add_argument('-p', '--publish', action="store_true", default=False,
                    help='''publish experiment results to git''')

args = parser.parse_args()

# Allow configs to be specified as paths as well as module names
if args.config.endswith('.py'):
  args.config = args.config[:-3].replace("/", ".")

try:
  config = __import__(args.config, globals(), locals(), ["*"])
except ImportError as e:
  try:
    # module path might not have been specified. Try again with path prepended
    config = __import__("config.%s" % args.config, globals(), locals(), ["*"])
  except ImportError:
    raise e

# Set up the experiment results directories
experiment_setup.setup_experiment(args, config)

# Load log configuration
if args.log_config:
  logging.config.fileConfig(args.log_config)
else:
  logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

# Simulator controls the simulation
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
signal.signal(signal.SIGQUIT, handle_int)

# Start the simulation
try:
  # First tell simulator where to log
  simulator.init_results(config.results_dir)
  res = simulator.simulate()
  # TODO(cs); temporary hack: replayer returns self.simulation no a return
  # code
  if type(res) != int:
    res = 0
finally:
  if (simulator.simulation_cfg.current_simulation is not None):
    simulator.simulation_cfg.current_simulation.clean_up()
  if args.publish:
    exp_lifecycle.publish_results(config.exp_name, config.results_dir)

sys.exit(res)
