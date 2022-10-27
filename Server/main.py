import errno
import os
from time import sleep, time
from typing import Dict
from Base.socket_base import Socket
from socket import SHUT_RDWR, socket
from threading import Thread
from Base.settings import ALREADY_CONNECTED, SERVER_PORT, SERVER_ADDRESS, STOP_WATCHING, TARGET_RUNNING, \
    TARGET_SCREEN_READER, TARGET_CONTROLLER, DISCONNECT, TARGET_WAITING, WATCHER, WATCHER_CONTROLLER,\
        WATCHER_SCREEN_READER, SEND_TARGET_LIST
import logging


class Server(Socket):

    def __init__(self):
        super().__init__(SERVER_ADDRESS, SERVER_PORT)

        self.running = False
        self.targets: Dict[str, Socket] = {}   # List of access codes of all targets available for watching
        self.target_screens: Dict[str, Socket] = {} # Screen readers of all targets which are being watched
        self.target_controllers: Dict[str, Socket] = {} # Controllers of all targets which are being watched
        self.watchers: Dict[str, Socket] = {}  # access codes and sockets of all watchers
        self.screen_watchers: Dict[str, Socket] = {}
        self.controller_watchers: Dict[str, Socket] = {}
        self.img = b""

    def start(self):
        self.running = True
        try:
            self.socket.bind(self.addr)
        except OSError as e:
            if e.errno == errno.EADDRINUSE:
                logging.fatal(f"Address {self.addr} already in use")
                return
        self.socket.listen()
        self.run()

    def run(self):
        try:
            while self.running:
                logging.info("Accepting connection")
                client_socket, addr = self.socket.accept()
                logging.info(f"{addr} connected")
                Thread(target=self.handle_client, args=(client_socket,)).start()
        except KeyboardInterrupt:
            logging.info("Stopping Server")
            self.stop()

    def handle_client(self, client_socket: socket):
        client = Socket(SERVER_ADDRESS, SERVER_PORT, client_socket)
        try:
            client_t = client.recv_data()
        except (BrokenPipeError, ConnectionResetError):
            logging.info("Client disconnected...")
            return

        if client_t == b'Hi!':
            self.handle_main_client(client)
        elif client_t == TARGET_SCREEN_READER.encode(self.FORMAT):
            self.handle_target_screen_reader_client(client)
        elif client_t == TARGET_CONTROLLER.encode(self.FORMAT):
            self.handle_target_controller_client(client)
        elif client_t == WATCHER.encode(self.FORMAT):
            self.handle_main_watcher_client(client)
        elif client_t == WATCHER_SCREEN_READER.encode(self.FORMAT):
            self.handle_watcher_screen_reader_client(client)
        elif client_t == WATCHER_CONTROLLER.encode(self.FORMAT):
            self.handle_watcher_controller_client(client)
        elif client_t == "":
            logging.info("Client sent no client type.. disconnecting")
            client.socket.close()
            return
        else:
            raise Exception(f"{client_t} is not a valid type")


    def handle_main_client(self, client: Socket):
        logging.info("Main Target client connected")
        code = client.recv_data().decode(self.FORMAT)
        if code in self.targets:
            logging.info(f"Not allowing target {code} to connect as it is already connected")
            client.socket.close()
            return
        client.watchers = 0
        client.code = code
        client.running = True
        client.status = TARGET_WAITING
        self.targets[code] = client
        try:
            while client.status == TARGET_WAITING and self.running:
                client.send_data(b"WAIT")
                sleep(1)
            client.send_data(b"OK")
            logging.info(f"Main target Client {code} Added")
        except (ConnectionResetError, BrokenPipeError):
            logging.info(f"Removing main target client {code}")
            del self.targets[code]
        # if code in self.targets:
        #     del self.targets[code]

    def handle_target_screen_reader_client(self, target: Socket):
        logging.info("target screen reader client connected")
        code = target.recv_data().decode(self.FORMAT)
        if code in self.target_screens:
            logging.info("Not allowing target screen reader {code} to connect as it is already connected")
            target.send_data(ALREADY_CONNECTED.encode(self.FORMAT))
            target.socket.close()
            return False
        target.img = b""
        target.ready = False
        self.target_screens[code] = target
        target.send_data(b"OK")
        running = True
        while running and self.running:
            try:
                target.img = target.recv_data()
                target.ready = True
                # with open("img.jpg", "wb") as f:
                #     f.write(target.img)
                target.send_data(b"OK")
            except (BrokenPipeError, ConnectionResetError): # client disconnected
                logging.info(f"Removing target screen reader client {code}")
                break

            try:
                running = self.targets[code].running
            except KeyError:
                break
        target.socket.close()
        del self.target_screens[code]
        self.remove_target(code)

    def remove_target(self, code):
        if code in self.targets:
            if self.targets[code].watchers > 0:
                pass
            del self.targets[code]

    def handle_target_controller_client(self, client: Socket):
        code = client.recv_data().decode(self.FORMAT)
        self.target_controllers[code] = client
        client.send_data(b"OK")

    def handle_main_watcher_client(self, watcher: Socket):
        logging.info("Main Watcher client connected")

        try:
            code = watcher.recv_data().decode(self.FORMAT)
            if code in self.watchers:
                logging.info("Not allowing watcher {code} to connect as it is already connected")
                watcher.send_data(ALREADY_CONNECTED.encode(self.FORMAT))
                watcher.socket.close()
                return False
            watcher.send_data(b"OK")
            self.watchers[code] = watcher
        except (BrokenPipeError, ConnectionResetError):
            logging.info(f"Connection to Main Watcher {code} failed unexpectedly. Removing it.")
            self.remove_watcher(code)
            return

        while self.running:
            try:
                request = watcher.recv_data().decode(self.FORMAT)
                if request == SEND_TARGET_LIST:
                    watcher.send_data(str(list(self.targets.keys())).encode(self.FORMAT))
                # elif request == WATCH_BY_CODE:
                #     target_code = watcher.recv_data().decode(self.FORMAT)
                #     if not target_code:
                #         del self.watchers[code]
                #         return
                #     target = self.targets[target_code]
                #     watcher.target = target
                #     target.running = True
                #     target.watchers += 1
                #     target.status = TARGET_RUNNING

                elif request == STOP_WATCHING:
                    # REMEMBER: decrement target.watcher after screen_reader deletes itself
                    watcher.running = False
                    sleep(2)    # sleep for 2 seconds so that screen_reader and controller disconnect themselves

                elif request == DISCONNECT or request == "":
                    watcher.socket.close()
                    self.remove_watcher(code)

                else:
                    raise Exception(f"Request '{request}' not defined!")
            except (BrokenPipeError, ConnectionResetError, OSError):
                logging.info(f"Connection to Main Watcher {code} closed. Removing it.")
                self.remove_watcher(code)
                return

    def remove_watcher(self, code: str):
        """After main watcher is removed screen reader 
        and controller remove themselves"""
        if code in self.watchers:
            del self.watchers[code]

    def handle_watcher_screen_reader_client(self, watcher: Socket):
        logging.info(f"Watcher screen reader client connected")
        try:
            code = watcher.recv_data().decode(self.FORMAT)
            target_code = watcher.recv_data().decode(self.FORMAT)
            watcher.send_data(b"OK")
        except (BrokenPipeError, ConnectionResetError):
            logging.debug("Watcher screen reader disconnected. Removing it and stopping watching")
            return
        target = self.targets[target_code]
        target.watchers += 1
        target.running = True
        target.status = TARGET_RUNNING
        while target_code not in self.target_screens:
            logging.debug("WAiting for target screen to connect")
            sleep(0.1)
        logging.debug("Getting target screen")
        target_screen = self.target_screens[target_code]
        while not target_screen.ready:
            sleep(0.1)
        running = True
        logging.debug(f"{self.targets[target_code].watchers} watchers connected")
        self.watchers[code].running = True
        while running and self.running:
            try:
                # t1 = time()
                # logging.debug("Sending image")
                # if os.path.exists("img2.jpg"):
                #     with open("img2.jpg", "rb") as f:
                #         logging.debug(str(f.read() == target_screen.img))
                # with open("img2.jpg", "wb") as f:
                #     f.write(target_screen.img)
                if target_code not in self.targets:
                    watcher.socket.close()
                    break
                watcher.send_data(target_screen.img)
                watcher.recv_data()  # receive "OK"
                sleep(0.02)
                # logging.debug(time()-t1)
            except (BrokenPipeError, ConnectionResetError):
                logging.debug("Screen reader disconnected. Removing it and stopping watching")
                break
            try:
                running = self.watchers[code].running
            except KeyError:
                logging.debug("Watcher disconnected. Removing screen reader")
                watcher.socket.close()
                break

        if target_code in self.targets:
            self.targets[target_code].watchers -= 1
            if (self.targets[target_code].watchers == 0):
                self.targets[target_code].running = False
                logging.info(f"Removing target screen reader client {code} as no watcher is watching it.")

    def handle_watcher_controller_client(self, watcher: Socket):
        pass

    def stop(self):
        self.running = False
        self.socket.close()


if __name__ == "__main__":
    server = Server()
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()

    logging.info("Server stopped")