#!/usr/bin/env python

# Installed from: http://dirtbags.net/py-pcap.html
import pcap
import argparse
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "pox"))
from pox.lib.packet.ethernet import *

def main(args):
  p = pcap.open(args.input)
  for i in p:
    e = ethernet(raw=i[1])
    import pdb; pdb.set_trace()
    print e

if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('-i', '--input')
  parser.add_argument('-o', '--output', default="pcap.trace")

  args = parser.parse_args()
  main(args)
