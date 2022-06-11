import socket
import pickle
import threading
import select
import os.path
from packet import *
from file import File
from write_ahead import WriteAheadLog
from datetime import datetime

HOST = "0.0.0.0"
PORT = 8081

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
        self.write_ahead_log = write_ahead_log
        self.files_buffer = {}
        self.sock = None
        self.neighbors_sock = {} # maps IP to sock
        self.neighbors_ip = {} # maps sock to IP
        self.routes = {} # maps ip to neighbors' ip, TODO: maybe make it list

    def send_packet(self, ip, packet):
        if ip not in self.routes or self.routes[ip] not in self.neighbors_sock:
            raise Exception(f'Given IP is unknown ({ip})')
        
        s = self.neighbors_sock[self.routes[ip]]
        print(f'sending to {ip} (using {self.routes[ip]})')
        _, pickled_packet = create_pickled_packet(packet, None)
        s.sendall(pickled_packet)

    def list_neighbors(self):
        for n in self.neighbors_sock.keys():
            print(n)

    def remove_neighbor(self, conn):
        self.neighbors_sock.pop(self.neighbors_ip[conn])
        self.routes.pop(self.neighbors_ip[conn])
        self.neighbors_ip.pop(conn)
        # TODO: alert others, update routes

    def join(self, ip, port): # TODO
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((ip, port))
        self.neighbors_ip[s] = ip
        self.neighbors_sock[ip] = s
        self.routes[ip] = ip

    def add_in_write_ahead_log(self, ip, send_time, file_name, last_part):
        self.write_ahead_log.add_entry(ip, send_time, file_name, last_part)


    def send_file(self, ip, file_name):
        if ip not in self.routes or self.routes[ip] not in self.neighbors_sock:
            raise Exception('Given IP is unknown')
        f = open(file_name, 'rb')
        data = f.read()
        f.close()
        packets = create_data_packets(MessageType.FILE_TRANFER, self.ip, ip, data, file_name)
        s = self.neighbors_sock[self.routes[ip]]
        self.add_in_write_ahead_log(ip, str(datetime.utcnow()), file_name, len(packets)-1)
        for p in packets:
            s.sendall(p)

    def has_file(self, file_name):
        return os.path.exists(file_name)
    
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
        elif packet.type == MessageType.HAS_FILE:
            p = Data(MessageType.TRANSFER_REQUEST, self.ip, packet.sender)
            p.file_name = packet.file_name
            self.send_packet(packet.sender, p)
        elif packet.type == MessageType.TRANSFER_REQUEST:
            self.send_file(packet.sender, packet.file_name)
    
    def handle_broadcast_packet(self, packet, conn): # TODO: handle circular routes, keep history of hops in packet?
        if packet.type == MessageType.FILE_SEARCH:
            if self.has_file(packet.file_name):
                to_send_packet = Data(MessageType.HAS_FILE, self.ip, packet.sender)
                to_send_packet.file_name = packet.file_name
                self.send_packet(packet.sender, to_send_packet)
            else: # pass on the message
                for neighbor in self.neighbors_ip.keys():
                    if neighbor == conn: # don't send message to where it came from
                        continue
                    self.send_packet(self.neighbors_ip[neighbor], packet)
    
    def update_routes(self, packet, conn):
        self.routes[packet.sender] = self.neighbors_ip[conn]
    
    def run_socket(self, host_ip):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((HOST, PORT))
        self.sock.listen()
        while 1:
            listening_socks = [self.sock]
            listening_socks.extend(self.neighbors_ip.keys())
            ready_socks, _, _ = select.select(listening_socks, [], [], 0.5)
            for sock in ready_socks:
                if sock == self.sock: # new connection
                    conn, addr = self.sock.accept()
                    self.neighbors_sock[addr[0]] = conn
                    self.neighbors_ip[conn] = addr[0]
                    self.routes[addr[0]] = addr[0]
                    listening_socks.append(conn)
                    print(f"Connected by {addr}")

                else:
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
                        listening_socks.remove(sock)
                        self.remove_neighbor(sock)
                        sock.close()
                        continue
                    
                    p = pickle.loads(data)
                    print(f'Received {MessageType.to_str(p.type)} from {p.sender} for part {p.part_num}')
                    self.update_routes(p, sock)
                    if p.receiver == host_ip:
                        self.handle_packet(p)
                    elif p.receiver == 'ALL':
                        self.handle_broadcast_packet(p, sock)
                    else:
                        self.send_packet(p.receiver, p)


class CommandHandler:
    def __init__(self):
        self.ip = get_my_ip()
        self.node = Node(self.ip, WriteAheadLog())
        print(f'IP: {self.ip}')
        t = threading.Thread(target=self.node.run_socket, args=(self.ip,), daemon=True)
        t.start()

    def run(self):
        while 1:
            cmd = input('> ').split()
            if not cmd:
                continue
            elif cmd[0] == 'send':
                self.node.send_file(cmd[1], cmd[2])
            elif cmd[0] == 'join':
                self.node.join(cmd[1], PORT)
            elif cmd[0] == 'request':
                self.node.request_file(cmd[1])
            elif cmd[0] == 'list':
                self.node.list_neighbors()
            elif cmd[0] == 'leave':
                pass # TODO
            elif cmd[0] == 'help':
                print('''join <ip>\nsend <ip>\nlist - lists neighbors\nhelp - shows this message\nrequest <file>''')
            else:
                print('Invalid command! use "help"')

if __name__ == '__main__':
    c = CommandHandler()
    c.run()
