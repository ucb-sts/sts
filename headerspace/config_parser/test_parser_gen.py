from cisco_router_parser import ciscoRouter
from pox.lib.headerspace.headerspace.tf import *

if __name__ == '__main__':
  cs = ciscoRouter(1)
  tf = TF(cs.HS_FORMAT()["length"]*2)
  cs.read_arp_table_file("examples/Cisco_rtr1/rtr1_arp_table.txt")
  cs.read_mac_table_file("examples/Cisco_rtr1/rtr1_mac_table.txt")
  cs.read_config_file("examples/Cisco_rtr1/rtr1_config.txt")
  cs.read_spanning_tree_file("examples/Cisco_rtr1/rtr1_spanning_tree.txt")
  cs.read_route_file("examples/Cisco_rtr1/rtr1_route.txt")
  cs.generate_port_ids([])
  print cs.fwd_table[26]
  cs.optimize_forwarding_table()
  print cs.vlan_ports
  print cs.config_vlans
  cs.generate_transfer_function(tf)

  tf.save_object_to_file("cisco_tf")
