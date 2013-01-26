#!/bin/bash

user=`whoami`
if [ $user == "cs" ]; then
  user="rcs"
fi
ssh $user@c5.millennium.berkeley.edu "rm -rf /tmp/graphs/* && mkdir -p /tmp/graphs"
scp *gpi *dat $user@c5.millennium.berkeley.edu:/tmp/graphs
ssh $user@c5.millennium.berkeley.edu "cd /tmp/graphs && for F in *gpi; do gnuplot \$F; done"
scp $user@c5.millennium.berkeley.edu:/tmp/graphs/*pdf .

