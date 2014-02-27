#!/usr/bin/ruby
# Requires ruby2.0+

require 'optparse'

class Experiment
  attr_reader :dir, :name, :branch
  def initialize(dir, name, branch: "master")
    @dir = dir
    @name = name
    @branch = branch
  end
end

real_bugs = [
  Experiment.new("new_pyretic_loop_mcs/", "Pyretic loop"),
  Experiment.new("pox_early_packetin", "POX premature PacketIn"),
  Experiment.new("updated_debug_branch_loop_v3_mcs", "POX migration blackhole"),
  Experiment.new("fuzz_pox_4mesh_blackhole_mcs", "POX migration blackhole", branch: "pox_blackhole"),
  Experiment.new("nox_mesh_4_loop_repro_verbose", "NOX discovery loop"),
  Experiment.new("zeta_final", "Floodlight loop", branch: "floodlight")
  # ONOS..
]

synthetic_bugs = [
  Experiment.new("pox_null_pointer_mcs", "Null pointer on rarely used codepath"),
  Experiment.new("trigger_priority_mismatch_small_mcs", "Overlapping flow entries"),
  Experiment.new("snapshot_demo_synthetic_link_failure", "Delicate timer interleaving"),
  Experiment.new("pox_broken_floyd_mcs", "Algorithm misimplementation"),
  Experiment.new("trigger_multithreading_bug_mcs", "Multithreaded race condition"),
  Experiment.new("trigger_memory_leak3_mcs", "Memory leak"),
  Experiment.new("syn_mem_corruption_3switch_fuzzer_mcs", "Memory corruption")
]

def walk_directories(experiments, command_path)
  Dir.chdir("experiments/") do
    current_branch = `git rev-parse --abbrev-ref HEAD 1>&2`
    original_branch = current_branch
    experiments.each do |experiment|
      if experiment.branch != current_branch
        system "git checkout #{experiment.branch} 1>&2"
      end
      Dir.chdir(experiment.dir) do
        puts "====================  #{experiment.name}  ======================"
        puts `#{command_path}`
      end
    end
    if original_branch != current_branch
      system "git checkout #{original_branch} 1>&2"
    end
  end
end

if __FILE__ == $0
  options = {}
  OptionParser.new do |opts|
    options[:command_path] = "/bin/ls"
    opts.on("-c", "--command-path", "Path to command to run within each directory") do |c|
      options[:command_path] = c
    end

    options[:exclude_synthetic] = false
    opts.on("-e", "--exclude-synthetic", "Whether to exclude synthetic bug experiments") do
      options[:exclude_synthetic] = true
    end
  end.parse!

  if options[:exclude_synthetic]
    experiments = real_bugs
  else
    experiments = real_bugs + synthetic_bugs
  end

  walk_directories(experiments, options[:command_path])
end
