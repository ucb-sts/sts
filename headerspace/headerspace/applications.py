'''
Created on Jan 27, 2011

@author: peyman kazemian
'''
from pox.lib.headerspace.headerspace.hs import *
from pox.lib.headerspace.headerspace.tf import *

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
  test_pkt = headerspace(NTF.length)
  test_pkt.add_hs(all_x)
                    
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

# Omega defines the externally visible behavior of the network. Defined as a table:
#   (header space, edge_port) -> [(header_space, final_location),(header_space, final_location)...]
def compute_omega(NTF, TTF, edge_ports, reverse_map, test_packet = None):
  omega = {}
  
  for start_port in edge_ports:
    print "port %d is being checked" % start_port
    propagation = []
    
    # put all-x test packet in propagation graph
    test_pkt = test_packet
    if test_pkt == None:
      test_pkt = get_all_x(NTF)
        
    p_node = {}
    p_node["hdr"] = test_pkt
    p_node["port"] = start_port
    p_node["visits"] = []
    p_node["hs_history"] = []
        
    propagation.append(p_node)
    while len(propagation) > 0: # TODO: is this stopping condition correct?!!!
      # get the next node in propagation graph and apply it to NTF and TTF
      print "Propagation has length: %d" % len(propagation)
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
                  
                # TODO: perhaps this check needs to come before computing TTF?
                if next_p in edge_ports:
                  # We've reached our final destination!
                  # ASSUMPTION: no edge port will send it back out into the network...
              
                  # TODO: the other possibility for final destination is a dropped packet...
                  #       I believe that is represented as a null header space... Do I need to
                  #       worry about that? Or do NTF/TTF take care of that for me?
               
                  # use the inverse T trick to get original headerspace which led us here
                  original_headers = find_loop_original_header(NTF,TTF,new_p_node)
                  for original_header in original_headers:
                    key = (original_header, start_port)
                    if not key in omega:
                      # TODO: python default value for hash?
                      omega[key] = []
                    omega[key].append((next_h, next_p))
                    
                if linked_p in new_p_node["visits"]:
                  print "WARNING: detected a loop - branch aborted: \nHeaderSpace: %s\n Visited Ports: %s\nLast Port %d "%(\
                         new_p_node["hdr"],new_p_node["visits"],new_p_node["port"])
                else:
                  tmp_propag.append(new_p_node) 
      propagation = tmp_propag
    return omega
  
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
                 
        
