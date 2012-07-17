import abc
import re

class Context(object):
  # TODO add docstring
  def __init__(self):
    # procs: A dictionary for mapping names to Popen instances. For controlling
    # external processes such as controllers (e.g. killing them).
    self.procs = {}

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
  command_regex = re.compile("^(?P<round>\d+) (?P<command>[\w-]+)(?: (?P<args>.+))?$")

  round2Command = {}

  with open(trace_filename, 'r') as trace_file:
    for line in trace_file:
      parsed = re.match(command_regex, line)
    if parsed:
      cmd_name = parsed.group('command')
      if cmd_name not in name2Command:
        raise Exception("unknown command", cmd_name)
      cmd = name2Command[cmd_name](parsed.group('args'))

      round = int(parsed.group('round'))
      if round not in round2Command:
        round2Command[round] = [cmd] # TODO is there a pythonic way to have a default dict value?
      else:
        round2Command[round].append(cmd)
    else:
      # FIXME use a logger instead, or maybe fail hard?
      print "unable to parse line:", line

  return round2Command

name2Command = {} #TODO a dictionary to map name(string) to command subclass

class Command(object):
  ''' The base class that represents an action in a the trace, as parsed by the
  parse method above.

  Commands that implement this class must have an operate method that takes the
  context (also in this module). The context holds the state that is passed
  between the successive commands. '''
  __metaclass__ = abc.ABCMeta

  @abc.abstractmethod
  def operate(self, context):
    pass # TODO operate on the context passed
