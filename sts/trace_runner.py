from collections import defaultdict
from functools import partial
from subprocess import Popen
from re import compile, match
import abc

class Context(object):
  """ A class to hold state between calls. The commands that handle the parsed
  data are essentially calls to this, but they handle the string parsing. """
  def __init__(self):
    # procs: A dictionary for mapping names to Popen instances. For controlling
    # external processes such as controllers (e.g. killing them).
    self.procs = {}

  def add_process(self, name, proc):
    self.procs[name] = proc # FIXME need to be safe in case process already exists!

  def stop_process(self, name):
    try:
      self.procs.pop(name).terminate()
    except KeyError:
      pass

def parse(trace_filename):
  ''' Parse a trace file name and return a dictionary of the following type:
  key: round number (int)
  value: list of actions to perform in that round

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
  rgx = compile("^(?P<name>[\w-]+)$")
  parsed = rgx.match(strng)

  if not parsed:
    raise ValueError("start_process could not parse string {}".format(strng))
  context.stop_process(parsed.group('name'))

name2Command = {
  'start-process' : start_process,
  'stop-process' : stop_process
}
