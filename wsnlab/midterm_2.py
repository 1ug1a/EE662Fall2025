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

RNG = random.Random(config.SIM_RANDOM_SEED)
print("Using random seed: ", config.SIM_RANDOM_SEED)
print("###########################################")

ROOT_ID = RNG.randint(0, config.SIM_NODE_COUNT)

# diagnostics
NODE_POS = {}
USED_ADDRS = []
ADDR_NODE_KEY = {}
ROLE_COUNTS = Counter()

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
        self.hops_to_root = 99999

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
        # root only: network availability
        # T/F based on what cluster net addresses are available
        # root is by default 1. always take the next lowest available address. 255 is broadcast and not included
        self.net_vacancies = [True] + [False] * 254
        # CH only: node availability
        self.node_vacancies = [True] + [False] * (config.SIM_MAX_CLUSTER_SIZE-1) if config.SIM_MAX_CLUSTER_SIZE is not None else [True] + [False] * 253

        # logging
        self.set_timer('TIMER_DEBUG', 99)

        self.sleep()

    def run(self):
        """Setting the arrival timer to wake up after firing.

        Args:

        Returns:

        """
        self.set_timer('TIMER_ACTIVATE', self.arrival)

        if self.id != ROOT_ID:
            if RNG.random() < 0.15:
                self.set_timer('TIMER_DIE', 500)

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
        self.log("📡 %s: Finished collection. Sending NETWORK_REQUEST to destination %s" % (str(self.addr), str(dest)))
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

                        self.net_vacancies[1] = True # root is always net address 1
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
                self.share_neighbors()
                self.set_timer('TIMER_HEARTBEAT', config.HEARTBEAT_INTERVAL)

            case 'TIMER_JOIN_REQUEST_SEND':  # if it has not received heart beat messages before, it sets timer again and wait heart beat messages once join request timer fired.
                if len(self.candidate_parents) == 0:
                    self.become_unregistered()
                else:  # otherwise it chose one of them and sends join request
                    self.select_and_join()

            case 'TIMER_JOIN_REQUEST_RECV':  # after collecting join requests for some time, send a network request to root
                self.send_network_request(self.root_addr)

            case 'TIMER_RANDOM_DATA':
                if RNG.random() < 0.3:
                    self.send_random_data(RNG.choice(USED_ADDRS))
                self.set_timer('TIMER_RANDOM_DATA', RNG.uniform(20, 50))

            case 'TIMER_DEBUG':
                #self.log("🐞 [Node %s]: Neighbors: %s" % (self.id, list((key, pck['addr'], pck['ch_addr']) for (key, pck) in self.neighbors.items())))
                #self.log("🐞 [Node %s]: Neighbors: %s" % (self.id, list((key, pck['hops_away']) for (key, pck) in self.neighbors.items())))
                #self.log("🐞 [Node %s]: Members: %s" % (self.id, list(self.members.keys())))
                #self.log("🐞 [Node %s]: Descendants: %s" % (self.id, list(self.descendants.keys())))
                if self.id == ROOT_ID:
                    #pprint(ADDR_NODE_KEY)
                    #pprint(ROLE_COUNTS)
                    pass
                self.set_timer('TIMER_DEBUG', 100)

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
                            self.set_timer('TIMER_JOIN_REQUEST_RECV', 4)
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
                        USED_ADDRS.append(pck['source'])
                        ADDR_NODE_KEY[(pck['source'].net_addr, pck['source'].node_addr)] = pck['gui']
                        self.log('🤝 [Network]: Node %s joined as member with address %s' % (str(pck['gui']), str(pck['source'])))
                case 'NETWORK_REQUEST':
                    if self.role == Roles.ROOT:
                        self.log("📨 %s: Received NETWORK_REQUEST from %s" % (str(self.addr), str(pck['source'])))
                        chosen_net_addr = min([idx for idx, val in enumerate(self.net_vacancies) if val == False])
                        self.send_network_response(pck['source'], wsn.Addr(chosen_net_addr, 254))
                        self.net_vacancies[chosen_net_addr] = True
                case 'NETWORK_RESPONSE':
                    if self.role == Roles.REGISTERED:
                        # either promote self to CH, or select and nominate a downstream node to become CH
                        if config.SIM_INCLUDE_ROUTERS:
                            self.select_and_nominate(pck['addr'])
                            self.set_role(Roles.ROUTER)
                            self.join_request_senders = {}
                        else:
                            self.set_role(Roles.CLUSTER_HEAD)
                            self.log("🚀 %s: Received NETWORK_RESPONSE. Promoting to CLUSTER_HEAD with address %s" % (str(self.addr), str(pck['addr'])))
                            self.ch_addr = pck['addr']
                            ADDR_NODE_KEY[(self.ch_addr.net_addr, self.ch_addr.node_addr)] = self.id
                            self.log("🔄 %s: Updating network..." % str(self.ch_addr))
                            self.send_network_update()
                            self.send_heartbeat()
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
                            #self.log("🔄 %s: Updated descendants with Node %s: %s" % (str(self.addr), str(pck['gui']), str(pck['descendants'])))
                            #self.log(self.descendants)
                        case Roles.CLUSTER_HEAD | Roles.ROUTER:
                            self.descendants[pck['gui']] = pck['descendants']
                            #self.log("🔄 %s: Updated descendants with Node %s: %s" % (str(self.addr), str(pck['gui']), str(pck['descendants'])))
                            #self.log(self.descendants)
                            self.send_network_update()
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
                case 'DATA':
                    self.log("📬 %s: Received DATA (%s) from %s. Time taken: %.0f μs" % (str(self.addr), str(pck['payload']), str(pck['source']), 1000000*(self.now-pck['created'])))
        else:
            self.route_and_forward(pck)

    ###########
    # Actions #
    ###########
    def select_and_join(self):
        min_hops_to_root = 99999
        min_hop_gui = 99999
        for gui in self.candidate_parents.keys():
            if self.neighbors[gui]['role'] != Roles.ROUTER:
                if self.neighbors[gui]['hops_to_root'] < min_hops_to_root or (self.neighbors[gui]['hops_to_root'] == min_hops_to_root and gui < min_hop_gui):
                    min_hops_to_root = self.neighbors[gui]['hops_to_root']
                    min_hop_gui = gui
        if min_hop_gui != 99999:
            selected_addr = self.neighbors[min_hop_gui]['source']
            self.send_join_request(selected_addr)
        self.set_timer('TIMER_JOIN_REQUEST_SEND', 5)

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
        for gui, pck in self.neighbors_table.items():
            if self.now - pck['arrival_time'] > 3 * config.HEARTBEAT_INTERVAL:
                will_be_removed.append(gui)
                if gui == self.parent_gui:
                    parent_dead = True
                if gui in self.descendants.keys():
                    del self.descendants[gui]
                    childs_updated = True
                if gui in self.candidate_parents:
                    self.candidate_parents.remove(gui)
        for gui in will_be_removed:
            del self.neighbors[gui]
        if self.role != Roles.UNREGISTERED:
            if parent_dead:
                self.repair()
            else:
                self.send_heart_beat()
                self.set_timer('TIMER_HEART_BEAT', config.HEARTBEAT_INTERVAL)
                if childs_updated:
                    if self.role != Roles.ROOT:
                        self.send_network_update()

    def route_and_forward(self, pck):
        """Routes and forwards a multi-hop message according to cluster-mesh rules.

        Args:
            pck (Dict): package to be routed and forwarded
        Returns:

        """
        #self.log("🚛 %s: Routing %s to destination %s..." % (str(self.addr), pck['type'], str(pck['dest'])))
        pck['next_hop'] = None
        if self.role != Roles.ROOT and self.parent_gui is not None:
            log_string = "🚛 %s: Next hop: parent %s" % (str(self.addr), str(self.neighbors[self.parent_gui]['addr']))
            pck['next_hop'] = self.neighbors[self.parent_gui]['addr']
        if self.ch_addr is not None:
            if pck['dest'].net_addr == self.ch_addr.net_addr:
                log_string = "🚛 %s: Next hop: cluster member %s" % (str(self.addr), str(self.ch_addr))
                pck['next_hop'] = pck['dest']
        for child_gui, child_networks in self.descendants.items():
            if pck['dest'].net_addr in child_networks:
                log_string = "🚛 %s: Next hop: descendant %s" % (str(self.addr), str(self.neighbors[child_gui]['ch_addr'] or self.neighbors[child_gui]['addr']))
                pck['next_hop'] = self.neighbors[child_gui]['addr']
        # add mesh routing using neighbor tables. overrides tree routing (what to do with routers....)
        # start by collecting all neighbor addresses (only if the neighbor has an addr or ch_addr)
        temp_neighbors_inverted = {(self.neighbors[key]['addr'].net_addr, self.neighbors[key]['addr'].node_addr): key for key in self.neighbors.keys() if self.neighbors[key]['addr'] is not None}
        temp_neighbors_inverted.update({(self.neighbors[key]['addr'].net_addr, self.neighbors[key]['addr'].node_addr): key for key in self.neighbors.keys() if self.neighbors[key]['ch_addr'] is not None})
        #self.log("Poisoned address: %s" % str(self.poisoned_addr))
        
        if self.poisoned_addr is not None:
            # this restriction is here because frequently-used gateways get poisoned the most
            if self.neighbors[temp_neighbors_inverted[(self.poisoned_addr.net_addr, self.poisoned_addr.node_addr)]]['hops_away'] != 1:
                temp_neighbors_inverted.pop((self.poisoned_addr.net_addr, self.poisoned_addr.node_addr))
        # remove non-leaf nodes
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
        if dest_net_addr in [addr[0] for addr in temp_neighbors_inverted.keys()]:
            neighbor_net_addr = dest_net_addr
            node_addr_candidates = [addr[1] for addr in temp_neighbors_inverted.keys() if addr[0] == neighbor_net_addr]
            #self.log(list(node_addr_candidates))
            # if destination is directly a neighbor node...
            if dest_node_addr in node_addr_candidates:
                # make note of the address to use
                #self.log("Found exact match.")
                neighbor_node_addr = dest_node_addr
            # if you have the destination's clusterhead that's good too
            elif 254 in node_addr_candidates:
                #self.log("Found clusterhead of destination.")
                neighbor_node_addr = 254
            # otherwise choose the candidate with the least hops away
            else:
                #self.log("Choosing closest neighbor.")
                hops_away_table = {}
                for node in node_addr_candidates:
                    gui = temp_neighbors_inverted[(dest_net_addr, node)]
                    hops_away_table[node] = self.neighbors[gui]['hops_away']
                #self.log(hops_away_table)
                neighbor_node_addr = min(hops_away_table, key=hops_away_table.get)
            '''for addr in temp_neighbors_inverted.keys():
                if addr[0] == neighbor_net_addr:
                    # okay yeah what we need is to gather the possibilities and make a decision
                    # the biggest thing, i think, is that it doesn't try to reduce hops_away
                    node_addr_candidates.append(addr[1])
                    neighbor_node_addr = addr[1]
                    if neighbor_node_addr == dest_node_addr:
                        break
                    elif neighbor_node_addr == 254:
                        break'''
            neighbor_addr = wsn.Addr(neighbor_net_addr, neighbor_node_addr)
            neighbor_id = temp_neighbors_inverted[(neighbor_net_addr, neighbor_node_addr)]
            #one_hop_neighbor_info = self.neighbors[neighbor_id]
            #self.log(one_hop_neighbor_info)
            one_hop_neighbor_addr = self.neighbors[neighbor_id]['next_hop']
            pck['next_hop'] = one_hop_neighbor_addr
            log_string = "🚛 %s: Next hop: 1-hop neighbor %s, towards neighbor %s" % (str(self.addr), str(one_hop_neighbor_addr), str(neighbor_addr))
                
        if pck['next_hop'] is not None:
            self.poisoned_addr = pck['next_hop']
            pck['ttl'] -= 1
            if config.SIM_ROUTING_LOGS == True:
                self.log(log_string + " TTL: %s" % pck['ttl'])
            if pck['ttl'] <= 0:
                self.log("⛔ %s: %s has expired. Dropping!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" % (str(self.addr), pck['type']))
                return
            self.send(pck)
            self.lose_energy()
        else:
            self.log("⛔ %s: %s could not be routed. Dropping!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" % (str(self.addr), pck['type']))

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
                    self.scene.nodecolor(self.id, 0.50, 0.50, 0.50)
                case Roles.UNDISCOVERED:
                    self.scene.nodecolor(self.id, 0.80, 0.31, 0.24) # red
                case Roles.UNREGISTERED:
                    self.scene.nodecolor(self.id, 0.91, 0.59, 0.18) # yellow
                case Roles.REGISTERED:
                    self.scene.nodecolor(self.id, 0.06, 0.52, 0.33) # green
                    # self.draw_tx_range()
                case Roles.ROUTER:
                    self.scene.nodecolor(self.id, 0.62, 0.17, 0.92) # purple
                case Roles.CLUSTER_HEAD:
                    self.scene.nodecolor(self.id, 0.11, 0.21, 0.89) # blue
                    self.draw_tx_range()
                case Roles.ROOT:
                    self.scene.nodecolor(self.id, 0.00, 0.00, 0.00)
                    self.draw_tx_range()
                    self.set_timer('TIMER_EXPORT_CH_CSV', config.EXPORT_CH_CSV_INTERVAL)
                    self.set_timer('TIMER_EXPORT_NEIGHBOR_CSV', config.EXPORT_NEIGHBOR_CSV_INTERVAL)

    def clear_data(self):
        self.erase_parent()

        self.addr = None
        self.ch_addr = None
        self.parent_gui = None
        self.root_addr = None

        self.hops_to_root = 99999

        self.probe_counter = 0
        self.probe_threshold = 5

        self.neighbors = {}
        self.candidate_parents = {}
        self.join_request_senders = {}
        self.members = {} # CH only
        self.descendants = {} # aka "child net table". CH only

    def become_unregistered(self):
        if self.role != Roles.UNDISCOVERED:
            self.kill_all_timers()
        self.clear_data()
        self.set_role(Roles.UNREGISTERED)
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
