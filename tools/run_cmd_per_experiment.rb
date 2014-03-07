#!/usr/bin/env ruby
# Requires ruby2.0+
# Must be invoked from top-level sts directory

require 'optparse'

class Experiment
  attr_reader :dir, :name, :branch
  def initialize(dir, name, branch: "master")
    @dir = dir
    @name = name
    @branch = branch
  end
end

# Tracks (and modifies) the current branch/commit of a repository
class Repository
  attr_reader :name, :current_branch
  def initialize(name, abs_path)
    @name = name
    @abs_path = abs_path
    @original_branch = chdir { `git rev-parse --abbrev-ref HEAD`.chomp }
    @current_branch = @original_branch
  end

  def maybe_change_branch(branch)
    if branch != @current_branch
      chdir { change_branch(branch) }
    end
  end

  def restore_to_original_state
    maybe_change_branch(@original_branch)
  end

  :private

  def change_branch(branch)
    system "git reset HEAD --hard 1>&2"
    system "git checkout #{branch} 1>&2"
    @current_branch = branch
  end

  def chdir(&block)
    Dir.chdir(@abs_path) do
      return block.call
    end
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
  #Experiment.new("snapshot_demo_synthetic_link_failure", "Delicate timer interleaving"),
  Experiment.new("pox_broken_floyd_mcs", "Algorithm misimplementation"),
  Experiment.new("trigger_multithreading_bug_mcs", "Multithreaded race condition"),
  Experiment.new("trigger_memory_leak3_mcs", "Memory leak"),
  Experiment.new("syn_mem_corruption_3switch_fuzzer_mcs", "Memory corruption")
]

def walk_directories(experiments, options)
  experiments_repo = Repository.new("experiments", Dir.pwd + "/experiments/")
  experiments.each do |experiment|
    experiments_repo.maybe_change_branch(experiment.branch)
    Dir.chdir("experiments/" + experiment.dir) do
      puts "====================  #{experiment.name}  ======================"
      puts `#{options[:command_path]}`
    end
  end
  experiments_repo.restore_to_original_state
end

if __FILE__ == $0
  options = {}
  OptionParser.new do |opts|
    options[:command_path] = "/bin/ls"
    opts.on("-c", "--command-path PATH", "Absolute path to a command to run within each directory") do |p|
      options[:command_path] = p
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

  walk_directories(experiments, options)
end
