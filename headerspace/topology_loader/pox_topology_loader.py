'''
Created on Mar 10, 2012

@author: rcs
'''

import headerspace.headerspace.tf as tf
import headerspace.config_parser.openflow_parser as of

def generate_TTF(all_links):
  ''' Takes a list of sts.debugger_entities.Link objects (directed) '''
  ttf = tf.TF(of.HS_FORMAT())
  
  for link in all_links:
    uniq_from_port = of.get_uniq_port_id(link.start_switch_impl, link.start_port)
    uniq_to_port = of.get_uniq_port_id(link.end_switch_impl, link.end_port)
    rule = tf.TF.create_standard_rule([uniq_from_port], None,[uniq_to_port], None, None)
    ttf.add_link_rule(rule)
    
  print "TTF: %s" % str(ttf)
  return ttf

def generate_NTF(switches):
  ntf = tf.TF(of.HS_FORMAT())
  for switch in switches:
    of.generate_transfer_function(ntf, switch) 
  print "NTF: %s" % str(ntf)
  return ntf
    