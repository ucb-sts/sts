---
layout: default
title: STS Walkthrough
subtitle: Step-by-step overview of STS's use-cases.
description: Walk through example usage of STS.
---

## Phase I: Bug Finding

We start by using STS to find bugs in controller software. STS
supports two ways to accomplish this goal:
most commonly, we use STS to simulate a network, generate random
network events, and periodically check invariants;
we also run STS interactively so that we can examine the state of
any part of the simulated network, observe and manipulate messages, and
follow our intuition to induce orderings that we believe may trigger bugs.

### Fuzzing Mode

Fuzzing mode is how we use STS to generate randomly chosen input sequences in
search of bugs. Let's begin by looking at how we run the STS fuzzer.

In the `config/` subdirectory, we find a configuration file
`fuzz_pox_simple.py` we'll use to specify our experiment.

The first two lines of this file tells STS how to boot the SDN controller
(in this case, POX):

    start_cmd = ('''./pox.py openflow.discovery forwarding.l2_multi '''
                 '''openflow.of_01 --address=__address__ --port=__port__''')
    controllers = [ControllerConfig(start_cmd, cwd="pox/")]

Here we're running POX's l2_multi module, a simple routing routing
application located in `./pox/forwarding/`. Note that the macros "__address__"
and "__port__" are expanded by STS to allow
it to choose available ports and addresses.

The next two lines specify the network topology we would like STS to simulate:

    topology_class = MeshTopology
    topology_params = "num_switches=2"

In this case, we're simulating a simple mesh topology consisting of two
switches each with an attached host, and a single link connecting the
switches.

The next line bundles up the controller configuration parameters with the
network topology configuration parameters:

    simulation_config = SimulationConfig(controller_configs=controllers,
                                         topology_class=topology_class,
                                         topology_params=topology_params)

The last line specifies what mode we would like STS to run in. In our case,
we want to generate random inputs with the Fuzzer class:

    control_flow = Fuzzer(simulation_config,
                          input_logger=InputLogger(),
                          invariant_check_name="InvariantChecker.check_liveness",
                          halt_on_violation=True)

Here we're telling the Fuzzer to record its execution with an
InputLogger, check periodically whether the controller process has crashed,
and halt the execution whenever we detect that the controller process has
indeed crashed.

For a complete list of invariants to check, see
the dictionary at the bottom of `config/invariant_checks.py`.

By default Fuzzer generates its inputs based on a set of event probabilities defined in
`config/fuzzer_params.py`. Taking a closer look at that file, we see a list of
event types followed by numbers in the range \[0,1\], such as:

     switch_failure_rate = 0.05
     switch_recovery_rate = 0.1
     ...

This tells the fuzzer to trigger kill live switches with a probability of 5%,
and recover down switches with a probability of 10%.

Let's go ahead and see STS in action, by invoking the simulator with our
config file:

    $ ./simulator.py -c config/fuzz_pox_simple.py

The output should look something like this:

<img
src="http://www.eecs.berkeley.edu/%7Ercs/research/console_output.png"
alt="console output">

We see that STS populates the simulated topology, boots POX, connects the
switches to POX, and begins feeding in traffic injections and other events.
The console output is colored to dilineate the different sources of output:
the green output is STS's internal logging, the blue output shows Fuzzer's
injected network events, and the orange/red output is the logging output of
the POX controller process ("C1").

One particularly useful usage hint for fuzzer is that you can drop into
interactive mode, described next, by hitting ^C at any point in the execution.

### Interactive Mode

This mode provides a command line interface for users to interactively step
through the execution of the network. Type `help` for more information on the
command line interface.

If you have bug in mind, interactive mode is the perfect way to manually
trigger it.

Just change one thing in the config file.

## Phase II: Troubleshooting

Let's suppose we found a juicy bug. Luckily, our event trace was recorded
while we were running STS previously.

The simulator automatically copies your configuration parameters, event logs,
and console output into the experiments/ directory for later examination.

See experiments/foo/bar for this event trace.

Introduce pretty_print_event_trace.py here? Seems like an appropriate intro to
event trace files.

Experiment results are automatically placed in their own subdirectory under experiments/.
There you can find console output, serialized event traces, and config files
for replay and MCS finding.

By default, the name of the results directory is inferred from the name of the
config file. You can also specify a custom name with the `-n` parameter to
simulator.py. You can also specify that each directory name should have a
timestamp appended with the `-t` parameter

### Replay Mode

All events observed in fuzzing and interactive mode are recorded for later replay.

Given an event trace generated by Interactive or Fuzzer, Replayer tries as best as it can to inject the inputs in
the trace in a way that reproduces the same result. It does this by listening
to the internal events in the trace and replaying inputs when it sees that the
causal dependencies have been met.

### MCS Finder Mode

Given an event trace, MCSFinder executes delta debugging to find the minimal
causal sequence. For each subsequence chosen by delta debugging, it
instantiates a new Replayer object to replay the execution, and checks at the
end whether the bug appears. To avoid garbage collection overhead, MCSFinder
runs each Replay in a separate process, and returns the results via XMLRPC.
See sts/util/rpc_forker.py for the mechanics of forking.

The runtime statistics of MCSFinder are stored in a dictionary and logged to a json file.

## Root Causing

### InteractiveReplayer Mode

Given an event trace (possibly minimized by MCSFinder), InteractiveReplayer
allows you to interactively step through the trace (a la OFRewind) in order to
understand the conditions that triggered a bug. This is helpful for:
  - visualizing the network topology
  - tracing the series of link/switch failures/recoveries
  - tracing the series of host migrations
  - tracing the series of flow_mods
  - tracing the series of traffic injections
  - perturbing the original event sequence by adding / removing inputs
    interactively
  - ...

### OpenFlowReplayer Mode

Delta debugging does not fully minimize traces (often for good reason,
e.g. delicate timings). In particular we have observed minimized traces often
contain many OpenFlow messages that time our or are overwritten, i.e. are not
directly relevent for triggering an invalid network configuratoon.

OpenFlowReplayer replays the OpenFlow messages from an event trace, enabling:
  - automatic filtering of flow_mods that timed out or were overwritten by
    later flow_mods.
  - automatic filtering of flow_mods that are irrelevant to a set of flow
    entries specified by the user.
  - interactive bisection of the OpenFlow trace to infer which messages were
    and were not relevent for triggering the bug (especially useful for tricky
    cases requiring human involvment). (TBD)

The tool can then spit back out a new event trace without the irrelevant
OpenFlow messages, to be replayed again by Replayer or InteractiveReplayer.

### Visualization tools

A common workflow:
  - Run `./simulator.py -c experiments/experiment_name/mcs_config.py`
  - Discover that the final MCS does not trigger the bug.
  - Open `visualize1D.html` in a web browser.
  - Load either the original (fuzzed) trace,
    `experiments/experiment_name/events.trace`,
    or the first replay of this trace,
    `experiments/experiment_name_mcs/interreplay_0_reproducibility/events.trace`,
    as the first timeline. I have found that it is often better to load the
    first replay rather than the original fuzzed trace, since this has
    timing information that matches the other replays much more closely.
  - Load the final replay of the MCS trace,
    `experiments/experiment_name_mcs/interreplay_._final_mcs_trace/events.trace`,
    as the second timeline.
  - Hover over events to further information about them, including functional equivalence
    with events in the other traces.
  - Load intermediate replay trace timelines if needed. Intermediate replay
    traces from delta debugging runs can be found in
    `experiments/experiment_name_mcs/interreplay_*`

- ```visualization/visualize2D.html```: A webpage for showing a Lamport time diagram of an
   event trace. Useful for visually spotting the root causes of race conditions
   and other nasty bugs.

### Pretty printing event traces.

The raw event.trace files are hard for humans to read.
./tools/pretty_print_event_trace.py.

This script's output is highly configurable.

<pre>
----- config file format: ----
config files are python modules that may define the following variables:
fields  => an array of field names to print. uses default_fields if undefined.
filtered_classes => a set of classes to ignore, from sts.replay_event
...
see example_pretty_print_config.py for an example.
</pre>

That's it! See this
[page](http://ucb-sts.github.io/sts/software_architecture.html) for a deeper dive into the structure
of STS's code, including additional configuration parameters to STS's different modes.
