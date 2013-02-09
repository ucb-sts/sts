
from sts.util.console import Tee
import sts.experiments.lifecycle as exp_lifecycle
from sts.util.convenience import timestamp_string

import os
import shutil
import re

def setup_experiment(args, config):
  # Grab parameters
  if args.exp_name:
    config.exp_name = args.exp_name
  elif not hasattr(config, 'exp_name'):
    config.exp_name = exp_lifecycle.guess_config_name(config)

  if not hasattr(config, 'results_dir'):
    config.results_dir = "exp/%s" % config.exp_name

  if args.timestamp_results is not None:
    # Note that argparse returns a list
    config.timestamp_results = args.timestamp_results[0]

  if hasattr(config, 'timestamp_results') and config.timestamp_results:
    now = timestamp_string()
    config.results_dir += "_" + str(now)

  # Set up results directory
  if not os.path.exists(config.results_dir):
    os.makedirs(config.results_dir)

  # Make sure there's an __init__.py
  module_init_py = os.path.join(config.results_dir, "__init__.py")
  if not os.path.exists(module_init_py):
    open(module_init_py,"a").close()

  # Copy stdout and stderr to a file "simulator.out"
  tee = Tee(open(os.path.join(config.results_dir, "simulator.out"), "w"))
  tee.tee_stdout()
  tee.tee_stderr()

  # If specified, set up a config file for each controller
  for controller_config in config.simulation_config.controller_configs:
    if controller_config.config_template:
      controller_config.generate_config_file(config.results_dir)

  # Make sure that there are no uncommited changes
  if args.publish:
    exp_lifecycle.publish_prepare(config.exp_name, config.results_dir)

  # Record machine information for this experiment
  exp_lifecycle.dump_metadata("%s/metadata" % config.results_dir)

  # Copy over config file
  config_file = re.sub(r'\.pyc$', '.py', config.__file__)
  if os.path.exists(config_file):
    canonical_config_file = config.results_dir + "/orig_config.py"
    if os.path.abspath(config_file) != os.path.abspath(canonical_config_file):
      shutil.copy(config_file, canonical_config_file)

