# Parsing global log files to create a list of Event objects
from re import compile, match

# TODO(sw): make this decorate the event parsers
def check_unique_id(event_id, all_ids):
  '''Check to make sure that event_id is not in all_ids. Throw an exception if
  this invariant does not hold.

  If the invariant does hold, add event_id to all_ids.'''
  if event_id in all_ids:
    raise Exception() # TODO(sw): raise a more informative exception
  all_ids.add(event_id)

def parse_external_event(existing_event_ids, dependent_ids, event_id, rest):
  '''Takes an external event line parsed from the global log file and returns a
  corresponding ExternalEvent object.'''
  check_unique_id(event_id, existing_event_ids)# TODO(sw): pull this out into a decorator
  # TODO(sw): parse 'rest' to extract dependent IDs
  rgx = compile("^\[(?P<dependent_ids>\S+(?: +\S+)*)\] (?P<rest>.*?)$")
  # ensure that dependent IDs haven't occurred yet
  parsed = rgx.match(rest)

  if not parsed:
    raise Exception() # TODO(sw): raise a more informative exception

  dependents = set(parsed.group('dependent_ids').split()) # 2 dependent ids could be the same on accident. deal with it!
  assert(dependents.isdisjoint(existing_event_ids)) # can't have dependencies that have already happened!
  dependent_ids.update(dependents)

  # TODO(sw): deal with other external events

def parse_internal_event(events_ids, dependent_ids, event_id, rest):
  '''Takes an internal event line parsed from the global log file and returns
  a corresponding InternalEvent object.'''
  check_unique_id(event_id, existing_event_ids) # TODO(sw): pull this out into a decorator
  dependent_ids.discard(event_id)
  # TODO(sw): deal with other internal events

def parse(logfile_path):
  '''Input: path to a logfile.

  Output: A list of all the internal and external events in the order in which
  they exist in the logfile. Each internal event is annotated with the set of
  source events that are necessary conditions for its occurence.

  Format for Logfile: Each line is either an internal or external event. Lines
  that do not match the following specification for either are ignored (with a
  warning issued).

  * External: ^e ID [list of dependent IDs] custom$
  * Internal: ^i ID custom$
  
  ID can be any unique non-whitespace identifier.

  The list of source IDs may be empty if the internal event is a source event
  itself. The brackets are part of the literal syntax and not special regex characters.'''
  event_rgx = compile("(?P<type>[ei]) (?P<id>\S+) (?P<rest>.*?)$")

  trace = [] # the return value of the parsed log
  event_ids = set() # a set of all external event ids
  dependent_ids = set() # dependent ids that have to be satisfied by future internal events

  parse_function = {
    'e' : parse_external_event,
    'i' : parse_internal_event
    }

  with open(logfile_path, 'r') as log_file:
    for line in log_file:
      parsed = event_rgx.match(line)
      if parsed:
        parsed = parsed.groupdict()
        event = parse_function[parsed['type']](
          event_ids,
          dependent_ids,
          parsed['id'],
          parsed['rest']
          )
        trace.append(event)

  assert(len(dependent_ids) == 0) # all the foward dependencies should be satisfied!

  return trace
