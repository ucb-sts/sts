See http://ucb-sts.github.com/sts/ for an html version of this file.

Ever had to painstakingly dig through logs to find the one or two inputs that lead your controller software to break? sts seeks to eliminate this need, freeing you to debug the problematic code itself. 

sts is intended for distributed SDN control software such as [Floodlight](http://floodlight.openflowhub.org/).  sts simulates the devices of your network, allowing fine-grained control over the inputs to your unmodified* controller(s). 
 
![sts architecture](http://www.eecs.berkeley.edu/~rcs/research/sts_arch.jpg)

Beyond troubleshooting, sts is also useful as a framework for programmatically generating integration tests.

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

This will boot up pox, generate a FatTree network with 16 hosts, and begin feeding in random inputs.

You can also run sts interactively:

```
$ ./simulator.py -c config.mesh
```

Finally, you can use sts to replay previous executions of your controller and automatically identify fault-inducing inputs:

```
$ ./simulator.py -c config.troubleshoot_pox_l2_learning
```

The config/ directory contains sample configurations. You can specify your own config file by specifying its path:

```
$ ./simulator.py -c config/my_config.py
```

See [config/README](https://github.com/ucb-sts/sts/blob/master/config/README) for more information. 

### Dependencies

sts requires python 2.7+

sts will automatically use [pypy](http://pypy.org/) as its interpreter if you place a pypy/ directory at the top-level of the repository.

To use the replay features of sts, you will need to install and make two dependencies:
```
$ sudo pip install marisa-trie
$ cd sts/headerspace/hassel-c && make -j
```

### Research

For more information about the research behind sts, see our paper [draft](http://www.eecs.berkeley.edu/~rcs/research/sts.pdf). 

### Questions?

Send questions or feedback to: sts-dev@googlegroups.com

*Automatic invariant checking requires an interface to the controllers' view of the network policy.
