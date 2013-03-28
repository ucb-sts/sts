from sts.invariant_checker import InvariantChecker

def check_for_loops_or_connectivity(simulation):
  from sts.invariant_checker import InvariantChecker
  result = InvariantChecker.check_loops(simulation)
  if result:
    return result
  result = InvariantChecker.python_check_connectivity(simulation)
  if not result:
    print "Connectivity established - bailing out"
    import sys
    sys.exit(0)
  return []

def check_stale_entries(simulation):
  '''Check wether a (hardcoded) migrated host's old switch has stale routing entries'''
  dpid = 1 # hardcoding host 1
  port_no = 1

  switch = simulation.topology.get_switch(dpid)

  port_down = port_no in switch.down_port_nos
  old_entries = switch.table.entries_for_port(port_no)

  if port_down and len(old_entries) > 0:
    # we have a violation!
    return old_entries

  return []

# Note: make sure to add new custom invariant checks to this dictionary!
name_to_invariant_check = {
  "check_for_loops_or_connectivity" : check_for_loops_or_connectivity,
  "check_stale_entries" : check_stale_entries,
  "InvariantChecker.check_liveness" :  InvariantChecker.check_liveness,
  "InvariantChecker.check_loops" :  InvariantChecker.check_loops,
  "InvariantChecker.python_check_connectivity" :  InvariantChecker.python_check_connectivity,
  "InvariantChecker.check_connectivity" :  InvariantChecker.check_connectivity,
  "InvariantChecker.check_blackholes" :  InvariantChecker.check_blackholes,
  "InvariantChecker.check_correspondence" :  InvariantChecker.check_correspondence,
}
