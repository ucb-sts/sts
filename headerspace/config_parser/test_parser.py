'''
Created on Jul 5, 2011

@author: peymankazemian
'''
from pox.lib.headerspace.headerspace.tf import *
from pox.lib.headerspace.headerspace.hs import *
from pox.lib.headerspace.config_parser.cisco_router_parser import ciscoRouter,dotted_ip_to_int
from time import time, clock

if __name__ == '__main__':
  f = TF(1)
  f.load_object_from_file("cisco_tf")
  f.activate_hash_table([15,14])

  cs = ciscoRouter(1)
  all_x = byte_array_get_all_x(ciscoRouter.HS_FORMAT()["length"]*2)
  hs = headerspace(ciscoRouter.HS_FORMAT()["length"]*2)
  cs.set_field(all_x, "ip_dst", dotted_ip_to_int("171.67.12.0"), 8)
  hs.add_hs(all_x)

  st = time()
  r = f.T(hs, 100000)
  en = time()
  for (h,p) in r:
    print "HS: %s - at port %s"%(h,p)
    print "rule %s"%h.applied_rule_ids
  print en-st
