#!/usr/bin/env ruby
# Requires ruby2.0+
# Must be invoked from top-level sts directory
# -r option will not work if there are unstaged changes.

require 'optparse'
require 'json'

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
  attr_reader :name, :original_commit
  def initialize(name, abs_path)
    @name = name
    @abs_path = abs_path
    @original_branch = chdir { `git rev-parse --abbrev-ref HEAD`.chomp }
    @current_branch = @original_branch
    @original_commit = chdir { `git rev-parse HEAD`.chomp }
    @current_commit = @original_commit
  end

  def change_branch(branch)
    if branch != @current_branch
      chdir do
        ret = system "git reset HEAD --hard 1>&2"
        raise "Failed to change branch" if ret != 0
        ret = system "git checkout #{branch} 1>&2"
        raise "Failed to change branch" if ret != 0
        @current_branch = branch
      end
    end
  end

  def rollback(commit)
    if commit != @current_commit
      chdir do
        ret = system "git checkout #{commit}"
        raise "Failed to rollback" if ret != 0
        @current_commit = commit
      end
    end
  end

  def restore_original_state
    change_branch(@original_branch)
    #rollback(@original_commit)
  end

  private

  def chdir(&block)
    Dir.chdir(@abs_path) do
      return block.call
    end
  end
end

class RepositoryOrchestrator
  # Manages all the repos
  def initialize
    # Must be invoked from the top-level STS directory
    @sts_repo = Repository.new("sts", Dir.pwd)
    @hassel_repo = Repository.new("hassel", Dir.pwd + "/sts/hassel")
    @pox_repo = Repository.new("pox", Dir.pwd + "/pox")
  end

  def rollback
    # Must be invoked from within the experiment directory of interest
    metadata = read_experiment_metadata
    @sts_repo.rollback(metadata["modules"]["sts"]["commit"])
    @pox_repo.rollback(metadata["modules"]["pox"]["commit"])
    if metadata["modules"].include? "hassel"
      @hassel_repo.rollback(metadata["modules"]["hassel"]["commit"])
      # Recompile binaries
      system "./tools/clean.sh"
    else
      # Legacy experiments didn't include hassel hashtags. Ensure that
      # by default, hassel is in the most up-to-date state.
      @hassel_repo.rollback(@hassel_repo.original_commit)
    end
  end

  def restore_original_state
    [@sts_repo, @hassel_repo, @pox_repo].each { |repo| repo.restore_original_state }
  end
end

real_bugs = [
  Experiment.new("new_pyretic_loop_mcs/", "Pyretic loop"),
  Experiment.new("pox_early_packetin", "POX premature PacketIn"),
  Experiment.new("updated_debug_branch_loop_v3_mcs", "POX in-flight blackhole"),
  Experiment.new("fuzz_pox_4mesh_blackhole_mcs", "POX migration blackhole", branch: "pox_blackhole"),
  Experiment.new("nox_mesh_4_loop_repro_verbose", "NOX discovery loop"),
  Experiment.new("zeta_final", "Floodlight loop", branch: "floodlight")
  # ONOS..
]

synthetic_bugs = [
  Experiment.new("pox_null_pointer_mcs", "Null pointer on rarely used codepath"),
  Experiment.new("trigger_priority_mismatch_small_mcs", "Overlapping flow entries"),
  # Replay does not reproduce violation, as noted in paper:
  #Experiment.new("snapshot_demo_synthetic_link_failure", "Delicate timer interleaving"),
  Experiment.new("pox_broken_floyd_mcs", "Algorithm misimplementation"),
  Experiment.new("trigger_multithreading_bug_mcs", "Multithreaded race condition"),
  Experiment.new("trigger_memory_leak3_mcs", "Memory leak"),
  Experiment.new("syn_mem_corruption_3switch_fuzzer_mcs", "Memory corruption")
]

def read_experiment_metadata
  # Read metadata (json file). Current working directory must contain it.
  metadata = {}
  File.open("metadata") do |f|
    metadata = JSON.load(f)
  end
  metadata
end

def walk_directories(experiments, options)
  experiments_repo = Repository.new("experiments", Dir.pwd + "/experiments")
  if options[:rollback_sts]
    repo_orchestrator = RepositoryOrchestrator.new
  end

  experiments.each do |experiment|
    experiments_repo.change_branch(experiment.branch)
    Dir.chdir("experiments/" + experiment.dir) do
      repo_orchestrator.rollback if options[:rollback_sts]
      puts "====================  #{experiment.name}  ======================"
      puts `#{options[:command_path]}`
    end
  end

  experiments_repo.restore_original_state
  if options[:rollback_sts]
    repo_orchestrator.restore_original_state
  end
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

    options[:rollback_sts] = false
    opts.on("-r", "--rollback-sts", "Whether to rollback STS + dependencies to the versions specified in metadata.json") do
      options[:rollback_sts] = true
    end
  end.parse!

  if options[:exclude_synthetic]
    experiments = real_bugs
  else
    experiments = real_bugs + synthetic_bugs
  end

  walk_directories(experiments, options)
end
