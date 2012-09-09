'''
Created on Mar 10, 2012

@author: rcs
'''

import headerspace.headerspace.tf as tf
import headerspace.config_parser.openflow_parser as of

# Python, Y U NO HAVE FIND BUILT IN
def find(f, seq):
  """Return first item in sequence where f(item) == True."""
  for item in seq:
    if f(item): 
      return item

def generate_TTF(all_links):
  ''' Takes a list of sts.debugger_entities.Link objects (directed) '''
  ttf = tf.TF(of.HS_FORMAT())
  
  for link in all_links:
    uniq_from_port = of.get_uniq_port_id(link.start_software_switch, link.start_port)
    uniq_to_port = of.get_uniq_port_id(link.end_software_switch, link.end_port)
    rule = tf.TF.create_standard_rule([uniq_from_port], None,[uniq_to_port], None, None)
    ttf.add_link_rule(rule)
    
  print "TTF: %s" % str(ttf)
  return ttf

def generate_NTF(switches):
  ntf = tf.TF(of.HS_FORMAT())
  for switch in switches:
    print "SWITCH", switch
    of.generate_transfer_function(ntf, switch) 
  print "NTF: %s" % str(ntf)
  return ntf

def NTF_from_snapshot(snapshot, real_switches):
  ntf = tf.TF(of.HS_FORMAT())
  for switch in snapshot.switches:
    real_switch = find(lambda sw: sw.dpid == switch.dpid, real_switches)
    of.tf_from_switch(ntf, switch, real_switch) 
  print "NTF: %s" % str(ntf)
  return ntf
