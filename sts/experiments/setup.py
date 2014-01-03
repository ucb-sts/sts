# Copyright 2011-2013 Andreas Wundsam
# Copyright 2011-2013 Colin Scott
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


from sts.util.console import Tee
import sts.experiments.lifecycle as exp_lifecycle
from sts.util.convenience import timestamp_string, create_clean_python_dir, create_python_dir

import os
import shutil
import re
import logging

def setup_experiment(args, config):
  # Grab parameters
  if args.exp_name:
    config.exp_name = args.exp_name
  elif not hasattr(config, 'exp_name'):
    config.exp_name = exp_lifecycle.guess_config_name(config)

  if not hasattr(config, 'results_dir'):
    config.results_dir = "experiments/%s" % config.exp_name

  if args.timestamp_results is not None:
    # Note that argparse returns a list
    config.timestamp_results = args.timestamp_results[0]

  if hasattr(config, 'timestamp_results') and config.timestamp_results:
    now = timestamp_string()
    config.results_dir += "_" + str(now)

  # Set up results directory
  create_python_dir("./experiments")
  create_clean_python_dir(config.results_dir)

  # Copy stdout and stderr to a file "simulator.out"
  tee = Tee(open(os.path.join(config.results_dir, "simulator.out"), "w"))
  tee.tee_stdout()
  tee.tee_stderr()

  # Load log configuration.
  # N.B. this must be done after Tee()'ing.
  if args.log_config:
    logging.config.fileConfig(args.log_config)
  else:
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

  # If specified, set up a config file for each controller
  for controller_config in config.simulation_config.controller_configs:
    if controller_config.config_template:
      controller_config.generate_config_file(config.results_dir)

  # Make sure that there are no uncommited changes
  if args.publish:
    exp_lifecycle.publish_prepare(config.exp_name, config.results_dir)

  # Record machine information for this experiment
  additional_metadata = None
  if hasattr(config, "get_additional_metadata"):
    additional_metadata = config.get_additional_metadata()

  exp_lifecycle.dump_metadata("%s/metadata" % config.results_dir,
                              additional_metadata=additional_metadata)

  # Copy over config file
  config_file = re.sub(r'\.pyc$', '.py', config.__file__)
  if os.path.exists(config_file):
    canonical_config_file = config.results_dir + "/orig_config.py"
    if os.path.abspath(config_file) != os.path.abspath(canonical_config_file):
      shutil.copy(config_file, canonical_config_file)

