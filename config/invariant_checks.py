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




