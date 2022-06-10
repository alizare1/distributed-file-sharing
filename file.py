from packet import *

class File:
    def __init__(self):
        self.parts = []
        self.parts_tracker = set()
        self.last_part = None

    def add_part(self, part):
        if part.part_num in self.parts_tracker:
            return
        self.parts_tracker.add(part.part_num)
        self.parts.append(part)
        if part.is_last:
            self.last_part = part

    def is_complete(self):
        return self.last_part and len(self.parts) == self.last_part.part_num + 1
    
    def write_file(self):
        self.parts.sort(key=lambda x: x.part_num)
        f = open(f'rcv_{self.last_part.file_name}', 'wb')
        for p in self.parts:
            f.write(p.data)
        f.close()
        print(self.last_part.file_name, 'downloaded!')
