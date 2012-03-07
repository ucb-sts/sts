'''
Created on Jul 27, 2011

@author: peymankazemian
'''
from pox.lib.headerspace.config_parser.helper import *
from pox.lib.headerspace.headerspace.hs import *
ip0 = (0x80000000,1,"eth0")
ip1 = (0x02030400,24,"eth0")
ip2 = (0x02030500,24,"eth0")
ip3 = (0x02030600,24,"eth0")
ip4 = (0x02030700,24,"eth0")
ip5 = (0x02030446,29,"eth1")
ip6 = (0x02030446,31,"eth0")

ip_list = [ip1,ip2, ip3,ip4,ip5,ip6]
n = compress_ip_list(ip_list)

for elem in n:
  str = "%s/%d: action: %s compressing: "%(int_to_dotted_ip(elem[0]) , elem[1], elem[2])
  for e in elem[3]:
    str = str + int_to_dotted_ip(e[0]) + "/%d, "%e[1]
  print str

ip0 = (dotted_ip_to_int("46.0.0.0"),16,"eth0")
ip1 = (dotted_ip_to_int("46.0.4.0"),22,"eth0")
ip2 = (dotted_ip_to_int("46.0.8.0"),22,"eth0")
ip3 = (dotted_ip_to_int("46.0.12.0"),22,"eth0")
ip_list = [ip1,ip2, ip3,ip0]
n = compress_ip_list(ip_list)
for elem in n:
  str = "%s/%d: action: %s compressing: "%(int_to_dotted_ip(elem[0]) , elem[1], elem[2])
  for e in elem[3]:
    str = str + int_to_dotted_ip(e[0]) + "/%d, "%e[1]
  print str
