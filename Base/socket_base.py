from socket import socket, AF_INET, SOCK_STREAM
import platform
import logging
import json


root = logging.getLogger()
root.setLevel(logging.DEBUG)

# handler = logging.StreamHandler(sys.stdout)
# handler.setLevel(logging.DEBUG)
# formatter = logging.Formatter('%(asctime)s - %(name)s - '
#     '%(levelname)s - %(message)s')
# handler.setFormatter(formatter)
# root.addHandler(handler)

class Config:
    """Contains configurations from config.json
    """
    def __init__(self):
        with open("config.json", "r") as f:
            self.config = json.load(f)
        self.code: str = self.config["code"]
        self.IMG_FORMAT = self.config["IMG_FORMAT"]


class Socket(object):
    """
        An extension on socket.io to atomize sending and receiving all data
        TODO: Encrypt all communication
    """

    def __init__(self, IP='127.0.0.1', port=33333, skt: socket = None) -> None:
        """
            If `skt` is None a new socket object is created
        """
        if skt:
            self.socket = skt
        else:
            self.socket = socket(AF_INET, SOCK_STREAM)
        self.platform = platform.platform().lower()
        self.IP = IP
        self.port = port
        self.HEADER = 64
        self.FORMAT = "utf-8"
        self.addr = (IP, port)
        self.running = False

    def send_data(self, data: bytes, conn: socket = None):
        """
            sends all data over `conn` or `self.socket`.
            Blocks untill all data is sent or an error in encountered
        """
        if conn is None:
            conn = self.socket
        ln = str(len(data)).encode(self.FORMAT)

        # send length of data
        conn.sendall(ln + ' '.encode(self.FORMAT)*(64-len(ln)))  
        conn.sendall(data)  # send data

    def recv_data(self, conn: socket = None) -> bytes:
        """
            receives all data from `conn` or `self.socket`.
            Blocks untill all data is sent or an error in encountered
        """
        if conn is None:
            conn = self.socket
        ln = data = b''
        t = self.HEADER

        # first get length of data
        while t:
            temp = conn.recv(t)
            if not temp:
                return b''
            ln += temp
            t -= len(temp)
        ln = int(ln)

        # then get data
        while ln:
            temp = conn.recv(ln)
            if not temp:
                return b''
            ln -= len(temp)
            data += temp

        return data

    def run(self):
        pass

    def stop(self):
        pass
