#!/usr/bin/ruby

# This script parses mcs_finder.log to infer which subsequences ended in
# a bug.
#
# It only exists because old STS versions didn't store this information in an
# easily accessible way. It should be replaced with a simple tool that parses
# the appropriate information in runtime_stats.json.

replay_number = 0
replay_to_violation = {}

File.foreach(ARGV[0]) do |line|
  if line =~ /Current subset:/
    replay_number += 1
  end
  if line =~ /No violation in/
    replay_to_violation[replay_number] = false
  end
  if line =~ /Violation!/
    replay_to_violation[replay_number] = true
  end
end

replay_to_violation.keys.sort.each do |key|
  puts "Replay #{key} violation #{replay_to_violation[key]}"
end
