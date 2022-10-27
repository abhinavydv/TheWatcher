from time import sleep
from typing import List
from Base.socket_base import Socket, Config
from socket import socket, AF_INET, SOCK_STREAM
from threading import Lock, Thread
from Base.settings import ALREADY_CONNECTED, SERVER_PORT, SERVER_ADDRESS, \
    STOP_WATCHING, WATCHER, WATCHER_SCREEN_READER, SEND_TARGET_LIST
import logging
from pynput.keyboard import Listener


class Watcher(Socket):

    def __init__(self):
        super().__init__(SERVER_ADDRESS, SERVER_PORT)

        self.running = False
        self.watching = False
        self.config = Config()
        self.target_list: List[str] = []

        self.screen_reader = None
        self.controller = None

        self.request_lock = Lock()

    def start(self):
        if self.running:
            logging.warning("Watcher started without stopping it. Cannot start again.")
            raise Exception("Watcher started without stopping")
        self.socket.close()
        self.socket = socket(AF_INET, SOCK_STREAM)
        logging.info("Starting Watcher")
        try:
            self.socket.connect(self.addr)
        except (ConnectionRefusedError, TimeoutError):
            logging.fatal("Cannot connect to server. Aborting")
            self.stop()
            return False
        logging.info("Connected to server")
        self.running = True

        try:
            self.send_data(WATCHER.encode(self.FORMAT))
            self.send_data(self.config.code.encode(self.FORMAT))
            ack = self.recv_data().decode(self.FORMAT)    # receive "OK"
            if ack == ALREADY_CONNECTED:
                logging.info("Already connected to server. Cannot connect again")
                return False
        except (BrokenPipeError, ConnectionResetError):
            logging.fatal("Connection to server closed unexpectedly. Aborting")
            self.stop()
            return False

        Thread(target=self.update_target_list).start()
        # logging.debug("Update started")

        return True

        # print(self.target_list)
        # i = int(input("Enter index: "))
        # self.send_data(self.target_list[i].encode(self.FORMAT))

    def update_target_list(self):
        while self.running:
            with self.request_lock:
                self.send_data(SEND_TARGET_LIST.encode(self.FORMAT))
                try:
                    target_list = self.recv_data().decode(self.FORMAT)
                except OSError:
                    logging.debug("OSError while getting target list. Aborting")
                    self.running = False
                    break
            if not target_list:
                logging.debug("Main watcher connection closed")
                self.running = False
                break
            # WARNING: Next line might be vulnerable and can result in remote code execution
            # Fix it
            self.target_list = eval(target_list)
            sleep(1)

    def watch(self, target_code):
        # with self.request_lock:
        #     try:
        #         self.send_data(WATCH_BY_CODE.encode(self.FORMAT))
        #         self.send_data(target_code.encode(self.FORMAT))
        #     except (ConnectionResetError, BrokenPipeError):
        #         self.stop()
        #         return False
        self.watching = True
        self.screen_reader = ScreenReader(target_code)
        self.screen_reader.watcher = self
        self.controller = Controller(target_code)
        self.controller.watcher = self
        Thread(target=self.screen_reader.start).start()
        Thread(target=self.controller.start).start()
        return True

    def stop_watching(self):
        self.watching = False
        with self.request_lock:
            try:
                self.send_data(STOP_WATCHING.encode(self.FORMAT))
            except (BrokenPipeError, ConnectionResetError):
                pass

    def stop(self):
        logging.info("Stopping Watcher")
        if self.watching:
            self.stop_watching()
        self.running = False
        self.target_list = []
        self.socket.close()


class ScreenReader(Socket):

    def __init__(self, target_code: str):
        super().__init__(SERVER_ADDRESS, SERVER_PORT)
        self.target_code = target_code
        self.config = Config()
        self.watcher: Watcher = None

    def start(self):
        logging.info("Starting Watcher Screen Reader")
        try:
            self.socket.connect(self.addr)
        except (ConnectionRefusedError, TimeoutError):
            logging.fatal("Cannot connect to server. Aborting")
            self.stop()
            return
        logging.info("Connected to server")

        try:
            self.send_data(WATCHER_SCREEN_READER.encode(self.FORMAT))
            self.send_data(self.config.code.encode(self.FORMAT))
            self.send_data(self.target_code.encode(self.FORMAT))
            self.recv_data().decode(self.FORMAT)  # receive "OK"
        except (BrokenPipeError, ConnectionResetError):
            # logging.debug(traceback.format_exc())
            logging.fatal("Connection to server closed unexpectedly. Aborting")
            self.stop()
            return

        self.running = True
        self.run()

    def run(self):
        while self.running and self.watcher.watching:
            try:
                self.img = self.recv_data()
                if not self.img:
                    logging.info("Connection to screen reader closed by server.")
                    break
                # logging.debug("Receiving image from server")
                # with open("img.jpg", "wb") as f:
                #     f.write(self.img)
                self.send_data(b"OK")
            except (BrokenPipeError, ConnectionResetError): # disconnected
                # logging.debug(traceback.format_exc())
                self.running = False   # check in the gui if this is running... If not running, Say connection problem
                logging.info("Screen Reader disconnected from server, stopping watching")
                self.watcher.watching = False
                break
        self.stop()

    def stop(self):
        self.running = False
        self.socket.close()


class Controller(Socket):

    def __init__(self, code):
        super().__init__(SERVER_ADDRESS, SERVER_PORT)

    def start(self):
        pass

    def run(self):
        pass

    def stop(self):
        pass


class KeyboardController(object):

    def __init__(self) -> None:
        pass


if __name__ == "__main__":
    watcher = Watcher()
    try:
        watcher.start()
    except KeyboardInterrupt:
        watcher.stop()
    logging.info("Watcher stopped")