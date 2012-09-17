'''
Created on Jan 27, 2011

@author: peyman kazemian
'''
from headerspace.headerspace.hs import *
from headerspace.headerspace.tf import *
from headerspace.config_parser.openflow_parser import get_uniq_port_id

import sys
import glob
import os
import subprocess

# What is a p_node?
# A hash apparently:
#  hdr -> foo
#  port -> foo
#  visits -> foo
def print_p_node(p_node):
    print "-----"
    print p_node["hdr"]
    print p_node["port"]
    print p_node["visits"]
    print "-----"
    
def find_reachability(NTF, TTF, in_port, out_ports, input_pkt):
    paths = []
    propagation = []
 
    p_node = {}
    p_node["hdr"] = input_pkt
    p_node["port"] = in_port
    p_node["visits"] = []
    p_node["hs_history"] = []
    propagation.append(p_node)
        
    while len(propagation)>0:
        #get the next node in propagation graph and apply it to NTF and TTF
        print "Propagation has length: %d"%len(propagation)
        tmp_propagate = []
        for p_node in propagation:
            next_hp = NTF.T(p_node["hdr"],p_node["port"])
            for (next_h,next_ps) in next_hp:
                for next_p in next_ps:
                    if next_p in out_ports:
                        reached = {}
                        reached["hdr"] = next_h
                        reached["port"] = next_p
                        reached["visits"] = list(p_node["visits"])
                        reached["visits"].append(p_node["port"])
                        reached["hs_history"] = list(p_node["hs_history"])
                        paths.append(reached)
                    else:
                        linked = TTF.T(next_h,next_p)
                        for (linked_h,linked_ports) in linked:
                            for linked_p in linked_ports:
                                new_p_node = {}
                                new_p_node["hdr"] = linked_h
                                new_p_node["port"] = linked_p
                                new_p_node["visits"] = list(p_node["visits"])
                                new_p_node["visits"].append(p_node["port"])
                                new_p_node["visits"].append(next_p)
                                new_p_node["hs_history"] = list(p_node["hs_history"])
                                new_p_node["hs_history"].append(p_node["hdr"])
                                if linked_p in out_ports:
                                    paths.append(new_p_node)
                                elif linked_p in new_p_node["visits"]:
                                    print "WARNING: detected a loop - branch aborted: \nHeaderSpace: %s\n Visited Ports: %s\nLast Port %d "%(\
                                        new_p_node["hdr"],new_p_node["visits"],new_p_node["port"])
                                else:
                                    tmp_propagate.append(new_p_node)
        propagation = tmp_propagate
                
    return paths
  
def get_all_x(NTF):
  all_x = byte_array_get_all_x(NTF.length)
  test_pkt = headerspace(NTF.format)
  test_pkt.add_hs(all_x)
  return test_pkt
                    
def detect_loop(NTF, TTF, ports, reverse_map, test_packet = None):
    loops = []
    for port in ports:
        print "port %d is being checked"%port
        propagation = []
        
        # put all-x test packet in propagation graph
        test_pkt = test_packet
        if test_pkt == None:
          test_pkt = get_all_x(NTF)
        
        p_node = {}
        p_node["hdr"] = test_pkt
        p_node["port"] = port
        p_node["visits"] = []
        p_node["hs_history"] = []
        
        propagation.append(p_node)
        while len(propagation)>0:
            #get the next node in propagation graph and apply it to NTF and TTF
            print "Propagation has length: %d"%len(propagation)
            tmp_propag = []
            for p_node in propagation:
                # hp is "header port"
                next_hp = NTF.T(p_node["hdr"],p_node["port"])
                for (next_h,next_ps) in next_hp:
                    for next_p in next_ps:
                        linked = TTF.T(next_h,next_p)
                        for (linked_h,linked_ports) in linked:
                            for linked_p in linked_ports:
                                new_p_node = {}
                                new_p_node["hdr"] = linked_h
                                new_p_node["port"] = linked_p
                                new_p_node["visits"] = list(p_node["visits"])
                                new_p_node["visits"].append(p_node["port"])
                                #new_p_node["visits"].append(next_p)
                                new_p_node["hs_history"] = list(p_node["hs_history"])
                                new_p_node["hs_history"].append(p_node["hdr"])
                                #print new_p_node
                                if len(new_p_node["visits"]) > 0 and new_p_node["visits"][0] == linked_p:
                                    loops.append(new_p_node)
                                    print "loop detected"
                                elif linked_p in new_p_node["visits"]:
#                                    if (linked_p not in ports):
#                                        print "WARNING: detected a loop whose port is not in checked ports - branch aborted:"
#                                        print_loops([new_p_node],reverse_map)
#                                        print "END OF WARNING"
                                    pass
                                else:
                                    tmp_propag.append(new_p_node)
            propagation = tmp_propag
    return loops

# TODO(cs): make this a parameter
# TODO(cs): don't assume that cwd is the sts top directory
HASSEL_C_PATH = "./headerspace/hassel-c"
HASSEL_TF_PATH = HASSEL_C_PATH + "/tfs/sts"

# Omega defines the externally visible behavior of the network. Defined as a table:
#   (header space, edge_port) -> [(header_space, final_location),(header_space, final_location)...]
def compute_omega(name_tf_pairs, TTF, edge_links):
  omega = {}

  # Nuke old TF object files
  old_tfs = glob.glob(HASSEL_TF_PATH + "/*tf")
  for path in old_tfs:
    os.unlink(path)

  # Write out TF for each switch, and TTF to object files
  for name, tf in name_tf_pairs:
    tf.save_object_to_file(HASSEL_TF_PATH + "/" + name + ".tf")
  TTF.save_object_to_file(HASSEL_TF_PATH + "/topology.tf")

  # Generate the .dat file
  # Make sure we're in the right cwd
  old_cwd = os.getcwd()
  os.chdir(HASSEL_C_PATH)
  os.system("./gen sts")

  # TODO(cs): need to model host end of link, or does switch end suffice?
  edge_ports = map(lambda access_link: get_uniq_port_id(access_link.switch, access_link.switch_port), edge_links)
  print "edge_ports: %s" % edge_ports
  
  for start_port in edge_ports:
    port_omega = compute_single_omega(start_port, edge_ports)
    omega = dict(omega.items() + port_omega.items()) 
  
  os.chdir(old_cwd)
  return omega
    
def compute_single_omega(start_port, edge_ports):
    if type(start_port) != int:
      start_port = get_uniq_port_id(start_port.switch, start_port.switch_port)
      
    if type(edge_ports) != list:
      edge_ports = list(edge_ports)
    if type(edge_ports[0]) != int:
      edge_ports = map(lambda access_link: get_uniq_port_id(access_link.switch, access_link.switch_port), edge_ports)
    
    print "port %d is being checked" % start_port
    
    str_start_port = str(start_port)
    str_edge_ports = map(str, edge_ports)
    proc = subprocess.Popen(["./sts", str(start_port)] + str_edge_ports,
                            stdout=subprocess.PIPE)
    while True:
      line = proc.stdout.readline()
      if line != '':
        print line
      else:
        break

    return {}

def print_reachability(paths, reverse_map):
    for p_node in paths:
        str = ""
        for port in p_node["visits"]:
            if str == "":
                str = reverse_map["%d"%port]
            else:
                str = "%s ---> %s"%(str,reverse_map["%d"%port])
        str = "%s ---> %s"%(str,reverse_map["%d"%p_node["port"]])
        print "Path: %s"%str
        print "HS Received: %s"%p_node["hdr"]
        print "----------------------------------------------"
        
def print_loops(loops, reverse_map):
    for p_node in loops:
        print "----------------------------------------------"
        str = ""
        for port in p_node["visits"]:
            if str == "":
                str = reverse_map["%d"%port]
            else:
                str = "%s ---> %s"%(str,reverse_map["%d"%port])
        str = "%s ---> %s"%(str,reverse_map["%d"%p_node["port"]])
        print "Path: %s"%str
        rl_id =  "applied rules: "
        for (n,r,s) in p_node["hdr"].applied_rule_ids:
            rl_id = rl_id + " -> %s"%r
        print rl_id
        for i in range(len(p_node["hs_history"])):
            print "*** %d) AT PORT: %s\nHS: %s\n"%(i,reverse_map["%d"%p_node["visits"][i]],p_node["hs_history"][i])
        print "*** %d) AT PORT: %s\nHS: %s\n"%(i+1,reverse_map["%d"%p_node["port"]],p_node["hdr"])
        print "----------------------------------------------"
        
        
def loop_path_to_str(p_node, reverse_map):
    str = ""
    for port in p_node["visits"]:
        if str == "":
            str = reverse_map["%d"%port]
        else:
            str = "%s ---> %s"%(str,reverse_map["%d"%port])
    str = "%s ---> %s"%(str,reverse_map["%d"%p_node["port"]])
    return str
        
def trace_hs_back(applied_rule_list,hs,last_port):
    port = last_port
    hs_list = [hs]
    hs.applied_rule_ids = []
    for (tf,rule_id,in_port) in reversed(applied_rule_list):
        tmp = []
        for next_hs in hs_list:
            hp = tf.T_inv_rule(rule_id,next_hs,port)
            for (h,p_list) in hp:
                if in_port in p_list:
                    tmp.append(h)
        if tmp == []:
            break
        hs_list = tmp
        port = in_port
    return hs_list
        
        
def find_loop_original_header(NTF,TTF,propagation_node):
    applied_rule_ids = list(propagation_node["hdr"].applied_rule_ids)
    hs_list = trace_hs_back(applied_rule_ids,propagation_node["hdr"],propagation_node["port"])
    return hs_list
        
#def is_loop_infinite(NTF, TTF, propagation_node):
#    p_node = propagation_node
#    header_cpy = p_node["hdr"].copy()
#    while len(p_node['visits']) > 0:
#        cur_port = p_node['visits'].pop()
#        
#         transfer back on the link
#        linked = TTF.T_inv(p_node["hdr"],p_node["port"])
#        
#         transfer back on node
#        prev_hp = NTF.T_inv(linked[0][0],linked[0][1])
#        
#        prev_hs = headerspace(NTF.length)
#        for (h,p) in prev_hp:
#            if p == cur_port:
#                prev_hs.add_hs(h)
#        
#        p_node["hdr"] = prev_hs
#        p_node["port"] = cur_port
        
    #print "hret = %s and"%propagation_node["hdr"]
    #print "hret_inv = %s"%(p_node["hdr"])    
#    if propagation_node["hdr"].is_subset_of(p_node["hdr"]):
#        return (True,p_node["hdr"])
#    else:
#        insect = propagation_node["hdr"].copy_intersect(p_node["hdr"])
#        if insect.count() == 0:
#            return (False,[])
#        else:
#            new_cpy = propagation_node.copy()
#            new_cpy["hdr"] = insect
#            return is_loop_infinite(NTF, TTF, new_cpy)
                 
        
