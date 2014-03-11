#!/usr/bin/env python2.7
#
# Copyright 2011-2013 Colin Scott
# Copyright 2011-2013 Andreas Wundsam
# Copyright 2012-2013 Sam Whitlock
# Copyright 2012-2012 Kyriakos Zarifis
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

import sys
if sys.version_info < (2, 7):
  raise RuntimeError('''Must use python 2.7 or greater. '''
                     '''See http://www.python.org/download/releases/2.7.4/''')

from sts.util.procutils import kill_procs
from sts.control_flow.fuzzer import Fuzzer
from sts.simulation_state import SimulationConfig
import sts.experiments.setup as experiment_setup
import sts.experiments.lifecycle as exp_lifecycle

import signal
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
                         '''subdirectory, e.g. config.fuzz_pox_mesh''')

parser.add_argument('-v', '--verbose', action="count", default=0,
                    help='''increase verbosity''')

parser.add_argument('-L', '--log-config',
                    metavar="FILE", dest="log_config",
                    help='''choose a python log configuration file''')

parser.add_argument('-n', '--exp-name', dest="exp_name",
                    default=None,
                    help='''experiment name (determines result directory name)''')

parser.add_argument('-t', '--timestamp-results', dest="timestamp_results",
                    default=False, action="store_true",
                    help='''whether to append a timestamp to the result directory name''')

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

# Simulator controls the simulation
if hasattr(config, 'control_flow'):
  simulator = config.control_flow
else:
  # We default to a Fuzzer
  simulator = Fuzzer(SimulationConfig())

# Set an interrupt handler
def handle_int(signal, frame):
  import os
  from sts.util.rpc_forker import LocalForker
  sys.stderr.write("Caught signal %d, stopping sdndebug (pid %d)\n" %
                    (signal, os.getpid()))
  if (simulator.simulation_cfg.current_simulation is not None):
    simulator.simulation_cfg.current_simulation.clean_up()
  # kill fork()ed procs
  LocalForker.kill_all()
  sys.exit(13)

signal.signal(signal.SIGINT, handle_int)
signal.signal(signal.SIGTERM, handle_int)
signal.signal(signal.SIGQUIT, handle_int)

# Start the simulation
try:
  # First tell simulator where to log
  simulator.init_results(config.results_dir)
  # Now start the simulation
  simulation = simulator.simulate()
finally:
  if (simulator.simulation_cfg.current_simulation is not None):
    simulator.simulation_cfg.current_simulation.clean_up()
  if args.publish:
    exp_lifecycle.publish_results(config.exp_name, config.results_dir)

sys.exit(simulation.exit_code)
