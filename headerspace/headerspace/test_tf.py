'''
Created on Jun 20, 2011

@author: peymankazemian
'''
from pox.lib.headerspace.headerspace.hs import *
from pox.lib.headerspace.headerspace.tf import *
from pox.lib.headerspace.config_parser.helper import *

def convert(ipsi,ipei):
  ips = ipsi
  ipe = ipei
  match = []
  while (ips <= ipe):
    for i in range(1,32):
      if not ((ips | (2**i - 1 )) <= ipe and (ips % 2**i)==0) :
        obtained_match = "%s/%d"%(int_to_dotted_ip(ips),33-i)
        match.append(obtained_match)
        ips = (ips| (2**(i-1) - 1 )) + 1
        break
  return match

def test_tf_simple():
  mtf = TF(2)

  mtf.add_rewrite_rule(TF.create_standard_rule([1,2,3], "100100xx", [5], "00111111", "01111111","",[]))
  mtf.add_rewrite_rule(TF.create_standard_rule([1,2], "1001xxxx", [5], "00001111", "01101111","",[]))
  mtf.add_fwd_rule(TF.create_standard_rule([1,2], "000011xx", [5], "00111111", "00111111","",[]))
  mtf.add_fwd_rule(TF.create_standard_rule([2,4], "10xxxxxx", [5], None , None,"",[]))
  #mtf.print_influences()

  hs = headerspace(2)
  hs.add_hs(hs_string_to_byte_array("100xxxxx"))
  ans = mtf.T(hs,2)
  for h in ans:
    print "at port %s:\n%s"%(h[1],h[0])

  print "\n-------\nINVERSE\n--------\n"
  ans = mtf.T_inv(hs, 5)
  for h in ans:
    print "at port %s:\n%s"%(h[1],h[0])

  print "\n-------\nAFTER RELOAD\n--------\n"
  mtf.save_object_to_file("qq.txt")
  mtf.load_object_from_file("qq.txt")

  ans = mtf.T(hs,2)
  for h in ans:
    print "at port %s:\n%s"%(h[1],h[0])

  print "\n-------\nINVERSE\n--------\n"
  ans = mtf.T_inv(hs, 5)
  for h in ans:
    print "at port %s:\n%s"%(h[1],h[0])

if __name__ == '__main__':
  test_tf_simple()
