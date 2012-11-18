#!/usr/bin/env python2.7

# TODO(cs): should use matplotlib instead of the template
from gpi_template import template
import string
import argparse
import json
import os

parser = argparse.ArgumentParser(description="generate a plot")
parser.add_argument('-i', '--input',
                    required=True,
                    help='''The input json file''')
args = parser.parse_args()

def write_data_file(dat_filename, stats):
  ''' Write out the datapoints '''
  sorted_keys = stats["iteration_size"].keys()
  sorted_keys.sort()
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
  gpi.write('''set title "total runtime=%.1fs, original runtime=%.1fs"\n''' %
            (stats["prune_duration_seconds"], stats["replay_duration_seconds"]))
  gpi.write('''plot "%s" index 0:1 title "" w lp ls 1\n''' %
            (dat_filename,))

# invoke gnuplot
os.system("gnuplot %s" % gpi_filename)
