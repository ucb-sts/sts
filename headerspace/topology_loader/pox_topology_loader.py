'''
Created on Mar 10, 2012

@author: rcs
'''

import headerspace.headerspace.tf as tf
import headerspace.config_parser.openflow_parser as of

def generate_TTF(all_links):
  ''' Takes a list of debugger.debugger_entities.Link objects (directed) '''
  ttf = tf.TF(of.HS_FORMAT()["length"]*2)
  
  for link in all_links:
    uniq_from_port = of.get_uniq_port_id(link.start_switch_impl, link.start_port)
    uniq_to_port = of.get_uniq_port_id(link.end_switch_impl, link.end_port)
    rule = tf.TF.create_standard_rule([uniq_from_port], None,[uniq_to_port], None, None)
    ttf.add_link_rule(rule)
    
  return ttf
