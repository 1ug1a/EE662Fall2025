import math
import random
import sys
# insert at 1, 0 is the script path (or '' in REPL)
sys.path.insert(1, '.')

from collections import Counter
from enum import Enum
from pprint import pprint

from source import wsnlab_vis as wsn
from source import config

Roles = Enum('Roles', 'OFF UNDISCOVERED UNREGISTERED ROOT REGISTERED CLUSTER_HEAD ROUTER')
"""Enumeration of roles"""

def _addr_to_tuple(a): return (a.net_addr, a.node_addr) if a is not None else None

RNG = random.Random(config.SIM_RANDOM_SEED)
with open('EE662output.txt', 'w') as f:
    print("Using random seed: ", config.SIM_RANDOM_SEED)
    print("###########################################")

ROOT_ID = RNG.randint(0, config.SIM_NODE_COUNT)

# diagnostics
NODE_POS = {}
ACTIVE_ADDRS = []
ADDR_NODE_KEY = {}
ROLE_COUNTS = Counter()

'''
Midterm 2 - Elpy Perez

Implementation Status:
0. Overall Changes (compared to previously provided code)
    - Complete reorganizion
    - Addressing changed to match design: counting from 1 onwards
    - Network and node availability taken into account.
        - New cluster tracking table for root.
            - If hasn't recieved CLUSTER_ALIVE packet from CH after a while...
            - ...Removes lease on that address.
            - Chooses smallest available network address.
        - Node availability only tracked using a simple list of booleans for each node address index.
1. Neighbor Tables
    - Added NEIGHBOR_SHARE packet for multi-hop
2. Clusterhead Tables (Child Net/Members)
    - Child net table is now known as "descendants".
    - Mostly unchanged aside from organizational stuff.
3. Routing
    - Implemented according to rules set in design document
    - Includes multi-hop routing via next hop, route poisioning to avoid loops
    - Added DATA packet to inspect mesh-tree routing.
4. Config Parameters
    - Max cluster size paramenter working nominally.
    - Tx power able to be adjusted but not able to respond to conditions.
    - Packet loss parameter added, relevant important packets get re-sent
5. Routers
    - Router mode implemented.
    - Added NOMINATION packet to promote joining node to CH w/ address from NETWORK_RESPONSE
    - Node that sends NOMINATION packet turns into a router, can only interact with other routers and CHs
    - Choice of node to nominate only chooses based on farthest distance
6. Recovery
    - ALL_ORPHAN fully repairs.
    - FIND_ANOTHER_PARENT seems to partially work.
        - But something causes NETWORK_RESPONSEs to fail.
        - It might be the network not properly updating descendants?
7. Maintenance/Optimization
    - No reorganization other than when performing repairs yet.
8. Energy Model
    - Rudimentary energy loss system is in place.
    - Currently, a fixed amount of a node's energy is lost when sending any packet.
    - If it reaches a threshold, it powers off (and triggers repair).
A. Known Issues
    - Somehow sending random data can still choose inactive addresses, causing loops.
        - This is despite the fact that it got removed from the table it chooses from.
        - See ADDR_NODE_KEY.txt and ACTIVE_ADDRS.txt.
'''

###########################################################
class SensorNode(wsn.Node):
    """SensorNode class is inherited from Node class in wsnlab.py.
    It will run data collection tree construction algorithms.

    Attributes:
        role (Roles): role of node
        is_root_eligible (bool): keeps eligibility to be root
        c_probe (int): probe message counter
        th_probe (int): probe message threshold
    """

    ##################
    # Initialization #
    ##################
    def init(self):
        """Initialization of node. Setting all attributes of node.
        At the beginning node needs to be sleeping and its role should be UNDISCOVERED.

        Args:

        Returns:

        """
        # visualization/scene setup
        self.scene.nodecolor(self.id, 0.7, 0.7, 0.7) # light gray
        self.is_root_eligible = True if self.id == ROOT_ID else False

        # addresses/ids
        self.addr = None
        self.ch_addr = None
        self.parent_gui = None
        self.root_addr = None

        # parameters
        self.probe_counter = 0
        self.probe_threshold = 5
        self.join_counter = 0
        self.join_threshold = 5
        self.hops_to_root = 99999

        self.logging = config.LOGGING

        # tables and trackers
        self.activation_time = None
        self.join_time = None
        self.energy_J = 21600
        self.poisoned_addr = None
        
        self.neighbors = {}
        self.candidate_parents = {}
        self.join_request_senders = {}
        self.members = {} # CH only
        self.descendants = {} # aka "child net table". CH only
        self.clusters = {}
        # CH only: node availability
        self.node_vacancies = [True] + [False] * (config.SIM_MAX_CLUSTER_SIZE-1) if config.SIM_MAX_CLUSTER_SIZE is not None else [True] + [False] * 252

        # logging
        self.set_timer('TIMER_DEBUG_STATUS', 99)
        self.set_timer('TIMER_DEBUG_END', config.SIM_DURATION-0.01)

        self.sleep()

    def clear_data(self):
        if self.addr is not None and self.addr in ACTIVE_ADDRS:
            ACTIVE_ADDRS.remove(self.addr)
        ADDR_NODE_KEY.pop(_addr_to_tuple(self.addr), None)
        ADDR_NODE_KEY.pop(_addr_to_tuple(self.ch_addr), None)

        self.erase_parent()

        self.addr = None
        self.ch_addr = None
        self.parent_gui = None
        self.root_addr = None

        self.hops_to_root = 99999

        self.probe_counter = 0
        self.probe_threshold = 5

        self.join_counter = 0
        self.join_threshold = 5

        self.poisoned_addr = None

        self.neighbors = {}
        self.candidate_parents = {}
        self.join_request_senders = {}
        self.members = {} # CH only
        self.descendants = {} # aka "child net table". CH only
        self.node_vacancies = [True] + [False] * (config.SIM_MAX_CLUSTER_SIZE-1) if config.SIM_MAX_CLUSTER_SIZE is not None else [True] + [False] * 252

        #self.log("Data cleared.")

    def run(self):
        """Setting the arrival timer to wake up after firing.

        Args:

        Returns:

        """
        self.set_timer('TIMER_ACTIVATE', self.arrival)

        if config.SIM_KILL_NODES == True and self.id != ROOT_ID:
            if RNG.random() < 0.15:
                self.set_timer('TIMER_DIE', 600)

    ###########
    # Packets #
    ###########
    def send_probe(self):
        """Sends a probe message to all neighbors. (1-hop)

        Args:

        Returns:

        """
        #self.log("🔎 Sending PROBE.")
        self.send({
            'dest': wsn.BROADCAST_ADDR,
            'type': 'PROBE',
            'created': self.now
        })
        self.lose_energy()

    def send_heartbeat(self):
        """Sends a heartbeat message to announce node's presence to neighbors. (1-hop)

        Args:

        Returns:

        """
        #self.log("💕 %s: Sent HEARTBEAT." % (self.ch_addr if self.ch_addr is not None else self.addr))
        self.send({
            'dest': wsn.BROADCAST_ADDR,
            'type': 'HEARTBEAT',
            'source': self.ch_addr if self.ch_addr is not None else self.addr,
            'gui': self.id,
            'role': self.role,
            'addr': self.addr,
            'ch_addr': self.ch_addr,
            'hops_to_root': self.hops_to_root,
            'created': self.now
        })
        self.lose_energy()

    def send_join_request(self, dest):
        """Sends a join request to the destination address to join the network. (1-hop)

        Args:
            dest (Addr): Address of destination node
        Returns:

        """
        self.log('💬 [Node %s]: Sent JOIN_REQUEST to %s' % (self.id, str(dest)))
        self.send({
            'dest': dest,
            'type': 'JOIN_REQUEST',
            'gui': self.id,
            'ttl': config.SIM_TTL,
            'created': self.now
        })
        self.lose_energy()

    def send_join_response(self, dest, resp, addr=wsn.Addr(0,0)):
        """Sends a join reply message to register the node that requested to join after being promoted to clusterhead.
        The message includes a gui to determine which node will take this reply, an addr to be assigned to the node,
        and a root_addr. (1-hop)

        Args:
            dest (int): GUI of destination node
            resp (string): 'ACCEPT' or 'REJECT'
            addr (Addr): Address that will be assigned to new registered node
        Returns:

        """
        if resp == 'ACCEPT':
            self.log('💬 %s: Sent JOIN_RESPONSE (%s) to Node %s, address assigned %s' % (str(self.ch_addr), resp, str(dest), str(addr)))
        else:
            self.log('💬 %s: Sent JOIN_RESPONSE (%s) to Node %s' % (str(self.ch_addr), resp, str(dest)))
        self.send({
            'dest': wsn.BROADCAST_ADDR,
            'type': 'JOIN_RESPONSE',
            'source': self.ch_addr,
            'gui': self.id,
            'dest_gui': dest,
            'response': resp,
            'addr': addr,
            'root_addr': self.root_addr,
            'hops_to_root': self.hops_to_root+1,
            'created': self.now
        })
        self.lose_energy()

    def send_join_ack(self, dest):
        """Sending join acknowledgement message to given destination address. (1-hop)

        Args:
            dest (Addr): Address of destination node
        Returns:

        """
        self.log('💬 %s: Sending JOIN_ACK to %s' % (str(self.addr), str(dest)))
        self.send({
            'dest': dest,
            'type': 'JOIN_ACK',
            'source': self.addr,
            'gui': self.id,
            'created': self.now
        })
        self.lose_energy()

    def share_neighbors(self):
        """Sends a node's neighbors to broadcast address.

        Args:

        Returns:

        """
        temp_neighbors = {}
        for gui, pck in self.neighbors.items():
            if gui == self.id:
                break
            temp_pck = dict(pck)
            if temp_pck['hops_away'] < config.SIM_NEIGHBOR_TABLE_HOPS:
                temp_pck['hops_away'] += 1
                temp_pck['next_hop'] = self.addr
                temp_neighbors[gui] = temp_pck
        #self.log("📝 %s: Sharing neighbors: %s" % (self.addr, list(temp_neighbors)))
        self.send({
            'dest': wsn.BROADCAST_ADDR,
            'type': 'NEIGHBOR_SHARE',
            'source': self.addr,
            'gui': self.id,
            'neighbors': temp_neighbors,
            'created': self.now
        })
        self.lose_energy()

    def send_nomination(self, dest, addr):
        self.log("✨ %s: Sent NOMINATION to Node %s, address assigned %s" % (str(self.addr), str(dest), str(addr)))
        self.send({
            'dest': wsn.BROADCAST_ADDR,
            'type': 'NOMINATION',
            'source': self.addr,
            'gui': self.id,
            'dest_gui': dest,
            'addr': addr,
            'root_addr': self.root_addr,
            'hops_to_root': self.hops_to_root+1,
            'created': self.now
        })
        self.lose_energy()

    def send_network_request(self, dest):
        """Sends a network request message to given destination address. (Multi-hop)

        Args:
            dest (Addr): Address of destination node
        Returns:

        """
        self.log("📡 %s: Sending NETWORK_REQUEST to destination %s" % (str(self.addr), str(dest)))
        self.route_and_forward({
            'dest': dest,
            'type': 'NETWORK_REQUEST',
            'source': self.addr,
            'ttl': config.SIM_TTL,
            'created': self.now
        })

    def send_network_response(self, dest, addr):
        """Sending network reply message to dest address to be cluster head with a new adress

        Args:
            dest (Addr): destination address
            source (Addr): source address
            addr (Addr): cluster head address of new network

        Returns:

        """
        self.log("📡 %s: Sending NETWORK_RESPONSE to %s with CH address %s" % (str(self.addr), str(dest), str(addr)))
        self.route_and_forward({
            'dest': dest,
            'type': 'NETWORK_RESPONSE',
            'source': self.addr,
            'addr': addr,
            'ttl': config.SIM_TTL,
            'created': self.now
        })

    def send_network_update(self):
        """Sending network update message to parent (1-hop)

        Args:

        Returns:

        """
        temp_descendants = []
        if self.ch_addr is not None:
            temp_descendants = [self.ch_addr.net_addr]
        for networks in self.descendants.values():
            temp_descendants.extend(networks)
        
        if self.neighbors[self.parent_gui]['ch_addr'] is not None:
            addr = self.neighbors[self.parent_gui]['ch_addr']
        elif self.neighbors[self.parent_gui]['addr'] is not None:
            addr = self.neighbors[self.parent_gui]['addr']
        self.log("🔄 %s: Sending NETWORK_UPDATE to parent %s" % (str(self.addr), str(addr)))
        self.send({
            'dest': addr,
            'type': 'NETWORK_UPDATE',
            'source': self.addr,
            'gui': self.id,
            'descendants': temp_descendants,
            'created': self.now
        })
        self.lose_energy()

    def send_cluster_alive(self):
        #self.log("👋 %s: Sending CLUSTER_ALIVE to root." % (str(self.ch_addr)))
        self.route_and_forward({
            'dest': self.root_addr,
            'type': 'CLUSTER_ALIVE',
            'source': self.ch_addr,
            'gui': self.id,
            'ttl': config.SIM_TTL,
            'created': self.now
        })

    def send_orphan_notice(self):
        """Sends i am orphan message to inform its neighbors.

        Args:

        Returns:

        """
        self.log("📣 [Node %s]: Broadcasting orphan notice." % self.id)
        self.send({
            'dest': wsn.BROADCAST_ADDR,
            'type': 'ORPHAN_NOTICE',
            'source': self.ch_addr
        })

    def send_random_data(self, dest):
        """Sends a random data message to given destination address. (Multi-hop)

        Args:
            dest (Addr): Address of destination node.

        Returns:

        """
        data_payload = RNG.randint(0, 1000)
        self.log("📦 %s: Sending DATA (%s) to random address %s" % (str(self.addr), str(data_payload), str(dest)))
        self.route_and_forward({
            'dest': dest,
            'type': 'DATA',
            'source': self.addr,
            'payload': data_payload,
            'ttl': config.SIM_TTL,
            'created': self.now
        })
    
    ##########
    # Timers #
    ##########
    def on_timer_fired(self, name, *args, **kwargs):
        """Executes when a timer fired.

        Args:
            name (string): Name of timer.
            *args (string): Additional args.
            **kwargs (string): Additional key word args.
        Returns:

        """
        match name:
            case 'TIMER_ACTIVATE':
                # self.log("👋 Activated.")
                self.wake_up()
                self.set_role(Roles.UNDISCOVERED)
                self.activation_time = self.now
                self.set_timer('TIMER_PROBE', 1)

            case 'TIMER_DIE':
                self.log("🔌 %s: Randomly turning off." % str(self.addr))
                self.die()
        
            case 'TIMER_PROBE':
                if self.probe_counter < self.probe_threshold:
                    if self.probe_counter == 0:
                        # self.log("📡 Sending probes...")
                        pass
                    self.send_probe()
                    self.probe_counter += 1
                    self.set_timer('TIMER_PROBE', 1)
                else:  # if the counter reached the threshold
                    if self.is_root_eligible:  # if the node is root eligible, it becomes root
                        self.log("[Node %s] 🌱 Root-eligible. Becoming root." % self.id)
                        self.set_role(Roles.ROOT)

                        self.addr = wsn.Addr(1, 254) 
                        self.ch_addr = wsn.Addr(1, 254)
                        ADDR_NODE_KEY[(self.addr.net_addr, self.addr.node_addr)] = self.id
                        self.root_addr = self.addr
                        self.hops_to_root = 0
                        self.set_timer('TIMER_HEARTBEAT', config.HEARTBEAT_INTERVAL)
                    else:  # otherwise it keeps trying to sending probe after a long time
                        # self.log("⏳ Probes failed. Waiting to send again...")
                        self.probe_counter = 0
                        self.set_timer('TIMER_PROBE', 30)

            case 'TIMER_HEARTBEAT':
                self.send_heartbeat()
                self.check_neighbors()
                self.share_neighbors()
                #self.log(self.neighbors)
                if self.role == Roles.CLUSTER_HEAD:
                    self.send_cluster_alive()
                if self.role == Roles.ROOT:
                    self.check_clusters()
                self.set_timer('TIMER_HEARTBEAT', config.HEARTBEAT_INTERVAL)

            case 'TIMER_JOIN_REQUEST_SEND':  # if it has not received heart beat messages before, it sets timer again and wait heart beat messages once join request timer fired.
                self.check_neighbors()
                #self.log(self.candidate_parents)
                if len(self.candidate_parents) == 0:
                    if self.ch_addr is not None: # if it has a cluster head address. (if it is in repairing phase)
                        self.send_orphan_notice()
                    self.become_unregistered()
                else:  # otherwise it chose one of them and sends join request
                    self.select_and_join()

            case 'TIMER_JOIN_REQUEST_RECV':  # after collecting join requests for some time, send a network request to root
                self.send_network_request(self.root_addr)
                self.set_timer("TIMER_NETWORK_REQUEST", 50)

            case 'TIMER_NETWORK_REQUEST':
                self.log("↪️ %s: Resending NETWORK_REQUEST..." % str(self.addr))
                self.send_network_request(self.root_addr)
                self.set_timer("TIMER_NETWORK_REQUEST", 50)

            case 'TIMER_RANDOM_DATA':
                if RNG.random() < 0.1:
                    self.send_random_data(RNG.choice(ACTIVE_ADDRS))
                self.set_timer('TIMER_RANDOM_DATA', RNG.uniform(20, 50))

            case 'TIMER_DEBUG_STATUS':
                #self.log("🐞 [Node %s]: Neighbors: %s" % (self.id, list((key, pck['addr'], pck['ch_addr']) for (key, pck) in self.neighbors.items())))
                #self.log("🐞 [Node %s]: Neighbors: %s" % (self.id, list((key, pck['hops_away']) for (key, pck) in self.neighbors.items())))
                #self.log("🐞 [Node %s]: Members: %s" % (self.id, list(self.members.keys())))
                #self.log("🐞 [Node %s]: Descendants: %s" % (self.id, list(self.descendants.keys())))
                if self.id == ROOT_ID:
                    #pprint(ADDR_NODE_KEY)
                    #pprint(ROLE_COUNTS)
                    pass
                self.set_timer('TIMER_DEBUG_STATUS', 100)

            case 'TIMER_DEBUG_END':
                if self.id == ROOT_ID:
                    #pprint(ADDR_NODE_KEY)
                    with open('ADDR_NODE_KEY.txt', 'w') as f:
                        for addr, gui in ADDR_NODE_KEY.items():
                            f.write(f"{addr}:\t{gui}" + '\n')
                    with open('ACTIVE_ADDRS.txt', 'w') as f:
                        for addr in ADDR_NODE_KEY:
                            f.write(f"{addr}" + '\n')
                    pass

    ############
    # Receives #
    ############
    def on_receive(self, pck):
        """Executes when a package received.

        Args:
            pck (Dict): received package
        Returns:

        """
        if RNG.random() < config.SIM_PACKET_LOSS_RATE:
            packet_type_log_filter = [
                'PROBE',
                'HEARTBEAT',
            ]
            if pck['type'] not in packet_type_log_filter:
                self.log("💥 [Node %s]: %s packet lost." % (self.id, pck['type']))
            return

        # only do something if the packet is addressed to me (unicast or broadcast)
        if pck['dest'] == wsn.BROADCAST_ADDR or (self.ch_addr is not None and pck['dest'] == self.ch_addr) or (self.addr is not None and pck['dest'] == self.addr):
            match pck['type']:
                case 'PROBE':
                    if self.role in [Roles.ROOT, Roles.CLUSTER_HEAD, Roles.REGISTERED, Roles.ROUTER]:
                        self.send_heartbeat()
                
                case 'HEARTBEAT':
                    #self.log("📨 Received heartbeat from Node %s" % pck['gui'])
                    self.update_neighbors(pck)
                    if pck['gui'] != self.parent_gui and self.parent_gui is not None:
                        #self.draw_mesh_link(pck['gui'])
                        pass

                    if self.is_root_eligible:
                        if pck['role'] == Roles.ROOT:
                            self.log("🚫 [Node %s]: Node %s is already root. Removing root eligibility." % (str(self.id), str(pck['gui'])))
                            self.is_root_eligible = False
                    elif self.role == Roles.UNDISCOVERED:
                        self.log("👀 [Network]: Node %s discovered." % str(self.id))
                        self.kill_timer('TIMER_PROBE')
                        self.become_unregistered()
                
                case 'NEIGHBOR_SHARE':
                    temp_neighbors = dict(pck['neighbors'])
                    if self.id in temp_neighbors:
                        temp_neighbors.pop(self.id)
                    for gui, pck in temp_neighbors.items():
                        if gui not in self.neighbors or pck['hops_away'] < self.neighbors[gui]['hops_away']:
                            self.neighbors[gui] = pck
                
                case 'JOIN_REQUEST':
                    if self.role in [Roles.ROOT, Roles.CLUSTER_HEAD]:
                        if not all(self.node_vacancies):
                            # get smallest available address by going through node_availability until false
                            #self.log("📝 %s: Node availability: %s" % (str(self.addr), dict(enumerate(self.node_vacancies))))
                            chosen_node_addr = min([idx for idx, val in enumerate(self.node_vacancies) if val == False])
                            self.send_join_response(pck['gui'], 'ACCEPT', wsn.Addr(self.ch_addr.net_addr, chosen_node_addr))
                            self.node_vacancies[chosen_node_addr] = True
                        else:
                            self.send_join_response(pck['gui'], 'REJECT')
                    elif self.role == Roles.REGISTERED:
                        # collect join request senders to avoid multiple requests from same node
                        self.log("📦 %s: Received JOIN_REQUEST from Node %s" % (str(self.addr), str(pck['gui'])))
                        if pck['gui'] not in self.join_request_senders:
                            self.log("➕ %s: Adding Node %s to join request senders. Waiting for more..." % (str(self.addr), str(pck['gui'])))
                            #self.log(str(self.join_request_senders))
                            self.join_request_senders[pck['gui']] = pck
                            self.kill_timer('TIMER_JOIN_REQUEST_RECV') # reset timer
                            self.set_timer('TIMER_JOIN_REQUEST_RECV', 5)
                        else:
                            self.log("➖ %s: Node %s already in join request senders. Ignoring." % (str(self.addr), str(pck['gui'])))
                            pass
                    elif self.role == Roles.ROUTER:
                        self.send_join_response(pck['gui'], 'REJECT')
                
                case 'JOIN_RESPONSE':
                    if self.role == Roles.UNREGISTERED:
                        if pck['dest_gui'] == self.id:
                            if pck['response'] == 'ACCEPT':
                                self.addr = pck['addr']
                                self.parent_gui = pck['gui']
                                self.root_addr = pck['root_addr']
                                self.hops_to_root = pck['hops_to_root']
                                self.draw_parent()
                                self.kill_timer('TIMER_JOIN_REQUEST_SEND')
                                if config.SIM_SEND_RANDOM_DATA:
                                    self.set_timer('TIMER_RANDOM_DATA', RNG.uniform(20, 50))
                                self.send_join_ack(pck['source'])
                                self.send_heartbeat()
                                self.share_neighbors()
                                self.set_timer('TIMER_HEARTBEAT', config.HEARTBEAT_INTERVAL)
                                self.set_role(Roles.REGISTERED)
                            elif pck['response'] == 'REJECT':
                                self.log("🚫 [Node %s]: Node %s is full. Removing from candidate parents. Remaining: %s" % (str(self.id), str(pck['gui']), list(self.candidate_parents)))
                                self.candidate_parents.pop(pck['gui'])
                
                case 'JOIN_ACK':
                    if self.role in [Roles.ROOT, Roles.CLUSTER_HEAD]:
                        self.members[pck['gui']] = pck
                        #self.log(self.join_request_senders)
                        if self.join_request_senders.get(pck['gui']):
                            self.join_request_senders.pop(pck['gui'])
                        ACTIVE_ADDRS.append(pck['source'])
                        ADDR_NODE_KEY[(pck['source'].net_addr, pck['source'].node_addr)] = pck['gui']
                        self.log('🤝 [Network]: Node %s joined as member with address %s' % (str(pck['gui']), str(pck['source'])))
                
                case 'NETWORK_REQUEST':
                    if self.role == Roles.ROOT:
                        pck['arrival_time'] = self.now
                        self.log("📨 %s: Received NETWORK_REQUEST from %s" % (str(self.addr), str(pck['source'])))
                        chosen_net_addr = min([net_addr for net_addr in range(2,254) if net_addr not in list(self.clusters.keys())])
                        self.send_network_response(pck['source'], wsn.Addr(chosen_net_addr, 254))
                        self.clusters[chosen_net_addr] = pck
                
                case 'NETWORK_RESPONSE':
                    if self.role == Roles.REGISTERED:
                        # either promote self to CH, or select and nominate a downstream node to become CH
                        if config.SIM_INCLUDE_ROUTERS:
                            self.select_and_nominate(pck['addr'])
                            self.set_role(Roles.ROUTER)
                            self.join_request_senders = {}
                        else:
                            self.set_role(Roles.CLUSTER_HEAD)
                            self.kill_timer('TIMER_NETWORK_REQUEST')
                            self.log("🚀 %s: Received NETWORK_RESPONSE. Promoting to CLUSTER_HEAD with address %s" % (str(self.addr), str(pck['addr'])))
                            self.ch_addr = pck['addr']
                            ADDR_NODE_KEY[(self.ch_addr.net_addr, self.ch_addr.node_addr)] = self.id
                            self.log("🔄 %s: Updating network..." % str(self.ch_addr))
                            self.send_network_update()
                            self.send_heartbeat()
                            self.send_cluster_alive()
                            for gui in RNG.sample(sorted(self.join_request_senders.keys()), len(self.join_request_senders.keys())): # randomly sample in case of limited slots
                                if not all(self.node_vacancies):
                                    # get smallest available address by going through node_availability until false
                                    #self.log("📝 %s: Node availability: %s" % (str(self.addr), dict(enumerate(self.node_vacancies))))
                                    chosen_node_addr = min([idx for idx, val in enumerate(self.node_vacancies) if val == False])
                                    self.send_join_response(gui, 'ACCEPT', wsn.Addr(self.ch_addr.net_addr, chosen_node_addr))
                                    self.node_vacancies[chosen_node_addr] = True
                                else:
                                    self.send_join_response(gui, 'REJECT')
                
                case 'NETWORK_UPDATE':
                    match self.role:
                        case Roles.ROOT:
                            self.descendants[pck['gui']] = pck['descendants']
                            #self.log("🔄 %s: Updated descendants: %s" % (str(self.addr), self.descendants))
                            #self.log(self.descendants)
                        case Roles.CLUSTER_HEAD | Roles.ROUTER:
                            self.descendants[pck['gui']] = pck['descendants']
                            #self.log("🔄 %s: Updated descendants with Node %s: %s" % (str(self.addr), str(pck['gui']), str(pck['descendants'])))
                            #self.log(self.descendants)
                            self.send_network_update()
                    #self.log("🔄 %s: Updated descendants: %s" % (str(self.addr), self.descendants))
                
                case 'CLUSTER_ALIVE':
                    if self.role == Roles.ROOT:
                        pck['arrival_time'] = self.now
                        self.clusters[pck['source'].net_addr] = pck
                        #self.log("👋 %s: CLUSTER_ALIVE received. Clusters updated." % str(self.ch_addr))

                case 'NOMINATION':
                    if self.role == Roles.UNREGISTERED:
                        if pck['dest_gui'] == self.id:
                            self.set_role(Roles.CLUSTER_HEAD)
                            self.log("🚀 [Node %s]: Received NOMINATION. Joining as CLUSTER_HEAD with address %s" % (self.id, str(pck['addr'])))
                            self.ch_addr = pck['addr']
                            self.addr = self.ch_addr
                            self.parent_gui = pck['gui']
                            self.root_addr = pck['root_addr']
                            self.hops_to_root = pck['hops_to_root']
                            self.draw_parent()
                            self.kill_timer('TIMER_JOIN_REQUEST_SEND')
                            ADDR_NODE_KEY[(self.ch_addr.net_addr, self.ch_addr.node_addr)] = self.id
                            self.draw_parent()
                            self.log("🔄 %s: Updating network..." % str(self.ch_addr))
                            self.send_network_update()
                            self.share_neighbors()
                            self.send_heartbeat()
                            self.join_request_senders = {}
                
                case 'ORPHAN_NOTICE':
                    if self.role not in [Roles.UNDISCOVERED, Roles.UNREGISTERED, Roles.ROOT]:
                        if pck['source'] == self.neighbors[self.parent_gui]['ch_addr'] or pck['source'] == self.neighbors[self.parent_gui]['addr']:
                            self.repair()
                    

                case 'DATA':
                    self.log("📬 %s: Received DATA (%s) from %s. Time taken: %.0f μs" % (str(self.addr), str(pck['payload']), str(pck['source']), 1000000*(self.now-pck['created'])))
        else:
            if self.addr is not None:
                self.route_and_forward(pck)

    ###########
    # Actions #
    ###########
    def select_and_join(self):
        min_hops_to_root = 99999
        min_hop_gui = 99999
        #self.check_neighbors()
        #self.log(self.neighbors)
        for gui in self.candidate_parents.keys():
            if self.neighbors[gui]['role'] not in [Roles.UNREGISTERED, Roles.ROUTER]:
                if self.neighbors[gui]['hops_to_root'] < min_hops_to_root or (self.neighbors[gui]['hops_to_root'] == min_hops_to_root and gui < min_hop_gui):
                    min_hops_to_root = self.neighbors[gui]['hops_to_root']
                    min_hop_gui = gui
        if min_hop_gui != 99999:
            #self.log(min_hop_gui)
            selected_addr = self.neighbors[min_hop_gui]['source']
            if self.join_counter < self.join_threshold:
                self.send_join_request(selected_addr)
                self.join_counter += 1
                self.set_timer('TIMER_JOIN_REQUEST_SEND', 10)
                return
            else:
                #self.log("✂️ [Node %s]: No JOIN_RESPONSE from selected address. Removing from candidate parents." % self.id)
                self.join_counter = 0
                del self.candidate_parents[min_hop_gui]
                self.set_timer('TIMER_JOIN_REQUEST_SEND', 20)
                return
        #self.log("No candidates found.")
        self.set_timer('TIMER_JOIN_REQUEST_SEND', 20)

    def select_and_nominate(self, addr):
        max_distance = -1
        max_distance_gui = -1
        
        for gui in self.join_request_senders.keys():
            if gui in NODE_POS and self.id in NODE_POS:
                x1, y1 = NODE_POS[self.id]
                x2, y2 = NODE_POS[gui]
                temp_distance = math.hypot(x1 - x2, y1 - y2)
            
            if temp_distance > max_distance:
                max_distance = temp_distance
                max_distance_gui = gui

        for gui in self.join_request_senders.keys():
            if gui != max_distance_gui:
                self.send_join_response(gui, 'REJECT')
        self.join_request_senders = {}

        self.send_nomination(max_distance_gui, addr)

    def update_neighbors(self, pck):
        pck['arrival_time'] = self.now
        pck['hops_away'] = 1
        pck['next_hop'] = pck['addr']
        # compute Euclidean distance between self and neighbor
        if pck['gui'] in NODE_POS and self.id in NODE_POS:
            x1, y1 = NODE_POS[self.id]
            x2, y2 = NODE_POS[pck['gui']]
            pck['distance'] = math.hypot(x1 - x2, y1 - y2)
        #self.log("Neighbor added: (%s, %s)" % (pck['gui'], pck['hops_away']))
        self.neighbors[pck['gui']] = pck

        if pck['gui'] not in self.descendants.keys() or pck['gui'] not in self.descendants:
            if pck['gui'] not in self.candidate_parents:
                self.candidate_parents[pck['gui']] = pck

    def check_neighbors(self):
        """Checks neighbors if they are still alive or not. If not, updates necessary tables.
        Sends heartbeat and network update messages in need.

        Args:

        Returns:

        """
        childs_updated = False
        parent_dead = False
        will_be_removed = []
        #self.log(self.neighbors)
        #self.log(self.candidate_parents)
        for gui, pck in self.neighbors.items():
            if self.now - pck['arrival_time'] > 3 * config.HEARTBEAT_INTERVAL:
                will_be_removed.append(gui)
                if gui == self.parent_gui:
                    parent_dead = True
                if gui in self.descendants.keys():
                    del self.descendants[gui]
                    childs_updated = True
                if gui in self.candidate_parents.keys():
                    del self.candidate_parents[gui]
        for gui in will_be_removed:
            del self.neighbors[gui]
        if self.role != Roles.UNREGISTERED:
            if parent_dead:
                #self.log("Parent lost. Repair imminent.")
                self.repair()
            else:
                #self.send_heartbeat()
                #self.set_timer('TIMER_HEARTBEAT', config.HEARTBEAT_INTERVAL)
                # ^ this (from repairing_network.py) was creating additional duplicate heartbeats and lagging the simulation
                if childs_updated:
                    if self.role != Roles.ROOT:
                        self.send_network_update()

    def check_clusters(self):
        will_be_removed = []
        for net_addr, pck in self.clusters.items():
            if self.now - pck['arrival_time'] > 3 * config.HEARTBEAT_INTERVAL:
                will_be_removed.append(net_addr)
        if will_be_removed:
            self.log("🧹 %s: Clusters %s inactive. Clearing..." % (str(self.ch_addr), will_be_removed))
        for net_addr in will_be_removed:
            del self.clusters[net_addr]

    def repair(self):
        """Executes chosen repairing instructions.

        Args:

        Returns:

        """
        if self.role == Roles.REGISTERED:
            self.become_unregistered()
        else:
            if config.REPAIRING_METHOD == 'ALL_ORPHAN':
                self.repair_all_orphan()
            elif config.REPAIRING_METHOD == 'FIND_ANOTHER_PARENT':
                self.repair_find_another_parent()

    def repair_all_orphan(self):
        """Becomes unregistered and sends I am orphan message.

        Args:

        Returns:

        """
        self.send_orphan_notice()
        self.become_unregistered()

    def repair_find_another_parent(self):
        """If it has potential parent in its table, tries to connect any of them. Otherwise becomes unregistered.

        Args:

        Returns:

        """
        if self.parent_gui in self.candidate_parents:
            del self.candidate_parents[self.parent_gui]
            del self.neighbors[self.parent_gui]
        # candidate parents should not be in your members either
        for gui in self.members.keys():
            if gui in self.candidate_parents:
                del self.candidate_parents[gui]
        if len(self.candidate_parents) != 0:
            self.kill_all_timers()
            self.erase_parent()
            self.role = Roles.UNREGISTERED
            self.select_and_join()
        else:
            self.send_orphan_notice()
            self.become_unregistered()

    def route_and_forward(self, pck):
        """Routes and forwards a multi-hop message according to cluster-mesh rules.

        Args:
            pck (Dict): package to be routed and forwarded
        Returns:

        """
        #self.log(pck)
        #self.log("🚛 %s: Routing %s to destination %s..." % (str(self.addr), pck['type'], str(pck['dest'])))
        #self.log(self.parent_gui)
        #self.log("Descendants: %s" % str(self.descendants))
        pck['next_hop'] = None
        if self.role != Roles.ROOT and self.parent_gui is not None:
            #self.log("Routing: parent.")
            if self.parent_gui in self.neighbors:
                log_string = "next hop: parent %s" % (str(self.neighbors[self.parent_gui]['addr']))
                pck['next_hop'] = self.neighbors[self.parent_gui]['addr']
        if self.ch_addr is not None:
            if pck['dest'].net_addr == self.ch_addr.net_addr:
                #self.log("Routing: cluster member.")
                log_string = "next hop: cluster member %s" % str(self.ch_addr)
                pck['next_hop'] = pck['dest']
        for child_gui, child_networks in self.descendants.items():
            if pck['dest'].net_addr in child_networks:
                #self.log("Routing: descendant.")
                log_string = "next hop: descendant %s" % (str(self.neighbors[child_gui]['ch_addr'] or self.neighbors[child_gui]['addr']))
                pck['next_hop'] = self.neighbors[child_gui]['addr']
        # add mesh routing using neighbor tables. overrides tree routing (what to do with routers....)
        # start by collecting all neighbor addresses (only if the neighbor has an addr or ch_addr)
        temp_neighbors_inverted = {(self.neighbors[key]['addr'].net_addr, self.neighbors[key]['addr'].node_addr): key for key in self.neighbors.keys() if self.neighbors[key]['addr'] is not None and key != self.parent_gui}
        temp_neighbors_inverted.update({(self.neighbors[key]['addr'].net_addr, self.neighbors[key]['addr'].node_addr): key for key in self.neighbors.keys() if self.neighbors[key]['ch_addr'] is not None})

        if self.poisoned_addr is not None and (self.poisoned_addr.net_addr, self.poisoned_addr.node_addr) in temp_neighbors_inverted:
            # this restriction is here because frequently-used gateways get poisoned the most
            if self.neighbors[temp_neighbors_inverted[(self.poisoned_addr.net_addr, self.poisoned_addr.node_addr)]]['hops_away'] != 1:
                #self.log("Poisoned address: %s" % self.poisoned_addr)
                temp_neighbors_inverted.pop((self.poisoned_addr.net_addr, self.poisoned_addr.node_addr))
        # remove non-leaf nodes for routers
        if self.role == Roles.ROUTER:
            temp_neighbors_inverted_keys = list(temp_neighbors_inverted.keys())
            for neighbor_tuple in temp_neighbors_inverted_keys:
                if self.neighbors[temp_neighbors_inverted[neighbor_tuple]]['role'] == Roles.REGISTERED:
                    temp_neighbors_inverted.pop(neighbor_tuple)
        
        #self.log("🧭 %s: Inverted neighbor table: %s" % (str(self.addr), dict(temp_neighbors_inverted)))
        # check for destination cluster in neighbor addresses
        #self.log([(gui, neighbor['source'], neighbor['hops_away'], neighbor['next_hop']) for gui, neighbor in self.neighbors.items()])
        dest_net_addr = pck['dest'].net_addr
        dest_node_addr = pck['dest'].node_addr
        # if we find the cluster in neighbor address...
        #self.log(list(temp_neighbors_inverted.keys()))
        if dest_net_addr in [addr[0] for addr in temp_neighbors_inverted.keys()]:
            neighbor_net_addr = dest_net_addr
            node_addr_candidates = [addr[1] for addr in temp_neighbors_inverted.keys() if addr[0] == neighbor_net_addr]
            #self.log("Candidates (network %s): %s" % (neighbor_net_addr, list(node_addr_candidates)))
            #self.log([member['source'] for gui, member in self.members.items()])
            # if destination is directly a neighbor node...
            if dest_node_addr in node_addr_candidates:
                # make note of the address to use
                #self.log("Routing: Found exact match.")
                neighbor_node_addr = dest_node_addr
            # if you have the destination's clusterhead that's good too
            elif 254 in node_addr_candidates:
                #self.log("Routing: Found clusterhead of destination.")
                neighbor_node_addr = 254
            # otherwise choose the candidate with the least hops away
            else:
                #self.log("Routing: Choosing closest neighbor.")
                hops_away_table = {}
                for node in node_addr_candidates:
                    gui = temp_neighbors_inverted[(dest_net_addr, node)]
                    hops_away_table[node] = self.neighbors[gui]['hops_away']
                #self.log(hops_away_table)
                neighbor_node_addr = min(hops_away_table, key=hops_away_table.get)
            
            neighbor_addr = wsn.Addr(neighbor_net_addr, neighbor_node_addr)
            neighbor_id = temp_neighbors_inverted[(neighbor_net_addr, neighbor_node_addr)]
            #one_hop_neighbor_info = self.neighbors[neighbor_id]
            #self.log(one_hop_neighbor_info)
            one_hop_neighbor_addr = self.neighbors[neighbor_id]['next_hop']
            if one_hop_neighbor_addr is not None:
                #self.log("Routing: neighbor.")
                pck['next_hop'] = one_hop_neighbor_addr
                log_string = "next hop: %s towards neighbor %s" % (str(one_hop_neighbor_addr), str(neighbor_addr))
                
        if pck['next_hop'] is not None:
            self.poisoned_addr = pck['next_hop']
            pck['ttl'] -= 1
            if config.SIM_ROUTING_LOGS == True and pck['type'] != 'CLUSTER_ALIVE':
                self.log("🚛 %s: %s from %s to %s, " % (self.addr, pck['type'], pck['source'], pck['dest']) + log_string + " TTL: %s" % pck['ttl'])
            if pck['ttl'] <= 0:
                self.log("⛔ %s: %s has expired. Dropping!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" % (str(self.addr), pck['type']))
                return
            self.send(pck)
            self.lose_energy()
        else:
            self.log("⛔ %s: %s could not be routed. Dropping!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" % (str(self.addr), pck['type']))

    ###########
    # Helpers #
    ###########
    def set_role(self, new_role, *, recolor=True):
        """Central place to switch roles, keep tallies, and (optionally) recolor."""
        old_role = getattr(self, "role", None)
        if old_role is not None:
            ROLE_COUNTS[old_role] -= 1
            if ROLE_COUNTS[old_role] <= 0:
                ROLE_COUNTS.pop(old_role, None)
        ROLE_COUNTS[new_role] += 1
        self.role = new_role

        if recolor:
            match new_role:
                case Roles.OFF:
                    self.scene.nodecolor(self.id, 0.80, 0.80, 0.80)
                    self.erase_tx_range()
                case Roles.UNDISCOVERED:
                    self.scene.nodecolor(self.id, 0.80, 0.31, 0.24) # red
                    self.erase_tx_range()
                case Roles.UNREGISTERED:
                    self.scene.nodecolor(self.id, 0.91, 0.59, 0.18) # yellow
                    self.erase_tx_range()
                case Roles.REGISTERED:
                    self.scene.nodecolor(self.id, 0.06, 0.52, 0.33) # green
                    # self.draw_tx_range()
                case Roles.ROUTER:
                    self.scene.nodecolor(self.id, 0.62, 0.17, 0.92) # purple
                case Roles.CLUSTER_HEAD:
                    self.scene.nodecolor(self.id, 0.11, 0.21, 0.89) # blue
                    self.draw_tx_range()
                case Roles.ROOT:
                    self.scene.nodecolor(self.id, 0.93, 0.08, 0.60)
                    self.draw_tx_range()
                    self.set_timer('TIMER_EXPORT_CH_CSV', config.EXPORT_CH_CSV_INTERVAL)
                    self.set_timer('TIMER_EXPORT_NEIGHBOR_CSV', config.EXPORT_NEIGHBOR_CSV_INTERVAL)

    def become_unregistered(self):
        self.sleep()
        if self.role != Roles.UNDISCOVERED:
            self.kill_all_timers()
        self.set_role(Roles.UNREGISTERED)
        self.clear_data()
        self.wake_up()
        self.send_probe()
        self.set_timer('TIMER_JOIN_REQUEST_SEND', 20)

    def lose_energy(self):
        if config.SIM_ENERGY_LOSS:
            self.energy_J -= 300 # large value for demonstration
            if self.energy_J < 0.10 * 21600:
                self.log("🔌 %s: Ran out of energy. Turning off..." % str(self.addr))
                self.die()

    def die(self):
        self.sleep()
        self.clear_data()
        self.kill_all_timers()
        self.set_role(Roles.OFF)
        

###########################################################
def create_network(node_class, number_of_nodes=100):
    """Creates given number of nodes at random positions with random arrival times.

    Args:
        node_class (Class): Node class to be created.
        number_of_nodes (int): Number of nodes.
    Returns:

    """
    edge = math.ceil(math.sqrt(number_of_nodes))
    for i in range(number_of_nodes):
        x = i / edge
        y = i % edge
        px = 50 + x * config.SIM_NODE_PLACING_CELL_SIZE + RNG.uniform(-1 * config.SIM_NODE_PLACING_CELL_SIZE / 3, config.SIM_NODE_PLACING_CELL_SIZE / 3)
        py = 50 + y * config.SIM_NODE_PLACING_CELL_SIZE + RNG.uniform(-1 * config.SIM_NODE_PLACING_CELL_SIZE / 3, config.SIM_NODE_PLACING_CELL_SIZE / 3)
        node = sim.add_node(node_class, (px, py))
        NODE_POS[node.id] = (px, py)
        if config.NODE_TX_STATIC:
            node.tx_range = config.NODE_TX_BASE_RANGE
        else:
            node.tx_range = config.NODE_TX_BASE_RANGE * RNG.choices(config.NODE_TX_POWER_MULTS, weights=config.NODE_TX_POWER_PROBS, k=1)[0]
        node.logging = True
        node.arrival = RNG.uniform(0, config.NODE_ARRIVAL_MAX)
        if config.SIM_FAST_ROOT and node.id == ROOT_ID:
            node.arrival = 0.1



sim = wsn.Simulator(
    duration=config.SIM_DURATION,
    timescale=config.SIM_TIME_SCALE,
    visual=config.SIM_VISUALIZATION,
    seed=config.SIM_RANDOM_SEED,
    terrain_size=config.SIM_TERRAIN_SIZE,
    title=config.SIM_TITLE)

# creating random network
create_network(SensorNode, config.SIM_NODE_COUNT)

# start the simulation
sim.run()

# Created 100 nodes at random locations with random arrival times.
# When nodes are created they appear in white
# Activated nodes becomes red
# Discovered nodes will be yellow
# Registered nodes will be green.
# Root node will be black.
# Routers/Cluster Heads should be blue
