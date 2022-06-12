import pickle

BLOCK_SIZE = 2048
DEFAULT_TTL = 10

class MessageType:
    FILE_TRANFER = 0
    JOIN = 1
    FILE_SEARCH = 2
    HAS_FILE = 3
    TRANSFER_REQUEST = 4
    ACK = 5

    _msg_str = {
        FILE_TRANFER: 'File Transfer',
        JOIN: 'Join',
        FILE_SEARCH: 'File Search',
        HAS_FILE: 'Has File',
        TRANSFER_REQUEST: 'Transfer Request',
        ACK: 'ACK'
    }

    @staticmethod
    def to_str(msg):
        return MessageType._msg_str[msg]




class Data:
    def __init__(self, msg_type, sender, receiver):
        self.type = msg_type
        self.sender = sender
        self.receiver = receiver
        self.data = None
        self.file_name = ''
        self.is_last = False
        self.part_num = 0
        self.ttl = DEFAULT_TTL


def get_pickled_size(obj):
    p = pickle.dumps(obj)
    return len(p)

def insert_padding(pickled_data):
    initial_size = len(pickled_data)
    if initial_size > BLOCK_SIZE:
        print(initial_size)
        raise Exception('insert_padding: Packet is larger than BLOCK_SIZE')
    
    return pickled_data + b'0' * (BLOCK_SIZE - initial_size)

def create_pickled_packet(packet, data) -> (int, bytes):
    initial_size = get_pickled_size(packet)
    if data and initial_size >= BLOCK_SIZE - 5:
        print(initial_size)
        raise Exception('get_pickled_packet: Packet has no space for data')
    
    capacity = BLOCK_SIZE - initial_size - 5
    if data:
        packet.data = data[:capacity]
        if (len(data) <= capacity):
            packet.is_last = True
    return capacity, insert_padding(pickle.dumps(packet))

def create_data_packets(msg_type, sender, receiver, data, file_name=''):
    part_num = 0
    while len(data) > 0:
        packet = Data(msg_type, sender, receiver)
        packet.file_name = file_name
        packet.part_num = part_num
        serialized_size, pickled_packet = create_pickled_packet(packet, data)
        yield (pickled_packet, part_num)
        data = data[serialized_size:]
        part_num += 1
