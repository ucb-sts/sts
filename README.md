See http://ucb-sts.github.com/sts/ for an HTML version of this file.

Ever had to manually dig through logs to find the one or two inputs that lead your controller software to break? STS seeks to eliminate this need, freeing you to debug the problematic code itself.

STS simulates the devices of your network, allowing you to easily generate tricky test cases, interactively examine the state of the network, and automatically find the exact inputs that are responsible for triggering a given bug.

![sts architecture](http://www.eecs.berkeley.edu/~rcs/research/Debugger_Architecture.jpg)

### Installation

STS depends on [pox](http://www.noxrepo.org/pox/about-pox/). To install STS, you'll just need to clone both repositories:

```
$ git clone git://github.com/ucb-sts/sts.git
$ cd sts
$ git clone -b debugger git://github.com/noxrepo/pox.git pox/
```

### Running

Take STS for a test drive with:

```
$ ./simulator.py
```

This will boot up pox, generate a 20-switch FatTree network, and begin feeding in random inputs.

You can also run STS interactively:

```
$ ./simulator.py -c config/interactive.py
```

STS can be used to replay previous executions:

```
$ ./simulator.py -c config/pox_example_replay.py
```

Finally, STS is able to identify the minimal set of inputs that trigger a given bug:

```
$ ./simulator.py -c config/pox_example_mcs.py
```

You can turn up the verbosity of the simulator's console output by passing the '-v' flag to simulator.py.

The simulator automatically copies your configuration parameters and console output into the experiments/ directory for later examination.

The config/ directory contains sample configurations. You can specify your own config file by passing its path:

```
$ ./simulator.py -c config/my_config.py
```

See [config/README](https://github.com/ucb-sts/sts/blob/master/config/README) for more information.

### Dependencies

STS requires python 2.7+

To check network invariants with headerspace analysis, you will need to load [hassel](https://bitbucket.org/peymank/hassel-public) as a submodule and build it:
```
$ git submodule init
$ git submodule update
$ (cd sts/hassel/hsa-python && source setup.sh)
$ (cd sts/hassel/hassel-c && make -j)
```

You will need a [bitbucket](https://bitbucket.org/) account in order to clone the submodule. Note also that Hassel-C may not compile on Macintosh computers.

To use the advanced replay features of STS, you may need to install pytrie:
```
$ sudo pip install pytrie
```

If your control software supports distribution, you may need to compile POX's pcap library to enable interposition on messages sent between controllers:
```
# (N.B. depends on the libpcap-dev package)
$ (cd pox/pox/lib/pxcap/pxcap_c && sudo python setup.py build && sudo python setup.py install)
```

Finally, interactive mode depends on the readline module:
```
$ sudo pip install readline
```

### Will I need to modify my controller to use sts?

If your controller supports OpenFlow 1.0, STS works out of the box. You'll only need to change one line in the config file to instruct STS how to launch your controller process(es).

### Documentation

For a high-level overview of STS's software architecture, see this [page](https://github.com/ucb-sts/sts/blob/master/DOCUMENTATION.md).

For searchable code documentation, see this [page](http://ucb-sts.github.io/documentation/).

### Interested in contributing?

Check out this [page](https://github.com/ucb-sts/sts/blob/master/CONTRIBUTE.md).

### Research

For more information about the research behind STS, see our
[short](http://www.eecs.berkeley.edu/~rcs/research/sts_short.pdf) or
[long](http://www.eecs.berkeley.edu/~rcs/research/sts.pdf) paper draft or our talk
[slides](http://www.eecs.berkeley.edu/~rcs/research/selectiverecall.pptx).

### Questions?

Send questions or feedback to: sts-dev@googlegroups.com
