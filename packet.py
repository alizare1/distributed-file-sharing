import pickle

BLOCK_SIZE = 300

class MessageType:
    FILE_TRANFER = 0
    JOIN = 1


class Data:
    def __init__(self, msg_type, sender, receiver):
        self.type = msg_type
        self.sender = sender
        self.receiver = receiver
        self.data = None
        self.file_name = ''
        self.is_last = False
        self.part_num = 0


def get_pickled_size(obj):
    p = pickle.dumps(obj)
    return len(p)

def insert_padding(pickled_data):
    initial_size = len(pickled_data)
    if initial_size > BLOCK_SIZE:
        raise Exception('insert_padding: Packet is larger than BLOCK_SIZE')
    
    return pickled_data + b'0' * (BLOCK_SIZE - initial_size)

def create_pickled_packet(packet, data):
    packet.data = None
    initial_size = get_pickled_size(packet)
    if initial_size >= BLOCK_SIZE - 5:
        raise Exception('get_pickled_packet: Packet has no space for data')
    
    capacity = BLOCK_SIZE - initial_size - 5
    packet.data = data[:capacity]
    if (len(data) <= capacity):
        packet.is_last = True
    return capacity, insert_padding(pickle.dumps(packet))

def create_data_packets(msg_type, sender, receiver, data, file_name=''):
    packets = []
    part_num = 0
    while len(data) > 0:
        packet = Data(msg_type, sender, receiver)
        packet.file_name = file_name
        packet.part_num = part_num
        serialized_size, pickled_packet = create_pickled_packet(packet, data)
        packets.append(pickled_packet)
        data = data[serialized_size:]
        part_num += 1
    return packets
