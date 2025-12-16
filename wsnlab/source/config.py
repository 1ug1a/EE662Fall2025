## network properties
BROADCAST_NET_ADDR = 255
BROADCAST_NODE_ADDR = 255


## node properties
NODE_TX_STATIC = True # use base range only for all nodes
NODE_TX_BASE_RANGE = 100  # base transmission range of nodes
NODE_TX_POWER_MULTS = [1.3, 1.1, 1.0, 0.9, 0.8]
NODE_TX_POWER_PROBS = [0.1, 0.2, 0.4, 0.2, 0.1]
NODE_ARRIVAL_MAX = 300  # max time to wake up

## simulation properties
SIM_VISUALIZATION = True  # visualization active
SIM_TITLE = 'Cluster-Tree Mesh Network'  # title of visualization window
SIM_TERRAIN_SIZE = (850, 800)  #terrain size
SIM_SCALE = 1  # scale factor for visualization
SIM_RANDOM_SEED = None  # random seed across the entire simulation
SIM_NODE_COUNT = 100  # node count in simulation
SIM_NODE_PLACING_CELL_SIZE = 75  # cell size to place one node
SIM_DURATION = 2500  # simulation duration in seconds
SIM_TIME_SCALE = 0.01  #  The real time duration of 1 second simualtion time
SIM_FAST_ROOT = True  # root node is activated faster than other nodes

## other network/sim properties
SIM_MAX_CLUSTER_SIZE = None  # max number of nodes in one cluster
SIM_MESH_ROUTING = True  # use mesh routing with tree fallback
SIM_NEIGHBOR_TABLE_HOPS = 5  # max hops away stored in neighbor table
SIM_ROUTING_LOGS = True  # output node logs
SIM_TTL = 32  # time to live for routed packets

## modes
SIM_SEND_RANDOM_DATA = True  # nodes send random data packets to other nodes. used to track routing
SIM_INCLUDE_ROUTERS = True  # (unilaterally) nominate nodes requesting join to CH and turn into Router in between 
SIM_ROUTER_PROMOTION_COOLDOWN = 360  # time units to prevent router promotion after becoming router
SIM_ENERGY_LOSS = False  # enable loss of node energy when sending a packet
SIM_PACKET_LOSS_RATE = 0.00  # self-explanatory
SIM_KILL_NODES = True  # kill a random selection of nodes
SIM_KILL_TIME = 700  # time to kill nodes
SIM_NODES_TO_KILL = 15  # number of nodes to kill
REPAIRING_METHOD = 'ALL_ORPHAN' # 'ALL_ORPHAN', 'FIND_ANOTHER_PARENT'

## application properties
LOGGING = True
HEARTBEAT_INTERVAL = 60
EXPORT_CH_CSV_INTERVAL = 10  # simulation time units;
EXPORT_NEIGHBOR_CSV_INTERVAL = 10  # simulation time units;
