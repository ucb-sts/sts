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

# Note: make sure to add new custom invariant checks to this dictionary!
name_to_invariant_check = {
  "check_for_loops_or_connectivity" : check_for_loops_or_connectivity,
  "InvariantChecker.check_liveness" :  InvariantChecker.check_liveness,
  "InvariantChecker.check_loops" :  InvariantChecker.check_loops,
  "InvariantChecker.python_check_connectivity" :  InvariantChecker.python_check_connectivity,
  "InvariantChecker.check_connectivity" :  InvariantChecker.check_connectivity,
  "InvariantChecker.check_blackholes" :  InvariantChecker.check_blackholes,
  "InvariantChecker.check_correspondence" :  InvariantChecker.check_correspondence,
}
