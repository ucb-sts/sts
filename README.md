See http://ucb-sts.github.com/sts/ for an HTML version of this file.

Ever had to manually dig through logs to find the one or two inputs that lead
your controller software to break? sts seeks to eliminate this need, freeing
you to debug the problematic code itself.

sts simulates the devices of your network, allowing you to easily generate
tricky test cases, interactively examine the state of the network, and
automatically find the exact inputs that are responsible for triggering a
given bug.

![sts architecture](http://www.eecs.berkeley.edu/~rcs/research/Debugger_Architecture.jpg)

### Installation

sts depends on [pox](http://www.noxrepo.org/pox/about-pox/). To install sts,
you'll just need to clone both repositories:

```
$ git clone git://github.com/ucb-sts/sts.git
$ cd sts
$ git clone -b debugger git://github.com/noxrepo/pox.git pox/
```

### Running

Take sts for a test drive with:

```
$ ./simulator.py
```

This will boot up pox, generate a 20-switch FatTree network, and begin feeding
in random inputs.

You can also run sts interactively:

```
$ ./simulator.py -c config/interactive.py
```

sts can be used to replay previous executions:

```
$ ./simulator.py -c config/pox_example_replay.py
```

Finally, sts is able to identify the minimal set of inputs that trigger a
given bug:

```
$ ./simulator.py -c config/pox_example_mcs.py
```

You can turn up the verbosity of the simulator's console output by passing the
'-v' flag to simulator.py.

The simulator automatically copies your configuration parameters and console
output into the experiments/ directory for later examination.

The config/ directory contains sample configurations. You can specify your own
config file by passing its path:

```
$ ./simulator.py -c config/my_config.py
```

See [config/README](https://github.com/ucb-sts/sts/blob/master/config/README)
for more information.

### Dependencies

sts requires python 2.7+

To use the advanced features of sts, you may need to install and make two
dependencies:
```
$ sudo pip install pytrie
$ (cd sts/headerspace/hassel-c && make -j)
```

### Will I need to modify my controller to use sts?

If your controller supports OpenFlow 1.0, sts works out of the box. You'll
only need to change one line in the config file to instruct sts how to launch
your controller process(es).

### Documentation

For a high-level overview of STS's software architecture, see this
[page](https://github.com/ucb-sts/sts/blob/master/DOCUMENTATION.md).

For searchable code documentation, see this
[page](http://ucb-sts.github.io/documentation/).

### Research

For more information about the research behind sts, see our paper
[draft](http://www.eecs.berkeley.edu/~rcs/research/sts.pdf) or our talk
[slides](http://www.eecs.berkeley.edu/~rcs/research/selectiverecall.pptx).

### Questions?

Send questions or feedback to: sts-dev@googlegroups.com
