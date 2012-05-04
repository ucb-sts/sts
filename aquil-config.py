from sts.topology_generator import *
from sts.experiment_config_lib import *
controllers = [ Controller(address="aquil", port=6633),
   Controller(address="aquil", port=6634)  
    ]
topology_generator = TopologyGenerator()
topology_generator.connections_per_switch = 2
