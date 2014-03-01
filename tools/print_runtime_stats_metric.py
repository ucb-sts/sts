#!/usr/bin/env python

# Print stats about the unexepected events in a MCS run.
# Tested by invoking it from run_cmd_per_experiment.rb

import json

def load_json(json_input):
  with open(json_input) as json_input_file:
    return json.load(json_input_file)

json_input = "runtime_stats.json"
runtime_stats = load_json(json_input)

non_lldp_count = 0
lldp_count = 0

#print runtime_stats['new_internal_events']
for l in runtime_stats['new_internal_events'].values():
  for e in l:
    if 'lldp' in e or 'ofp_echo_request' in e:
      lldp_count += 1
    else:
      non_lldp_count += 1

if 'buffered_message_receipts' in runtime_stats:
  for l in runtime_stats['buffered_message_receipts'].values():
    for e in l:
      if 'lldp' in e or 'ofp_echo_request' in e:
        lldp_count += 1
      else:
        non_lldp_count += 1

print "Unexpected LLDP/echo messages: ", non_lldp_count
print "All other unexpected messages: ", lldp_count
