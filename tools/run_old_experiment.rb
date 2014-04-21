#!/usr/bin/env ruby
# Requires ruby2.0+
# Must be invoked from top-level sts directory

require_relative 'run_cmd_per_experiment'

if ARGV.length == 0
  raise RuntimeError.new("Usage: #{$0} /path/to/<config file>.py")
end

experiment_dir = File.dirname(ARGV[0])

# Pesky .pyc files in old directories cause import path confusion
system "./tools/clean.sh"

repo_orchestrator = RepositoryOrchestrator.new
Dir.chdir(experiment_dir) do
  repo_orchestrator.rollback
  Dir.chdir "../../" do
    system "./simulator.py -c #{ARGV[0]}"
  end
  repo_orchestrator.restore_original_state
end
