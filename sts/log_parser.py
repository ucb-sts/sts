# Parsing of global log files to create a list of Event objects
from re import compile, match

def parse_external_event(external_events, id, rest):
  '''Takes an external event line parsed from the global log file and returns a
  corresponding ExternalEvent object.'''
  if id in external_events:
    raise Exception() # TODO raise a more informative exception

  # TODO demux on the rest to create different external events later
  external_events.add(id) # do last in case external event creation errors

def parse_internal_event(external_events, dependency_id, rest):
  '''Takes an internal event line parsed from the global log file and returns
  a corresponding InternalEvent object.'''
  if id not in external_events:
    raise Exception() # TODO raise a more informative exception

  # TODO demux on the rest to create different internal events later

event_rgx = compile("(?P<type>e|i) (?P<id>\S+) (?P<rest>.*?)$")
def parse(logfile_path):
  '''Input: path to a logfile.

  Output: A list of all the internal and external events in the order in which
  they exist in the logfile. Each internal event is annotated with the single
  (for now) external event that it depends on.

  Format for Logfile: Each line is either an internal or external event. Lines
  that do not match the following specification for either are ignored (with a
  warning issued).

  * External: ^e ID custom$
  * Internal: ^i ID_of_external_dependency custom$

  ID can be any unique non-whitespace identifier.'''

  trace = [] # the return value of the parsed log
  external_events = set() # a set of all external event ids

  parse_function = {
    'e' : parse_external_event,
    'i' : parse_internal_event
    }

  with open(logfile_path, 'r') as log_file:
    for line in log_file:
      parsed = match(event_rgx, line)
      if parsed:
        parsed = parsed.groupdict()
        trace.append(parse_function[parsed['type']](
          external_events,
          parsed['id'],
          parsed['rest']
          )

  return trace
