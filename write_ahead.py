import json
from os.path import exists

WRITE_AHEAD_LOG_FILE_NAME = "write_ahead_log.json"

class WriteAheadLog:
    def __init__(self):
        if exists(WRITE_AHEAD_LOG_FILE_NAME):
            file = open(WRITE_AHEAD_LOG_FILE_NAME, 'r')
            self.__read_from_json(file)
            file.close()
        else:
            self.log = dict()
    
    def print_log(self):
        for ip in self.log:
            print(ip)
            for entry in self.log[ip]:
                print(f'\t{entry["send_time"]} {entry["file_name"]} {entry["receiver_unacked_parts"]}')

    def __write_to_file(self):
        file = open(WRITE_AHEAD_LOG_FILE_NAME, 'w')
        try:
            json.dump(self.log, file)
            file.close()
        except KeyboardInterrupt:
            file.close()
            print("Quitting after write is finished!")
            self.__write_to_file()
            exit(0)
    
    def __read_from_json(self, file):
        try:
            self.log = json.load(file)
        except json.decoder.JSONDecodeError:
            self.log = dict()

    def add_entry(self, ip, send_time, file_name):
        if ip not in self.log:
            self.log[ip] = list()
        self.log[ip].append(dict(send_time=send_time, file_name=file_name, receiver_unacked_parts=[]))
        self.__write_to_file()

    def ack_part(self, ip, file_name, part_number):
        if ip not in self.log:
            return
        for entry in self.log[ip]:
            if entry['file_name'] == file_name:
                if part_number in entry['receiver_unacked_parts']:
                    entry['receiver_unacked_parts'].remove(part_number)
                if len(entry['receiver_unacked_parts']) == 0:
                    self.log[ip].remove(entry)
                    self.__write_to_file()
                    return
        self.__write_to_file()
    
    def remove_entry(self, ip, file_name):
        if ip not in self.log:
            return
        for entry in self.log[ip]:
            if entry['file_name'] == file_name:
                self.log[ip].remove(entry)
                self.__write_to_file()
                return
        self.__write_to_file()
    
    def update_send_time(self, time, ip, file_name):
        if ip not in self.log:
            return
        for entry in self.log[ip]:
            if entry['file_name'] == file_name:
                entry['send_time'] = time
                self.__write_to_file()
                return
        self.__write_to_file()
    
    def update_receiver_unacked_parts(self, ip, file_name, part_number):
        if ip not in self.log:
            return
        for entry in self.log[ip]:
            if entry['file_name'] == file_name:
                if part_number not in entry['receiver_unacked_parts']:
                    entry['receiver_unacked_parts'].append(part_number)
                self.__write_to_file()
                return
        self.__write_to_file()

