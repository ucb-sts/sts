# Parsing of global log files to create a list of Event objects
from re import compile, match

# TODO make this decorate the event parsers
def check_unique_id(event_id, all_ids):
  '''Check to make sure that event_id is not in all_ids. Throw an exception if
  this invariant does not hold.

  If the invariant does hold, add event_id to all_ids.'''
  if event_id in all_ids:
    raise Exception() # TODO raise a more informative exception
  all_ids.add(event_id)

def parse_external_event(event_ids, event_id, rest):
  '''Takes an external event line parsed from the global log file and returns a
  corresponding ExternalEvent object.'''
  check_unique_id(event_id, event_ids)# TODO pull this out into a decorator
  # TODO deal with other external events

def parse_internal_event(events_ids, event_id, rest):
  '''Takes an internal event line parsed from the global log file and returns
  a corresponding InternalEvent object.'''
  check_unique_id(event_id, event_ids) # TODO pull this out into a decorator
  # TODO deal with other internal events

event_rgx = compile("(?P<type>e|i) (?P<id>\S+) (?P<rest>.*?)$")
def parse(logfile_path):
  '''Input: path to a logfile.

  Output: A list of all the internal and external events in the order in which
  they exist in the logfile. Each internal event is annotated with the set of
  source events that are necessary conditions for its occurence.

  Format for Logfile: Each line is either an internal or external event. Lines
  that do not match the following specification for either are ignored (with a
  warning issued).

  * External: ^e ID custom$
  * Internal: ^i ID [list of source IDs] custom$
  
  ID can be any unique non-whitespace identifier.

  The list of source IDs may be empty if the internal event is a source event
  itself. The brackets are part of the literal syntax and not special regex characters.'''

  trace = [] # the return value of the parsed log
  event_ids = set() # a set of all external event ids

  parse_function = {
    'e' : parse_external_event,
    'i' : parse_internal_event
    }

  with open(logfile_path, 'r') as log_file:
    for line in log_file:
      parsed = match(event_rgx, line)
      if parsed:
        parsed = parsed.groupdict()
        event = parse_function[parsed['type']](
          event_ids,
          parsed['id'],
          parsed['rest']
          )
        trace.append(event)

  return trace
