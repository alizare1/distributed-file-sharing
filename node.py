import socket
from socket import error as SocketError
import pickle
import threading
import select
import os.path
import sys
from time import sleep
from packet import *
from file import File
from write_ahead import WriteAheadLog
from datetime import datetime
from difflib import SequenceMatcher

HOST = "0.0.0.0"
PORT = 8081
BT_PORT = 4

ACK_LIMIT = 20 #seconds
SIMILARITY_MIN_THRESHOLD = 0.8

CLOSED_SOCKET = 1

def get_my_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


class Node:
    def __init__(self, ip, write_ahead_log):
        self.ip = ip
        print(f'IP: {self.ip}')
        self.write_ahead_log = write_ahead_log
        self.files_buffer = {}
        self.sock = None
        self.neighbors_sock = {} # maps IP to sock
        self.neighbors_ip = {} # maps sock to IP
        self.routes = {} # maps ip to neighbors' ip

    def retransmit_packets_after_failure(self):
        log = self.write_ahead_log.log
        for ip in log:
            for entry in log[ip]:
                print(f'Retransmitting {entry["file_name"]} to {ip}')
                self.join(ip, PORT)
                self.send_file(ip, entry["file_name"])

    def send_packet(self, ip, packet):
        if ip not in self.routes or self.routes[ip] not in self.neighbors_sock:
            print(f'Given IP is unknown ({ip})')
            return
        
        s = self.neighbors_sock[self.routes[ip]]
        print(f'sending {MessageType.to_str(packet.type)} to {ip} (using {self.routes[ip]})')
        _, pickled_packet = create_pickled_packet(packet, None)
        s.sendall(pickled_packet)

    def list_neighbors(self):
        for n in self.neighbors_sock.keys():
            print(n)

    def remove_neighbor(self, conn):
        self.neighbors_sock.pop(self.neighbors_ip[conn])
        self.routes.pop(self.neighbors_ip[conn])
        self.neighbors_ip.pop(conn)

    def check_for_time_out_acks(self):
        while True:
            for ip in self.write_ahead_log.log:
                for entry in self.write_ahead_log.log[ip]:
                    if (datetime.utcnow() - datetime.strptime(entry["send_time"], '%Y-%m-%d %H:%M:%S.%f')).seconds > ACK_LIMIT:
                        print(f'ACK timed out for {entry["file_name"]} to {ip}')
                        print(f'Retransmitting {entry["file_name"]} to {ip}')
                        self.write_ahead_log.remove_entry(ip, entry["file_name"])
                        self.send_file(ip, entry["file_name"], False)
            sleep(1)

    def join(self, ip, port, is_bt=False):
        if is_bt:
            s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        else:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((ip, port))
        self.neighbors_ip[s] = ip
        self.neighbors_sock[ip] = s
        self.routes[ip] = ip

    def add_in_write_ahead_log(self, ip, send_time, file_name):
        self.write_ahead_log.add_entry(ip, send_time, file_name)

    def threaded_send_file(self, ip, file_name, update_log=True):
        if ip not in self.routes or self.routes[ip] not in self.neighbors_sock:
            print(f'Given IP is unknown ({ip})')
            return
        f = open(file_name, 'rb')
        data = f.read()
        f.close()
        packets = create_data_packets(MessageType.FILE_TRANFER, self.ip, ip, data, file_name)
        s = self.neighbors_sock[self.routes[ip]]
        if update_log:
            self.add_in_write_ahead_log(ip, str(datetime.utcnow()), file_name)
        for p, n in packets:
            self.write_ahead_log.update_receiver_unacked_parts(ip, file_name, n)
            try:
                s.sendall(p)
            except OSError:
                print('Other node probably got disconnected')
                return

    def send_file(self, ip, file_name, update_log=True):
        t = threading.Thread(target=self.threaded_send_file, args=(ip, file_name, update_log), daemon=True)
        t.start()

    def has_file(self, file_name):
        if os.path.exists(file_name):
            return True
        for file in os.listdir('.'):
            if SequenceMatcher(None, file, file_name).ratio() >= SIMILARITY_MIN_THRESHOLD:
                return True
        return False
    
    def get_similar_file(self, file_name):
        if os.path.exists(file_name):
            return file_name
        for file in os.listdir('.'):
            if SequenceMatcher(None, file, file_name).ratio() >= SIMILARITY_MIN_THRESHOLD:
                return file
    
    def request_file(self, file_name):
        packet = Data(MessageType.FILE_SEARCH, self.ip, 'ALL')
        packet.file_name = file_name
        for neighbor in self.neighbors_ip.keys():
            _, pickled_packet = create_pickled_packet(packet, None)
            neighbor.sendall(pickled_packet)

    def send_ack(self, ip, part_number, file_name):
        packet = Data(MessageType.ACK, self.ip, ip)
        packet.part_num = part_number
        packet.file_name = file_name
        self.send_packet(ip, packet)

    def handle_packet(self, packet):
        if packet.type == MessageType.FILE_TRANFER:
            if packet.file_name not in self.files_buffer:
                self.files_buffer[packet.file_name] = File()
            f = self.files_buffer[packet.file_name]
            f.add_part(packet)
            self.send_ack(packet.sender, packet.part_num, packet.file_name)
            if (f.is_complete()):
                f.write_file()
                self.files_buffer.pop(packet.file_name)
        elif packet.type == MessageType.ACK:
            self.write_ahead_log.ack_part(packet.sender, packet.file_name, packet.part_num)
            self.write_ahead_log.update_send_time(str(datetime.utcnow()), packet.sender, packet.file_name)
        elif packet.type == MessageType.HAS_FILE:
            if packet.file_name in self.files_buffer:
                return
            p = Data(MessageType.TRANSFER_REQUEST, self.ip, packet.sender)
            p.file_name = packet.file_name
            self.send_packet(packet.sender, p)
        elif packet.type == MessageType.TRANSFER_REQUEST:
            self.send_file(packet.sender, packet.file_name)
    
    def handle_broadcast_packet(self, packet, conn):
        if packet.type == MessageType.FILE_SEARCH:
            if self.has_file(packet.file_name):
                to_send_packet = Data(MessageType.HAS_FILE, self.ip, packet.sender)
                to_send_packet.file_name = self.get_similar_file(packet.file_name)
                self.send_packet(packet.sender, to_send_packet)
            else: # pass on the message
                packet.ttl -= 1
                for neighbor in self.neighbors_ip.keys():
                    if neighbor == conn: # don't send message to where it came from
                        continue
                    self.send_packet(self.neighbors_ip[neighbor], packet)
    
    def update_routes(self, packet, conn):
        self.routes[packet.sender] = self.neighbors_ip[conn]

    def handle_incomming_data(self, sock):
        data = b''
        try:
            for _ in range(BLOCK_SIZE):
                temp = sock.recv(1)
                if not temp:
                    data = b''
                    break

                data += temp

        except ConnectionResetError: # Windows doesn't close socket (so no EOF) when program is closed
            print('dumb windows')
        if not data: # EOF
            print(self.neighbors_ip[sock], 'disconnected!')
            # listening_socks.remove(sock)
            self.remove_neighbor(sock)
            sock.close()
            return CLOSED_SOCKET
        
        p = pickle.loads(data)
        print(f'Received {MessageType.to_str(p.type)} from {p.sender} for part {p.part_num} with ttl {p.ttl}')
        self.update_routes(p, sock)
        if p.ttl <= 0:
            return
        if p.receiver == self.ip:
            self.handle_packet(p)
        elif p.receiver == 'ALL':
            self.handle_broadcast_packet(p, sock)
        else:
            p.ttl -= 1
            self.send_packet(p.receiver, p)
    
    def run_socket(self, bt_name=None):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((HOST, PORT))
        self.sock.listen()
        bt_sock = None
        if bt_name:
            bt_sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
            bt_sock.bind((bt_name, BT_PORT))
            bt_sock.listen()
            print('Bluetooth socket is running')
        while 1:
            listening_socks = [self.sock]
            if bt_name:
                listening_socks.append(bt_sock)
            listening_socks.extend(self.neighbors_ip.keys())
            ready_socks, _, _ = select.select(listening_socks, [], [], 0.5)
            for sock in ready_socks:
                if sock == self.sock or sock == bt_sock: # new connection
                    conn, addr = sock.accept()
                    self.neighbors_sock[addr[0]] = conn
                    self.neighbors_ip[conn] = addr[0]
                    self.routes[addr[0]] = addr[0]
                    listening_socks.append(conn)
                    print(f"Connected by {addr}")

                else:
                    try:
                        ret = self.handle_incomming_data(sock)
                        if ret == CLOSED_SOCKET:
                            listening_socks.remove(sock)
                    except SocketError as e:
                        print(f'Socket error')
                        self.remove_neighbor(sock)
                        listening_socks.remove(sock)
                    except Exception as e:
                        print(f'Exception: {e}')

                    


class CommandHandler:
    def __init__(self, bt_addr=None):
        self.ip = get_my_ip()
        self.node = Node(self.ip, WriteAheadLog())
        t = threading.Thread(target=self.node.run_socket, args=(bt_addr,), daemon=True)
        t.start()
        t2 = threading.Thread(target=self.node.retransmit_packets_after_failure, daemon=True)
        t2.start()
        t3 = threading.Thread(target=self.node.check_for_time_out_acks, daemon=True)
        t3.start()

    def run(self):
        while 1:
            cmd = input('> ').split()
            if not cmd:
                continue
            elif cmd[0] == 'send':
                self.node.send_file(cmd[1], cmd[2])
            elif cmd[0] == 'join':
                if len(cmd) > 2:
                    self.node.join(cmd[1], BT_PORT, True)
                else:
                    self.node.join(cmd[1], PORT)
            elif cmd[0] == 'request':
                self.node.request_file(cmd[1])
            elif cmd[0] == 'list':
                self.node.list_neighbors()
            elif cmd[0] == 'leave':
                pass
            elif cmd[0] == 'help':
                print('''join <ip>\nsend <ip>\nlist - lists neighbors\nhelp - shows this message\nrequest <file>''')
            else:
                print('Invalid command! use "help"')

if __name__ == '__main__':
    bt_addr = None
    if len(sys.argv) > 1:
        bt_addr = sys.argv[1]

    c = CommandHandler(bt_addr)
    c.run()
