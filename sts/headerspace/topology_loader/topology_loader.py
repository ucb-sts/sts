'''
Created on Mar 10, 2012

@author: rcs
'''

import sts.headerspace.headerspace.tf as tf
import sts.headerspace.config_parser.openflow_parser as of
from sts.util.convenience import find

import logging
log = logging.getLogger("topology_loader")

def generate_TTF(all_links):
  ''' Takes a list of sts.debugger_entities.Link objects (directed) '''
  ttf = tf.TF(of.HS_FORMAT())

  for link in all_links:
    uniq_from_port = of.get_uniq_port_id(link.start_software_switch, link.start_port)
    uniq_to_port = of.get_uniq_port_id(link.end_software_switch, link.end_port)
    rule = tf.TF.create_standard_rule([uniq_from_port], None,[uniq_to_port], None, None)
    ttf.add_link_rule(rule)

  log.debug("topology transfer function (links): %s" % str(ttf))
  return ttf

def generate_NTF(switches):
  ntf = tf.TF(of.HS_FORMAT())
  for switch in switches:
    of.generate_transfer_function(ntf, switch)
  log.debug("network transfer function (routing entries): %s" %
            str(ntf))
  return ntf

def generate_tf_pairs(switches):
  name_tf_pairs = []
  for switch in switches:
    switch_tf = tf.TF(of.HS_FORMAT())
    of.generate_transfer_function(switch_tf, switch)
    name_tf_pairs.append((switch.name, switch_tf))
    log.debug("transfer function: %s" % str(switch_tf))
  return name_tf_pairs

def tf_pairs_from_snapshot(snapshot, real_switches):
  name_tf_pairs = []
  for switch in snapshot.switches:
    real_switch = find(lambda sw: sw.dpid == switch.dpid, real_switches)
    if real_switch is None:
      log.warn("Could not find switch dpid {} in the physical network. Ignoring.", switch.dpid)
      continue

    switch_tf = tf.TF(of.HS_FORMAT())
    of.tf_from_switch(switch_tf, switch, real_switch)
    name_tf_pairs.append((switch.name, switch_tf))
    log.debug("transfer function: %s" % str(switch_tf))
  return name_tf_pairs

