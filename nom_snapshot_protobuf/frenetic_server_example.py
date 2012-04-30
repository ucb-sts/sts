        import threading
        class SimulatorHook(threading.Thread):
          _freneticmatch2protomatch = {
            "switch" : nom_snapshot_pb2.Match.switch,
            "inport" : nom_snapshot_pb2.Match.in_port,
            "srcmac" : nom_snapshot_pb2.Match.dl_src,
            "dstmac" : nom_snapshot_pb2.Match.dl_dst,
            "dltype" : nom_snapshot_pb2.Match.dl_type,
            "vlan" : nom_snapshot_pb2.Match.dl_vlan,
            "srcport" : nom_snapshot_pb2.Match.tp_src,
            "dstport" : nom_snapshot_pb2.Match.tp_dst,
            "protocol" : nom_snapshot_pb2.Match.nw_proto,
            "srcip" : nom_snapshot_pb2.Match.nw_src,
            "dstip" : nom_snapshot_pb2.Match.nw_dst,
          }

          _freneticaction2protoaction = {
            "forward" : nom_snapshot_pb2.Action.output,
            # "modify" : TODO,
          }

          def run(self):
            import socket
            print "binding sts socket..."
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('', 6634))
            s.listen(1)
            conn, addr = s.accept()
            print 'Connected by', addr
            while 1:
              data = conn.recv(1024)
              if not data: break
              # TODO: I don't think we need flows?
              # For now, assume response fits into a single packet
              #print "rts_flows:"
              #self.recursive_print(rts.flows)
              #flows = {}
              #for k,v in rts.flows.iteritems():
              #  print "k:", type(k), k
              #  print "v:", type(v), v
              #  flows[k] = v
              #print "rts_switches:"
              #self.recursive_print(rts.switches)
              #print "rts_policy:"
              #self.recursive_print(rts.policy)
              # Policy is:
              #   dpid -> [Rule1, Rule2...]
              # Rule is:
              #   - pattern (FilterPattern)
              #   - actions ([Action1, Actions2...]) 
              # Action is:
              #   - tag (header field name)
              #   - subexprs ([port1, port2...])  # TODO: except for "modify" Action, which is [field name, new value]
              # FilterPattern is:
              #   - tag (header field name)
              #   - subexprs (tuple (polarity, header values))
              #       - polarity (True is ==, False is !=)
              #   - lambda for whether the given header matches
              switches = []
              for dpid,rule_list in rts.policy.configs.iteritems():
                # One match per rule, one or more actions per rule
                sanitized_rule_list = [] 
                for rule in rule_list:
                  # (name, polarity, values)
                  matches = []
                  polarity = rule.pattern.subexprs[0]
                  for value in rule.pattern.subexprs[1]:
                    match = self._freneticmatch2protomatch[rule.pattern.tag]
                    protobuf_match = nom_snapshot_pb2.Match(field=match, polarity=polarity, value=str(value))
                    matches.append(protobuf_match)
                    
                  actions = []
                  for action in rule.actions:
                    for port in action.subexprs:
                      # [(tag, [port1, port2...]), ...]
                      protobuf_tag = self._freneticaction2protoaction[action.tag]
                      protobuf_action = nom_snapshot_pb2.Action(type=protobuf_tag, port=port)
                      actions.append(protobuf_action)
                      
                  for match in matches:
                    sanitized_rule_list.append(nom_snapshot_pb2.Rule(match=match, actions=actions))
                switches.append(nom_snapshot_pb2.Switch(dpid=dpid, rules=sanitized_rule_list))
                
              # TODO: does Frenetic have a notion of Hosts? I hope they do
              snapshot = nom_snapshot_pb2.Snapshot(switches=switches, hosts=[]).SerializeToString()
              print "sending %d byte response..." % len(snapshot)
              conn.sendall(snapshot)

        SimulatorHook().start()
