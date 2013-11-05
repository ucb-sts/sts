---
layout: default
title: STS Traffic Generation
subtitle: Guide to generating dataplane traffic in STS.
description: Guide to generating dataplane traffic in STS.
---

STS supports three ways to generate dataplane traffic.

### Random Traffic Generation

By default STS generates ICMP pings between random pairs of hosts in the
network. The ICMP ping is injected at the access link of the source, and sent
through the switches in the network.

In Fuzzer mode, the rate of packet generation is determined by the `traffic_generation_rate`
parameter in [config/fuzzer_params.py](https://github.com/ucb-sts/sts/blob/master/config/fuzzer_params.py).
A value of 0.3 says that each host in the network has a 30% probability of
injecting an IMCP ping to another host every fuzzer round.

In Interactive mode, the command `dp_ping` with no arguments will generate a
new packet, and `dp_ping <hid1> <hid2>` will send a ping between host 1 and
host 2.

See [sts/traffic_generator.py](https://github.com/ucb-sts/sts/blob/master/sts/traffic_generator.py)
for the details of how packets are generated.

### Programmatic Traffic Generation

It is also possible to craft dataplane traces programmatically.
[sts/dataplane_trace/trace_generator.py](https://github.com/ucb-sts/sts/blob/master/sts/dataplane_traces/trace_generator.py)
contains several algorithms for generating synthetic ARP/ICMP exchanges
between hosts.

After a trace is generated with `trace_generator.py`, you can cause STS to use
that trace by specify the path to
it in SimulationConfig. For example:

    SimulationConfig(dataplane_trace="dataplane_traces/ping_pong_same_subnet.trace")

Note that dataplane traces are specific to the topology they were generated
for; if you attempt to run a dataplane trace on a different topology, STS will
raise an exception.

In Fuzzer mode, the rate of packet injection is determined by the
`traffic_inject_interval`, an argument to Fuzzer's initializer. For example,

    Fuzzer(simulation_cfg, traffic_inject_interval=5)

will cause Fuzzer to inject the next element in the trace every 5 rounds.
Note that random traffic generation in Fuzzer mode is mutually exclusive with programmatic
traffic generation; that is, if you specify a dataplane trace, no other
packets will be injected.

In Interactive mode, the `dp_inject` command will inject the next element in
the given trace.

STS comes packaged with several dataplane traces, found in the
[dataplane_trace/](https://github.com/ucb-sts/sts/tree/master/dataplane_traces) subdirectory.

### Network Namespaces

The final and most powerful way to generate dataplane traffic is to make use
of Linux's [network namespaces](http://blog.scottlowe.org/2013/09/04/introducing-linux-network-namespaces/).
Network namespaces provide us with a full networking stack that can respond to
ARP/ICMP and run real networked applications such as Chrome or Apache Web
Server. To use network namespace hosts in our simulated network, we just set a
flag in the topology objection in our configuration file:

    MeshTopology(simulation_cfg, netns_hosts=True)

When we run `simulator.py` with this configuration, we will be presented with
one xterm window per host. From there, we can execute arbitrary bash commands,
and the network namespaces will automatically respond to
packets such as ICMP pings, just as a real host would.

Internally, the network namespace hosts are assigned a virtual interface each.
STS reads and writes to these virtual interfaces to transfer packets to and
from the simulated network.

Note that network namespaces require us to run `simulator.py` as root.

### Concluding Remarks

It is worth noting that traffic generation is only necessary during the bug finding phase, since packets are
logged for the purposes of replay.
