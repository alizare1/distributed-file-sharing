import socket
import pickle
import threading
import select
from packet import *
from file import File

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
    def __init__(self, ip):
        self.ip = ip
        self.files_buffer = {}
        self.sock = None
        self.neighbors_sock = {} # maps IP to sock
        self.neighbors_ip = {} # maps sock to IP

    def list_neighbors(self):
        for n in self.neighbors_sock.keys():
            print(n)

    def remove_neighbor(self, conn):
        self.neighbors_sock.pop(self.neighbors_ip[conn])
        self.neighbors_ip.pop(conn)
        # TODO: alert others

    def join(self, ip, port): # TODO
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((ip, port))
        self.neighbors_ip[s] = ip
        self.neighbors_sock[ip] = s

    def send_file(self, ip, file_name):
        if ip not in self.neighbors_sock:
            raise Exception('Given IP is unknown')
        f = open(file_name, 'rb')
        data = f.read()
        f.close()
        packets = create_data_packets(MessageType.FILE_TRANFER, self.ip, ip, data, file_name)
        for p in packets:
            self.neighbors_sock[ip].sendall(p)

    def handle_packet(self, packet):
        if packet.type == 0:
            if packet.file_name not in self.files_buffer:
                self.files_buffer[packet.file_name] = File()
            f = self.files_buffer[packet.file_name]
            f.add_part(packet)
            if (f.is_complete()):
                f.write_file()
                self.files_buffer.pop(packet.file_name)

    def forward_packet(self, packet):
        if packet.receiver in self.neighbors_sock:
            self.neighbors_sock[packet.receiver].sendall(packet)
    
    def run_socket(self, host_ip):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((HOST, PORT))
        self.sock.listen()
        listening_socks = [self.sock]
        while 1:
            ready_socks, _, _ = select.select(listening_socks, [], [])
            for sock in ready_socks:
                if sock == self.sock: # new connection
                    conn, addr = self.sock.accept()
                    self.neighbors_sock[addr[0]] = conn
                    self.neighbors_ip[conn] = addr[0]
                    listening_socks.append(conn)
                    print(f"Connected by {addr}")

                else:
                    data = None
                    try:
                        data = sock.recv(BLOCK_SIZE)
                    except ConnectionResetError: # Windows doesn't close socket (so no EOF) when program is closed
                        print('dumb windows')
                    if not data: # EOF
                        print(self.neighbors_ip[conn], 'disconnected!')
                        listening_socks.remove(conn)
                        self.remove_neighbor(conn)
                        conn.close()
                        continue
                    
                    p = pickle.loads(data)
                    if p.receiver == host_ip or True:
                        self.handle_packet(p)
                    else:
                        self.forward_packet(p)


class CommandHandler:
    def __init__(self):
        self.ip = get_my_ip()
        self.node = Node(self.ip)
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
            elif cmd[0] == 'list':
                self.node.list_neighbors()
            elif cmd[0] == 'leave':
                pass # TODO
            elif cmd[0] == 'help':
                print('''join <ip>\nsend <ip>\nlist - lists neighbors\nhelp - shows this message''')
            else:
                print('Invalid command! use "help"')

if __name__ == '__main__':
    c = CommandHandler()
    c.run()