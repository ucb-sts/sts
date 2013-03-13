#!/usr/bin/env python2.7
#
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

# TODO(cs): should use matplotlib instead of the template
from gpi_template import template
import string
import argparse
import json
import os

parser = argparse.ArgumentParser(description="generate a plot")
parser.add_argument('input', metavar="INPUT",
                    help='''The input json file''')
args = parser.parse_args()

def write_data_file(dat_filename, stats):
  ''' Write out the datapoints '''
  sorted_keys = stats["iteration_size"].keys()
  sorted_keys.sort(lambda a,b: -1 if int(a) < int (b) else 1 if int(a) > int(b) else 0)
  with open(dat_filename, "w") as dat:
    for key in sorted_keys:
      dat.write(str(key) + " " + str(stats["iteration_size"][key]) + '\n')

# Load the json
with open(args.input) as json_input:
  stats = json.load(json_input)

gpi_filename = string.replace(args.input, ".json", ".gpi")
output_filename = string.replace(args.input, ".json", ".pdf")
dat_filename = string.replace(args.input, ".json", ".dat")

write_data_file(dat_filename, stats)

with open(gpi_filename, "w") as gpi:
  # Finish off the rest of the template
  gpi.write(template)
  gpi.write('''set output "%s"\n''' % output_filename)
  if('prune_duration_seconds' in stats and 'replay_duration_seconds' in stats):
    gpi.write('''set title "total runtime=%.1fs, original runtime=%.1fs"\n''' %
            (stats["prune_duration_seconds"], stats["replay_duration_seconds"]))
  gpi.write('''plot "%s" index 0:1 title "" with steps ls 1\n''' %
            (dat_filename,))

# invoke gnuplot
os.system("gnuplot %s" % gpi_filename)
