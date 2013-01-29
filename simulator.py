#!/usr/bin/env python2.7

from sts.util.console import tee_stdout
from sts.util.procutils import kill_procs
from sts.control_flow import Fuzzer
from sts.simulation_state import SimulationConfig
from sts.util.convenience import timestamp_string
import sts.exp.lifecycle as exp_lifecycle

import os
import re
import shutil
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

parser.add_argument('-p', '--publish', action="store_true", default=False,
                    help='''publish experiment results to git''')

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
except ImportError as e:
  try:
    # try again, but prepend config module path
    config = __import__("config.%s" % args.config, globals(), locals(), ["*"])
  except ImportError:
    raise e

if not hasattr(config, 'exp_name'):
  config.exp_name = exp_lifecycle.guess_config_name(config)

if not hasattr(config, 'results_dir'):
  config.results_dir = "exp/%s" % config.exp_name

now = timestamp_string()
if hasattr(config, 'timestamp_results') and config.timestamp_results:
  config.results_dir += "_" + str(now)

if not os.path.exists(config.results_dir):
  os.makedirs(config.results_dir)
module_init_py = os.path.join(config.results_dir, "__init__.py")
if not os.path.exists(module_init_py):
  open(module_init_py,"a").close()
tee_stdout(os.path.join(config.results_dir, "simulator.out"))

for controller_config in config.simulation_config.controller_configs:
  if controller_config.config_template:
    controller_config.generate_config_file(config.results_dir)

if args.publish:
  exp_lifecycle.publish_prepare(config.exp_name, config.results_dir)

exp_lifecycle.dump_metadata("%s/metadata" % config.results_dir)

config_file = re.sub(r'\.pyc$', '.py', config.__file__)
if os.path.exists(config_file):
  canonical_config_file = config.results_dir + "/orig_config.py"
  if  os.path.abspath(config_file) != os.path.abspath(canonical_config_file):
    shutil.copy(config_file, canonical_config_file)

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
