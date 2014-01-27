#!/usr/bin/ruby

# This script parses mcs_finder.log to infer which subsequences ended in
# a bug.
#
# It only exists because old STS versions didn't store this information in an
# easily accessible way. It should be replaced with a simple tool that parses
# the appropriate information in runtime_stats.json.

require 'json'

replay_number = -1
replay_to_violation = {}
unknown_replay_results = []

File.foreach(ARGV[0]) do |line|
  if line =~ /Sleeping/ # /Current subset:/
    replay_number += 1
    unknown_replay_results << replay_number
  end
  if line =~ /No violation in/
    unknown_replay_results.each do |i|
      replay_to_violation[i] = false
    end
    unknown_replay_results = []
  end
  if line =~ /Violation!/
    replay_to_violation[replay_number] = true
    unknown_replay_results.each do |i|
      replay_to_violation[i] = false unless i == replay_number
    end
    unknown_replay_results = []
  end
end

puts JSON.pretty_generate(replay_to_violation)

