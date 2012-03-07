'''
Created on Aug 18, 2011

@author: peymankazemian
'''
from pox.lib.headerspace.headerspace.hs import *
from pox.lib.headerspace.headerspace.tf import *
from pox.lib.headerspace.config_parser.cisco_router_parser import *
from pox.lib.headerspace.config_parser.helper import *

cs = ciscoRouter(1)
t = TF(ciscoRouter.HS_FORMAT()["length"]*2)
all_x = byte_array_get_all_x(ciscoRouter.HS_FORMAT()["length"]*2)
cs.set_field(all_x, "vlan", 45, 0)
cs.set_field(all_x, "ip_dst", dotted_ip_to_int("172.168.0.0"), 16)
rule = TF.create_standard_rule([2], all_x, [3], None, None, "", [])
t.add_fwd_rule(rule)
all_x = byte_array_get_all_x(ciscoRouter.HS_FORMAT()["length"]*2)
cs.set_field(all_x, "ip_dst", dotted_ip_to_int("172.168.0.0"), 16)
cs.set_field(all_x, "vlan", 46, 0)
rule = TF.create_standard_rule([2], all_x, [3], None, None, "", [])
t.add_fwd_rule(rule)
t.print_influences()
all_x = byte_array_get_all_x(ciscoRouter.HS_FORMAT()["length"]*2)
h = headerspace(ciscoRouter.HS_FORMAT()["length"]*2)
h.add_hs(all_x)
output = t.T(h,2)
for (h,p) in output:
  print "(%s,%s)"%(h,p)
