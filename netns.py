import sys
import subprocess

"""
A useful script for configuring the guest side of the network and ping a single ip address.

Expects 3 arguments

sys.argv[1] the name of the interface to configure
sys.argv[2] the string to pass to ifconfig to configure the network
sys.argv[3] the argument to pass to ping (preferably an ip address)
"""

subprocess.check_call(['ifconfig', sys.argv[1], 'up', sys.argv[2]])
subprocess.check_call(['ping', '-c', '1', sys.argv[3]])
