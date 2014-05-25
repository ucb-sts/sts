#!/usr/bin/env ruby
# Requires ruby2.0+
# Must be invoked from top-level sts directory

require_relative 'run_cmd_per_experiment'

options = {}
parser = OptionParser.new do |opts|
  options[:config_path] = ""
  opts.on("-c", "--config CONFIG", "path to experiment config file") do |name|
    options[:config_path] = name
  end

  options[:new_experiment_name] = ""
  opts.on("-n", "--new-experiment-name NAME", "experiment name to assign to this execution") do |name|
    options[:new_experiment_name] = name
  end
end
parser.parse!

if options[:config_path].empty?
  puts parser
  exit 1
end

# Pesky .pyc files in old directories cause import path confusion
# Unfortunately, git clean -fX doesn't remove non-tracked .pyc files, so
# remove them ourselves.
Dir.glob('**/*pyc').each { |f| File.delete(f) }

experiment_dir = File.dirname(options[:config_path])

repo_orchestrator = RepositoryOrchestrator.new
Dir.chdir(experiment_dir) do
  repo_orchestrator.rollback
  Dir.chdir "../../" do
    cmd = "./simulator.py -c #{options[:config_path]}"
    cmd += " -n #{options[:new_experiment_name]}" unless options[:new_experiment_name].empty?
    system cmd
  end
  repo_orchestrator.restore_original_state
end
