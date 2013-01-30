#! /usr/bin/python
import re
import sys

path = re.compile("WARN:new link detected [(](00:)+?(?P<from_id>\w{2}) p:(?P<from_port>\w+) -> (00:)+?(?P<to_id>\w{2}) p:(?P<to_port>\w+)")

def make_id(switch_id, port):
  '''make a string id for'''
  return switch_id + ":" + port

argv = sys.argv

if len(argv) != 2:
  print "Please provide exactly one filename argument"
  sys.exit(2)

connectivity = {} # a dict of k,v = from_id, to_id
occupied_ports = {} # k,v = switch_id, set(ports)

with open(argv[1], 'r') as f:
  for line in f:
    m = re.search(path, line)
    if m:
      frm_id = m.group("from_id")
      from_port = m.group("from_port")
      from_id = make_id(frm_id, from_port)
      to_id = make_id(m.group("to_id"), m.group("to_port"))

      if from_id in connectivity:
        print "from_id already connected to", connectivity[from_id]
        print "  this round's to_id:", to_id
        continue

      connectivity[from_id] = to_id

      if not occupied_ports.has_key(frm_id):
        occupied_ports[frm_id] = set()

      occupied_ports[frm_id].add(from_port)

# Now compare the things
print "Path count:", len(connectivity)

def print_link(from_id, to_id):
  '''pretty print the paths from the switch at from_id to all the ids in its to_bag'''
  print "from_id:", from_id, "to_id:", to_id

for from_id, to_id in connectivity.iteritems():
  print "---"
  print_link(from_id, to_id)

  if to_id in connectivity:
    if from_id != connectivity[to_id]:
      print "  Bad reverse path! connectivity[to_id] =", connectivity[to_id]
  else:
    print "  ERROR: no reverse path!"

print "Printing port count"

for switch in sorted(occupied_ports.iterkeys()):
  ports = occupied_ports[switch]
  print switch, ":", sorted(list(ports))
