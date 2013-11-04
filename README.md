See http://ucb-sts.github.com/sts/ for an HTML version of this file.

Ever had to manually dig through logs to find the one or two inputs that lead
your controller software to break? STS seeks to eliminate this need, freeing
you to debug the problematic code itself. 

STS simulates the devices of your network, allowing you to easily generate
tricky test cases, interactively examine the state of the network, and
automatically find the exact inputs that are responsible for triggering a
given bug.

![sts
architecture](http://www.eecs.berkeley.edu/~rcs/research/Debugger_Architecture.jpg)

### Installation

STS depends on [pox](http://www.noxrepo.org/pox/about-pox/). To install STS,
you'll just need to clone both repositories:

```
$ git clone git://github.com/ucb-sts/sts.git
$ cd sts
$ git clone -b debugger git://github.com/ucb-sts/pox.git
```

### Running STS

For a detailed step-by-step walkthrough of STS's use cases, see this
[page](http://ucb-sts.github.io/sts/walkthrough).

For the impatient, take STS for a test drive with:

```
$ ./simulator.py
```

This will boot up pox, generate a 20-switch FatTree network, and begin feeding
in random inputs.

You can also run STS interactively:

```
$ ./simulator.py -c config/interactive.py
```

STS can be used to replay previous executions:

```
$ ./simulator.py -c config/pox_example_replay.py
```

Finally, STS is able to identify the minimal set of inputs that trigger a
given bug:

```
$ ./simulator.py -c config/pox_example_mcs.py
```

You can turn up the verbosity of the simulator's console output by passing the
'-v' flag to simulator.py. 

### Configuring your own experiments

The simulator automatically copies your configuration parameters, event logs,
and console output into the experiments/ directory for later examination.

The config/ directory contains sample configurations. You can specify your own
config file by passing its path:

```
$ ./simulator.py -c config/my_config.py
```

See [config/README](https://github.com/ucb-sts/sts/blob/master/config/README)
for more information on how to write configuration files. 

### Dependencies

STS requires python 2.7+

To check network invariants with headerspace analysis, you will need to load
[hassel](https://bitbucket.org/peymank/hassel-public) as a submodule and build
it: 
```
$ git submodule init 
$ git submodule update
$ (cd sts/hassel/hsa-python && source setup.sh)
$ (cd sts/hassel/hassel-c && make -j)
```

You will need a [bitbucket](https://bitbucket.org/) account in order to clone
the submodule. Note also that Hassel-C may not compile on Macintosh computers.

To use the advanced replay features of STS, you may need to install pytrie:
```
$ sudo pip install pytrie
```

Finally, interactive mode depends on the readline module:
```
$ sudo pip install readline
```

### Will I need to modify my controller to use sts?

If your controller supports OpenFlow 1.0, STS works out of the box. You'll
only need to change one line in the config file to instruct STS how to launch
your controller process(es).

### Documentation

For a high-level overview of STS's software architecture, see this
[page](http://ucb-sts.github.io/sts/software_architecture.html).

For searchable code documentation, see this
[page](http://ucb-sts.github.io/documentation/).

### Interested in contributing?

Check out this [page](http://ucb-sts.github.io/sts/contribute.html).

### Research

For more information about the research behind STS, see our 
[short](http://www.eecs.berkeley.edu/~rcs/research/sts_short.pdf) or 
[long](http://www.eecs.berkeley.edu/~rcs/research/sts.pdf) paper draft or our
talk
[slides](http://www.eecs.berkeley.edu/~rcs/research/selectiverecall.pptx).

You should also check out our collection of replayable
experiments that have been used to find and troubleshoot real bugs in SDN
controllers:
```
$ git clone git@github.com:ucb-sts/experiments.git
```

### Questions?

Send questions or feedback to: sts-dev@googlegroups.com
