from collections import defaultdict
from functools import partial
from subprocess import Popen
from re import compile, match
import abc
import urllib2
import json

class Context(object):
  """ A class to hold state between calls. The commands that handle the parsed
  data are essentially calls to this, but they handle the string parsing. """
  def __init__(self, simulator):
    # procs: A dictionary for mapping names to Popen instances. For controlling
    # external processes such as controllers (e.g. killing them).
    self.procs = {}
    self.simulator = simulator # this should be a FuzzTester instance

  def add_process(self, name, proc):
    self.procs[name] = proc # HACK this should be made safe in case process already exists!

  def stop_process(self, name):
    try:
      self.procs.pop(name).terminate()
    except KeyError:
      pass

  def kill_process(self, name):
    try:
      self.procs.pop(name).kill()
    except KeyError:
      pass

  def start_switch(self, switch_index, ports=[]):
    self.simulator.start_switch(switch_index, ports)

  def stop_switch(self, switch_index):
    self.simulator.stop_switch(switch_index)

  def check_correspondence(self, port):
    self.simulator.check_correspondence(port)

  def exit_simulator(self):
    self.simulator.stop()

  def boot_topology(self):
    self.simulator.setup_topology()

def parse(trace_filename):
  ''' Parse a trace file name and return a dictionary of the following type:
  key: round number (int)
  value: list of actions to perform in that round

  The idea is that every round, the simulator will check the returned dict to
  see if there are any event in the round, and it will apply them in order.

  Command syntax: The commands must follow this rough syntax. See regex in
  source for more detail:

    ^round_num command args$

  The round number must be an int and groups the actions into rounds to be
  executed in the simulator. These round numbers do *not* have to be strictly
  monotonically increasing, but within each round the actions will be sorted in file-order.
  '''
  command_regex = compile("^(?P<round>\d+) (?P<command>[\w-]+)(?: (?P<args>.+))?$")

  round2Command = defaultdict(list)

  with open(trace_filename, 'r') as trace_file:
    for line in trace_file:
      parsed = match(command_regex, line)
    if parsed:
      cmd_name = parsed.group('command')
      if cmd_name not in name2Command:
        raise Exception("unknown command", cmd_name)
      cmd = partial(name2Command[cmd_name],parsed.group('args'))

      round = int(parsed.group('round'))
      round2Command[round].append(cmd)
    else:
      # FIXME use a logger instead, or maybe fail hard?
      print "unable to parse line:", line

  return round2Command

# Defining a command
#
# Every command takes 2 arguments: a string and a context instance. The string
# is partially applied when parsing is done, and the context is passed in the
# execution of the trace.
#
# Some of the commands may check their arguments with a regex. If they fail to
# parse, many will throw a ValueError.

def start_process(strng, context):
  rgx = compile("^(?P<name>[\w-]+) (?P<cmd>.+)$")
  parsed = rgx.match(strng)

  if not parsed:
    raise ValueError("start_process could not parse string {}".format(strng))
  proc = Popen(parsed.group('cmd').split())
  context.add_process(parsed.group('name'), proc)

def stop_process(strng, context):
  rgx = compile("^(?P<name>[\w-]+)(?: (?P<signal>SIG(?:(?:TERM)|(?:KILL))))?$")
  parsed = rgx.match(strng)

  if not parsed:
    raise ValueError("stop_process could not parse string {}".format(strng))

  signal = parsed.group('signal')
  name = parsed.group('name')
  if signal == "KILL": # use SIGTERM by default
    context.kill_process(name)
  else:
    context.stop_process(name)

def boot_topology(strng, context):
  context.boot_topology()

def stop_switch(strng, context):
  switch_index = int(strng) # let it crash
  context.stop_switch(switch_index)

def start_switch(strng, context):
  rgx = compile("^(?P<switchidx>\d+) (?P<port>\d+)$") # FIXME this is a hack to get it out the door
  parsed = rgx.match(strng)

  if not parsed:
    raise ValueError("start_switch could not parse string {}".format(strng))

  switch_index = int(parsed.group('switchidx'))
  port_number = int(parsed.group('port'))

  context.start_switch(switch_index=switch_index,
                       ports=[port_number])

def change_role(strng, context):
  rgx = compile("^(?P<port>\d+) (?P<role>\[A-Z]+)$")
  parsed = rgx.match(strng)

  if not parsed:
    raise ValueError("change_role could not parse string {}".format(strng))

  floodlight_port = int(parsed.group('port'))
  floodlight_role = int(parsed.group('role'))

  request_data = json.dumps({"role" : floodlight_role})
  url = "http://localhost:{0}/wm/core/role/json".format(floodlight_port)
  req = urllib2.Request(url, request_data, {'Content-Type': 'application/json',
                                            'Accept': 'application/json'})
  response = urllib2.urlopen(req) # HACK don't worry about the response

def check_correspondence(strng, context):
  context.check_correspondence(int(strng))

def exit(strng, context):
  context.exit_simulator()

name2Command = {
  'start-process' : start_process,
  'stop-process' : stop_process,
  'boot-topology' : boot_topology,
  'stop-switch' : stop_switch,
  'start-switch' : start_switch,
  'change-role' : change_role,
  'check-correspondence' : check_correspondence,
  'exit' : exit
}
