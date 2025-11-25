## network properties
BROADCAST_NET_ADDR = 255
BROADCAST_NODE_ADDR = 255


## node properties
NODE_TX_STATIC = True
NODE_TX_BASE_RANGE = 100  # base transmission range of nodes
NODE_TX_POWER_MULTS = [1.58, 1.41, 1.26, 1.12, 1.00, 0.89, 0.79, 0.71, 0.63]
NODE_TX_POWER_PROBS = [0.01, 0.03, 0.10, 0.22, 0.28, 0.22, 0.10, 0.03, 0.01]
NODE_ARRIVAL_MAX = 300  # max time to wake up

## simulation properties
SIM_VISUALIZATION = True  # visualization active
SIM_TITLE = 'Cluster-Mesh Network'  # title of visualization window
SIM_TERRAIN_SIZE = (850, 800)  #terrain size
#SIM_TERRAIN_SIZE = (550, 500)  #terrain size
SIM_SCALE = 1  # scale factor for visualization
SIM_RANDOM_SEED = 127
SIM_NODE_COUNT = 100  # node count in simulation
SIM_NODE_PLACING_CELL_SIZE = 75  # cell size to place one node
SIM_DURATION = 410  # simulation duration in seconds
SIM_DURATION = 1500
SIM_TIME_SCALE = 0.01  #  The real time duration of 1 second simualtion time
SIM_FAST_ROOT = True  # root node is activated faster than other nodes

## other network/sim properties
SIM_MAX_CLUSTER_SIZE = None  # max number of nodes in one cluster
SIM_NEIGHBOR_TABLE_HOPS = 4
SIM_ROUTING_LOGS = True
SIM_TTL = 32

## modes
SIM_SEND_RANDOM_DATA = True  # nodes send random data packets to other nodes
SIM_INCLUDE_ROUTERS = False
SIM_ENERGY_LOSS = False
SIM_PACKET_LOSS_RATE = 0  # self-explanatory. currently doesn't work great with it active
SIM_KILL_NODES = True
REPAIRING_METHOD = 'ALL_ORPHAN' # 'ALL_ORPHAN', 'FIND_ANOTHER_PARENT'

## application properties
LOGGING = True
HEARTBEAT_INTERVAL = 60
EXPORT_CH_CSV_INTERVAL = 10  # simulation time units;
EXPORT_NEIGHBOR_CSV_INTERVAL = 10  # simulation time units;