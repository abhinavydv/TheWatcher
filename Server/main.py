from Base.constants import CONTROL_MOUSE, STOP_WATCHING, TARGET_RUNNING, \
    TARGET_SCREEN_READER, TARGET_CONTROLLER, DISCONNECT, TARGET_WAITING, \
    WATCHER, WATCHER_CONTROLLER, WATCHER_SCREEN_READER, \
    SEND_TARGET_LIST, ALREADY_CONNECTED, ImageSendModes
from Base.settings import SERVER_PORT, SERVER_ADDRESS, WEB_SERVER_ADDRESS, \
    WEB_SERVER_PORT, ACKNOWLEDGEMENT_ITERATION, ADDRESS_TYPE, IMAGE_SEND_MODE
from Base.socket_base import Socket
import errno
from http.server import SimpleHTTPRequestHandler
from io import BytesIO
from queue import Queue
import logging
from PIL import Image, ImageChops, UnidentifiedImageError
from socket import socket, SO_REUSEADDR, SOL_SOCKET
from socketserver import TCPServer
from threading import Thread
from time import sleep, time
from typing import Dict


pil_logger = logging.getLogger("PIL")
pil_logger.setLevel(logging.INFO)


class Server(Socket):
    """
    TODO: use a thread lock while incrementing or decrementing 
        the `target.watchers` property
    """

    def __init__(self):
        super().__init__(SERVER_ADDRESS, SERVER_PORT)

        self.running = False

        # List of access codes of all targets available for watching
        self.targets: Dict[str, Socket] = {}

        # Screen readers of all targets which are being watched
        self.target_screens: Dict[str, Socket] = {}

        # Controllers of all targets which are being watched
        self.target_controllers: Dict[str, Socket] = {}

        # mapping for target and mouse events
        self.mouse_events: Dict[str, Queue[bytes]] = {}

        # access codes and sockets of all watchers
        self.watchers: Dict[str, Socket] = {}

        self.screen_watchers: Dict[str, Socket] = {}
        self.controller_watchers: Dict[str, Socket] = {}
        self.img = b""

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
            Thread(target=self.start_file_server, args=("/srv/fileShare",)).start()
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
        if client_t == b'Hi!':
            self.handle_main_target_client(client)
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
        code = client.recv_data().decode(self.FORMAT)

        # don't allow two target clients with same code to connect
        if code in self.targets:
            client.send_data(ALREADY_CONNECTED.encode(self.FORMAT))
            logging.info(f"Not allowing target {code} to connect "
            "as it is already connected")
            client.socket.close()
            return
        client.watchers = 0     # No. of watchers wathing this target
        client.code = code
        client.running = True
        client.status = TARGET_WAITING
        self.targets[code] = client
        try:
            # wait untill a watcher starts to watch
            while client.status == TARGET_WAITING and self.running:
                client.send_data(b"WAIT")
                sleep(1)
            client.send_data(b"OK")
            logging.info(f"Main target Client {code} Added")
        except (ConnectionResetError, BrokenPipeError):
            logging.info(f"Removing main target client {code}")
            del self.targets[code]

    def handle_target_screen_reader_client(self, target: Socket):
        """
            The `target` object has img object which is set to the image
            received from the target client.
        """
        logging.info("target screen reader client connected")
        code = target.recv_data().decode(self.FORMAT)
        if code in self.target_screens:
            logging.info("Not allowing target screen reader {code} "
                "to connect as it is already connected")
            target.send_data(ALREADY_CONNECTED.encode(self.FORMAT))
            target.socket.close()
            return False
        target.img = b""
        target.ready = False
        self.target_screens[code] = target
        target.send_data(b"OK")
        running = True
        i = 0
        prev_img = None

        # while server is running and the target is connected and running
        while running and self.running:
            try:
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

                    # diff = np.array(Image.open(bio))
                    # if prev_img is None:
                    #     img = diff
                    # else:
                    #     img = prev_img - diff
                    prev_img = img
                    # img = Image.fromarray(img)
                    bio = BytesIO(b"")
                    img.save(bio, format="JPEG")
                    # target.img = diff
                    target.img = bio.getvalue()

                    t5 = time()
                    logging.debug(f"{t2-t1}, {t3-t2}, {t4-t3}, {t5-t4}, {i}")

                target.ready = True
                i += 1
                if i==ACKNOWLEDGEMENT_ITERATION:
                    target.send_data(b"OK")
                    i = 0
                running = self.targets[code].running

            except (BrokenPipeError, ConnectionResetError, KeyError, UnidentifiedImageError): 
                # client disconnected
                logging.info(f"Removing target screen reader client {code}")
                break

        target.socket.close()
        del self.target_screens[code]
        self.remove_target(code)

    # fix this: all watchers disconnect when one of them disconnects
    def remove_target(self, code):
        """
            removes target from `self.targets` if present.
        """
        if code in self.targets:
            if self.targets[code].watchers > 0:
                pass
            del self.targets[code]

    def handle_target_controller_client(self, target: Socket):
        """
            Create a queue for each controller for this target.
            The watcher contoller will populate the queue.
            Fetch the control values from queue and send to target.
        """
        code = target.recv_data().decode(self.FORMAT)
        if code in self.target_controllers:
            logging.info("Not allowing target controller {code} to "
                "connect as it is already connected")
            target.send_data(ALREADY_CONNECTED.encode(self.FORMAT))
            target.socket.close()
            return False
        self.target_controllers[code] = target
        self.mouse_events[code] = Queue(0)
        target.send_data(b"OK")

        running = True
        while running and self.running:

            try:
                # handle mouse events
                if not self.mouse_events[code].empty():
                    target.send_data(CONTROL_MOUSE.encode(self.FORMAT))
                    target.send_data(self.mouse_events[code].get())
                    # target.recv_data()    # reveive 'OK'
            except (BrokenPipeError, ConnectionResetError):
                logging.info(f"Connection to target controller client {code} "
                    "failed unexpectedly. Removing it.")
                break

            try:
                running = self.targets[code].running
            except KeyError:
                break
            sleep(0.0001)

        target.socket.close()
        del self.target_controllers[code]
        if code in self.targets:
            self.targets[code].running = False

    def handle_main_watcher_client(self, watcher: Socket):
        """
            The main watcher client connects and sends requests
            that are to be served.
        """

        logging.info("Main Watcher client connected")

        try:
            code = watcher.recv_data().decode(self.FORMAT)
            if code in self.watchers:
                logging.info("Not allowing watcher {code} "
                    "to connect as it is already connected")
                watcher.send_data(ALREADY_CONNECTED.encode(self.FORMAT))
                watcher.socket.close()
                return False
            watcher.send_data(b"OK")
            self.watchers[code] = watcher
        except (BrokenPipeError, ConnectionResetError):
            logging.info(f"Connection to Main Watcher {code} "
                "failed unexpectedly. Removing it.")
            self.remove_watcher(code)
            return

        while self.running:
            try:
                request = watcher.recv_data().decode(self.FORMAT)
                if request == SEND_TARGET_LIST:
                    watcher.send_data(str(list(self.targets.keys()))
                        .encode(self.FORMAT))
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
                    """
                        TODO: decrement target.watcher after 
                            screen_reader deletes itself
                    """
                    watcher.running = False

                    """
                        sleep for 2 seconds so that screen_reader 
                        and controller disconnect themselves
                    """
                    sleep(2)

                elif request == DISCONNECT or request == "":
                    watcher.socket.close()
                    self.remove_watcher(code)

                else:
                    raise Exception(f"Request '{request}' not defined!")
            except (BrokenPipeError, ConnectionResetError, OSError):
                logging.info(f"Connection to Main Watcher {code} "
                    "closed. Removing it.")
                self.remove_watcher(code)
                return

    def remove_watcher(self, code: str):
        """
            After main watcher is removed screen reader 
            and controller automatically remove themselves
        """
        if code in self.watchers:
            del self.watchers[code]

    def handle_watcher_screen_reader_client(self, watcher: Socket):
        """
            Screen reader connects to the server and sends 
            target images to the watcher.
        """
        logging.info(f"Watcher screen reader client connected")
        try:
            code = watcher.recv_data().decode(self.FORMAT)
            target_code = watcher.recv_data().decode(self.FORMAT)
            watcher.send_data(b"OK")
        except (BrokenPipeError, ConnectionResetError):
            logging.debug("Watcher screen reader disconnected. "
                "Removing it and stopping watching")
            return

        # get the main target object
        target = self.targets[target_code]
        target.watchers += 1
        target.running = True
        target.status = TARGET_RUNNING

        # wair for the target screen to connect
        while target_code not in self.target_screens:
            logging.debug("Waiting for target screen to connect")
            sleep(0.1)
        logging.debug("Getting target screen")
        target_screen = self.target_screens[target_code]
        while not target_screen.ready:
            sleep(0.1)
        running = True
        logging.debug(f"{self.targets[target_code].watchers} "
            "watchers connected")
        self.watchers[code].running = True
        i = 0
        while running and self.running:
            try:
                if target_code not in self.targets:
                    watcher.socket.close()
                    break
                while not target_screen.ready:
                    sleep(0.01)
                target.ready = False
                watcher.send_data(target_screen.img)
                i += 1
                if i==ACKNOWLEDGEMENT_ITERATION:
                    watcher.recv_data()  # receive acknowledgement
                    i = 0
                sleep(0.01)
            except (BrokenPipeError, ConnectionResetError):
                logging.debug("Screen reader disconnected. Removing "
                    "it and stopping watching")
                break
            try:
                running = self.watchers[code].running
            except KeyError:
                logging.debug("Watcher disconnected. Removing screen reader")
                watcher.socket.close()
                break

        # decrement `target.watchers` when disconnecting.
        # Remove the target if `target.watchers` becomes 0
        if target_code in self.targets:
            self.targets[target_code].watchers -= 1
            if (self.targets[target_code].watchers == 0):
                self.targets[target_code].running = False
                logging.info(f"Removing target screen reader client {code} "
                    "as no watcher is watching it.")

    def handle_watcher_controller_client(self, watcher: Socket):
        """
            Gets the controller request for the given watcher and forwards
            it to the `handle_watcher_controllers` method.
        """
        logging.info(f"Watcher controller client connected")
        try:
            code = watcher.recv_data().decode(self.FORMAT)
            target_code = watcher.recv_data().decode(self.FORMAT)
            watcher.send_data(b"OK")
        except (BrokenPipeError, ConnectionResetError):
            logging.debug("Watcher screen reader disconnected. Removing it "
                "and stopping watching")
            return

        running = True
        while running and self.running:
            try:
                if target_code not in self.targets:
                    watcher.socket.close()
                    break
                self.handle_watcher_controllers(watcher, target_code)
            except (BrokenPipeError, ConnectionResetError):
                logging.debug("Controller disconnected. Removing it and "
                    "stopping watching")
                break

            try:
                running = self.watchers[code].running
            except KeyError:
                logging.debug("Watcher disconnected. Removing controller")
                watcher.socket.close()
                break

    def handle_watcher_controllers(self, watcher: Socket, target_code):
        """
            All kinds of controller requests are handled here.
        """
        control_type = watcher.recv_data().decode(self.FORMAT)

        # handle mouse controller requests
        if control_type == CONTROL_MOUSE:
            mouse_event = watcher.recv_data()
            if target_code in self.target_controllers:
                self.mouse_events[target_code].put(mouse_event)

        # watcher.send_data(b"OK")

    def start_file_server(self, path):
        """
            Starts the file server that the target script will
            use to download the main code and the dependencies.
        """
        Handler = lambda *args, **kwargs: SimpleHTTPRequestHandler(
            *args, directory=path, **kwargs
        )

        with CustomTCPServer((WEB_SERVER_ADDRESS, WEB_SERVER_PORT), Handler) as server:
            self.file_server_running = True
            self.file_server = server
            server.allow_reuse_address = True
            logging.info(f"Starting file server at {WEB_SERVER_ADDRESS}:{WEB_SERVER_PORT}")
            server.serve_forever()
        self.file_server_running = False

    def stop(self):
        if self.file_server_running:
            pass
        self.running = False
        self.socket.close()


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
