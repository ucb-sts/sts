'''
Created on Jun 20, 2011

@author: peymankazemian
'''

from pox.lib.headerspace.headerspace.hs import *
from pox.lib.headerspace.headerspace.wildcard_dictionary import *

def test_hs_simple():
  hs = headerspace(2)
  hs.add_hs(hs_string_to_byte_array("101xxxxx"))
  hs.add_hs(hs_string_to_byte_array("0010xxxx"))
  hs.diff_hs(hs_string_to_byte_array("1010011x"))
  hs.diff_hs(hs_string_to_byte_array("1010xxx0"))
  print hs
  hs.self_diff()
  print " = "
  print hs

if __name__ == '__main__':
  #test_hs_simple()

  hs = headerspace(4)
  hs.add_hs(hs_string_to_byte_array("0101000110001001"))
  hs.diff_hs(hs_string_to_byte_array("0101000110001001"))
  print byte_array_equal(hs_string_to_byte_array("0101000110001001"),hs_string_to_byte_array("0101000110001001"))
  hs.clean_up()
  print hs
  print byte_array_subset(hs_string_to_byte_array("0101000110001001"),hs_string_to_byte_array("0101000110001001"))

  wcd = wildcard_dictionary(4,30)
  wcd.add_entry([0x55, 0x66],1)
  wcd.add_entry([0x57, 0x65],2)
  wcd.add_entry([0x75, 0x56],3)
  wcd.add_entry([0x77, 0xaa],4)
  wcd.add_entry([0xff, 0xff],5)
  print wcd.find_entry([0x55, 0xff])
  wcd.self_print()
