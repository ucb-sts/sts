See http://ucb-sts.github.com/sts/ for an html version of this file.

Ever had to manually dig through logs to find the one or two inputs that lead your controller software to break? sts seeks to eliminate this need, freeing you to debug the problematic code itself.

sts simulates the devices of your network, allowing you to easily generate tricky test cases, interactively examine the state of the network, and automatically find the exact inputs that are responsible for triggering a given bug.

![sts architecture](http://www.eecs.berkeley.edu/~rcs/research/sts_arch.jpg)

### Installation

sts depends on [pox](http://www.noxrepo.org/pox/about-pox/). To install sts, you'll just need to clone both repositories:

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

This will boot up pox, generate a 2-node mesh network, and begin feeding in random inputs.

You can also run sts interactively:

```
$ ./simulator.py -c config.interactive
```

You can also use sts to replay previous executions:

```
$ ./simulator.py -c config/pox_list_violation.py
```

Finally, sts is able to identify the minimal set of inputs that trigger a given bug:

```
$ ./simulator.py -c config/pox_list_mcs.py
```

The config/ directory contains sample configurations. You can specify your own config file by passing its path:

```
$ ./simulator.py -c config/my_config.py
```

See [config/README](https://github.com/ucb-sts/sts/blob/master/config/README) for more information.

### Dependencies

sts requires python 2.7+

To use the advanced features of sts, you may need to install and make two dependencies:
```
$ sudo pip install pytrie
$ (cd sts/headerspace/hassel-c && make -j)
```

### Will I need to modify my controller to use sts?

If your controller supports OpenFlow 1.0, sts works out of the box. You'll only need to change one line in the config file to instruct sts how to launch your controller process(es).

### Research

For more information about the research behind sts, see our paper [draft](http://www.eecs.berkeley.edu/~rcs/research/sts.pdf).

### Questions?

Send questions or feedback to: sts-dev@googlegroups.com
