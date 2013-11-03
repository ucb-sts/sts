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
switches, and feeds in network traffic and other events.
The console output is colored to delineate the different sources of output:
the <font color="009900">green</font> output is STS's internal logging, the
<font color="66CCFF">blue</font> output shows Fuzzer's
injected network events, and the <font color="FFCC66">orange</font> output is the logging output of
the POX controller process ("C1").

One particularly useful feature of the Fuzzer is that you can drop into
interactive mode, described next, by hitting ^C at any point in the execution.

### Interactive Mode

If you have bug in mind, interactive mode is the perfect way to manually
trigger it. It allows us to simulate the same network events as fuzzer mode,
but gives us a command line interface to control the execution and examine the
state of the network as we proceed.

We can run interactive either by hitting ^C during a fuzz execution, or by
changing one line in the config file from before:

    control_flow = Interactive(simulation_config, input_logger=InputLogger())

This tells STS to start with interactive mode rather than fuzzing. When we run
STS with our modified configuration file, it will again populate the network
topology, start the controller process, connect switches, and this time present us with
a prompt:

<img
src="http://www.eecs.berkeley.edu/%7Ercs/research/interactive_screenshot.png"
alt="console output">

Each time we hit enter without other console input, the simulator will process
any pending I/O operations (e.g. OpenFlow receipts), sleep for a small amount
of time, and present us again with a prompt.

Interactive mode is particularly useful for examining the state of the network.
For example, we can list all switches in the network by accessing the
`topology` object's `switches` property:

    STS [next] >topology.switches
    [SoftwareSwitch(dpid=1, num_ports=2), SoftwareSwitch(dpid=2, num_ports=2)]

We can also examine the current routing tables of a switch with the
`show_flows` command:

    STS [next] >show_flows 1
    ----------------------------------------------------------------------------------------------------------------------
    |  Prio | in_port | dl_type | dl_src | dl_dst            | nw_proto | nw_src | nw_dst | tp_src | tp_dst | actions    |
    ----------------------------------------------------------------------------------------------------------------------
    | 32768 |    None |    LLDP |   None | 01:23:20:00:00:01 |     None |   None |   None |   None |   None | CONTROLLER |
    ----------------------------------------------------------------------------------------------------------------------

From the prompt we can also check invariants, reorder or drop messages, and
inject other network events such as link failures. Enter `help` for a full list of
commands available in interactive mode.

## Phase II: Troubleshooting

Let's suppose we found a juicy invariant violation. Our InputLogger has
recorded a trace of the network events that we can use to track down the root
cause of the violation.

We can find the raw event trace in the `experiments/fuzz_pox_simple` directory:

    $ ls experiments/fuzz_pox_simple/
    __init__.py                  fuzzer_params.py             mcs_config.py     openflow_replay_config.py    replay_config.py
    events.trace                 interactive_replay_config.py metadata          orig_config.py               simulator.out

The raw event trace is stored in the file `events.trace`. In this directory we find a
number of other useful files: the simulator automatically copies your
configuration parameters (`fuzzer_params.py`, `orig_config.py`), console
output (`simulator.out`), metadata about the state of the system when the
trace was recorded, and new configuration files for replaying the event trace
(`replay_config.py`), minimizing the event trace (`mcs_config.py`), and root
causing the bug (`interactive_replay_config.py`, `openflow_replay_config.py`).

By default, this experiments results directory is inferred from the name of the
config file. You can also specify a custom name with the `-n` parameter to
`simulator.py`. You can optionally specify that each experiment results directory should have a
timestamp appended with the `-t` parameter.

The simplest way to start troubleshooting is by examining the event trace
along with the console output. We rarely want to look at the event trace in its raw form though; we instead use a tool to
parse and format the events:

    $ ./tools/pretty_print_event_trace.py experiments/fuzz_pox_simple/events.trace
    i1 ConnectToControllers (prunable)
    fingerprint:  ()
    --------------------------------------------------------------------
    i2 ControlMessageReceive (prunable)
    fingerprint:  (OFFingerprint{u'class': u'ofp_hello'}, 2, (u'c', u'1'))
    ...

The output of this tool is highly configurable; see the
[documentation](http://ucb-sts.github.io/sts/software_architecture.html#tools) for more
information.

### Replay Mode

Suppose we realize that we need to add more logging statements to the
controller to understand what's going on. With STS's replayer mode, we can add our logging
statements and then replay the same set of network events that triggered the
original violation.

Replayer mode tries as best as it can to inject the network events from the trace
in a way that reproduces the same outcome. It does this in part by maintaining
the relative timing between input events as they appeared originally.
Sometimes though the behavior of the controller can also change during replay. For
example, the operating system may delay or reorder deliver of OpenFlow
messages. For this reason STS also tracks the order and timing of internal
events triggered by the controller software itself, and buffers these internal events
during replay in an attempt to ensure the same causal order of events.

We can replay out trace simply by specifying `replay_config.py` as our
configuration file:


    $ ./simulator.py -c experiments/fuzz_pox_simple/replay_config.py
    ...
    00:01.003 00:00.000 Successfully matched event ConnectToControllers:i1
    00:01.006 00:00.000 Successfully matched event ControlMessageReceive:i2 c1 -> s2 [ofp_hello: ]
    ...

We can now replay as many times as we need to understand the root cause. The
console output and other results from our replay runs can be found in a new
subdirectory `experiments/fuzz_pox_simple_replay/`.

<!-- TODO: mention events.trace.unacked -->

### MCS Finder Mode

Randomly generated event traces often contain a large number of events, many
of which distract us during the troubleshooting process and are not actually relevant for the bug
we are interested in. In such cases we can attempt to minimize the original
event trace, leaving just behind just the events that are directly responsible
for trigger the bug.

STS's MCSFinder mode executes the
[delta debugging](http://www.st.cs.uni-saarland.de/papers/tse2002/tse2002.pdf)
algorithm to minimize the original event log. We can invoke MCSFinder by
specifying the appropriate configuration file:

    $ ./simulator.py -c experiments/fuzz_pox_simple/mcs_config.py

The output of MCSFinder is yet another event trace that we can replay to
continue with our troubleshooting. The results are stored in a new
subdirectory `experiments/fuzz_pox_simple_mcs/`. The minimized event trace can
be found in the `mcs.trace` and `mcs.trace.notimeouts` files. In addition, we
see subdirectories such as `interreplay_1_l_0/`, which store results from
intermediate replays throughout delta debugging's execution. Finally, we can
see statistics about MCSFinder's progress by graphing the data stored in the
`runtime_stats.json` file:

    $ ./runtime_stats/generate_graph.py experiments/fuzz_pox_simple_mcs/runtime_stats.json

The resulting graph will show us the decreasing size of the event trace
throughout the delta debugging's execution:

<img
src="http://www.eecs.berkeley.edu/%7Ercs/research/mcs_runtime.png"
alt="console output">

## Root Causing

The last stage of the troubleshooting process involves understand the
precise circumstances that lead up to the invariant violation. STS includes
several tools to help with this process.

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
directly relevant for triggering an invalid network configuration.

OpenFlowReplayer replays the OpenFlow messages from an event trace, enabling:
  - automatic filtering of flow_mods that timed out or were overwritten by
    later flow_mods.
  - automatic filtering of flow_mods that are irrelevant to a set of flow
    entries specified by the user.
  - interactive bisection of the OpenFlow trace to infer which messages were
    and were not relevant for triggering the bug (especially useful for tricky
    cases requiring human involvement). (TBD)

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
