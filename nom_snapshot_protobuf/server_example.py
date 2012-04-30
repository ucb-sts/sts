import threading
import socket
import nom_snapshot_pb2

class SimulatorHook(threading.Thread):
  def run(self):
    print "binding simulator socket..."
    # TODO: use an RPC framework...
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', 6634))
    s.listen(1)
    conn, addr = s.accept()
    print 'Connected by', addr
    while 1:
      data = conn.recv(1024)
      if not data: break
      test_action = Action(type=Action.output, port=2)
      field_match = Match.FieldMatch(field=Match.dl_src, value="1")
      test_match = Match(field_matches=[field_match], polarity=False)
      test_rule = Rule(match=test_match, actions=[test_action])
      test_switch = Switch(dpid=1, rules=[test_rule])
      test_host = Host(mac="00:00:00:00:00:00")
      test_snapshot = Snapshot(switches=[test_switch], hosts=[test_host])
      print "sending %d byte response..." % len(test_snapshot)
      conn.sendall(snapshot)

SimulatorHook().start()
