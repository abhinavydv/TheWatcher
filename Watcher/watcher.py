from time import sleep
from typing import List, Tuple
from Base.socket_base import Socket, Config
from socket import socket, AF_INET, SOCK_STREAM
from threading import Lock, Thread
from Base.settings import IMG_FORMAT, SERVER_PORT, SERVER_ADDRESS, ACKNOWLEDGEMENT_ITERATION
from Base.constants import ALREADY_CONNECTED, CONTROL_KEYBOARD, CONTROL_MOUSE, STOP_WATCHING, WATCHER, WATCHER_CONTROLLER, WATCHER_SCREEN_READER, SEND_TARGET_LIST
import logging
from pynput.keyboard import Listener, Key, KeyCode
from queue import Queue, Empty


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
        """
            Starts watcher
            returns true if started successfully else false
        """
        if self.running:
            logging.warning("Watcher started without stopping it. Cannot start again.")
            raise Exception("Watcher started without stopping")
        self.socket.close()     # close socket if already open
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
            self.send_data(WATCHER.encode(self.FORMAT))     # send this client's type
            self.send_data(self.config.code.encode(self.FORMAT))   # send this client's unique code
            ack = self.recv_data().decode(self.FORMAT)    # receive "OK"
            if ack == ALREADY_CONNECTED:
                logging.info("Already connected to server. Cannot connect again")
                return False
        except (BrokenPipeError, ConnectionResetError):
            logging.fatal("Connection to server closed unexpectedly. Aborting")
            self.stop()
            return False

        Thread(target=self.update_target_list).start()

        return True

    def update_target_list(self):
        """ 
            Keeps fetching list of targets from Server
        """
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

            # TODO: WARNING: Next line is vulnerable and can result in remote code execution
            # Fix it
            self.target_list = eval(target_list)
            sleep(1)

    def watch(self, target_code):
        """"
            Start screen reader and controller
        """
        self.watching = True
        self.screen_reader = ScreenReader(target_code)
        self.screen_reader.watcher = self
        self.controller = Controller(target_code)
        self.controller.watcher = self
        Thread(target=self.screen_reader.start).start()
        Thread(target=self.controller.start).start()
        return True

    def stop_watching(self):
        """
            Send stop watching request to the server
        """
        self.watching = False
        with self.request_lock:
            try:
                self.send_data(STOP_WATCHING.encode(self.FORMAT))
            except (BrokenPipeError, ConnectionResetError):
                pass

    def stop(self):
        """
            Stop the main watcher client and all its dependents (ScreenReader, Controller, etc.)
        """
        logging.info("Stopping Watcher")
        if self.watching:
            self.stop_watching()
        self.running = False
        self.target_list = []
        self.socket.close()


class ScreenReader(Socket):
    """
        The class with methods to read the target screen
    """

    def __init__(self, target_code: str):
        super().__init__(SERVER_ADDRESS, SERVER_PORT)
        self.target_code = target_code
        self.config = Config()
        self.watcher: Watcher = None

    def start(self):
        """
            Start the screen reader client
        """
        logging.info("Starting Watcher Screen Reader")
        try:
            self.socket.connect(self.addr)
        except (ConnectionRefusedError, TimeoutError):
            logging.fatal("Cannot connect to server. Aborting")
            self.stop()
            return
        logging.info("Connected to server")

        try:
            self.send_data(WATCHER_SCREEN_READER.encode(self.FORMAT))   # send client type
            self.send_data(self.config.code.encode(self.FORMAT))        # send client code
            self.send_data(self.target_code.encode(self.FORMAT))        # send target code
            self.recv_data().decode(self.FORMAT)  # receive "OK"
        except (BrokenPipeError, ConnectionResetError):
            # logging.debug(traceback.format_exc())
            logging.fatal("Connection to server closed unexpectedly. Aborting")
            self.stop()
            return

        self.running = True
        self.run()

    def run(self):
        """
            keep fetching target screen images
            send acknowledgement at every `ACKNOWLEDGEMENT_ITERATION` iteration
        """
        i = 0
        while self.running and self.watcher.watching:
            try:
                self.img = self.recv_data()
                if not self.img:
                    logging.info("Connection to screen reader closed by server.")
                    break
                i += 1
                if i==ACKNOWLEDGEMENT_ITERATION:
                    self.send_data(b"OK")  # send acknowledgement
                    i = 0
            except (BrokenPipeError, ConnectionResetError): # disconnected
                self.running = False   # check in the gui if this is running... If not running, Say connection problem
                logging.info("Screen Reader disconnected from server, stopping watching")
                self.watcher.watching = False
                break
        self.stop()

    def stop(self):
        """
            Stop screen reader only
        """
        self.running = False
        self.socket.close()


class Controller(Socket):
    """switch from pynput to pyautogui
        TODO: 
        The main controller client.
        All controllers (i.e mouse controller, keyboard controller, etc.) use
        the same socket provided by this main controller. To avoid data races
        they all use `control_lock` (an object of `threading.Lock`).
    """

    def __init__(self, target_code):
        super().__init__(SERVER_ADDRESS, SERVER_PORT)
        self.target_code = target_code
        self.control_lock = Lock()
        # self.keyboard_controller = KeyboardController(self.socket, self.control_lock)
        self.mouse_controller = MouseController(self.socket, self.control_lock)
        self.watcher: Watcher = None
        self.config = Config()

    def start(self):
        """
            Start all the controllers
        """
        logging.info("Starting watcher controller")
        # self.keyboard_controller.start()
        # self.socket.connect(self.addr)
        # self.send_data(WATCHER_CONTROLLER.encode(self.FORMAT))
        # self.running = True
        # Thread(target=self.run).start()

        try:
            self.socket.connect(self.addr)
        except (ConnectionRefusedError, TimeoutError):
            logging.fatal("Cannot connect to server. Aborting")
            self.stop()
            return
        logging.info("Connected to server")

        self.mouse_controller.start()
        try:
            self.send_data(WATCHER_CONTROLLER.encode(self.FORMAT))  # send client type
            self.send_data(self.config.code.encode(self.FORMAT))    # send client code
            self.send_data(self.target_code.encode(self.FORMAT))    # send target code
            self.recv_data().decode(self.FORMAT)  # receive "OK"
        except (BrokenPipeError, ConnectionResetError):
            # logging.debug(traceback.format_exc())
            logging.fatal("Connection to server closed unexpectedly. Aborting")
            self.stop()
            return

        self.running = True
        self.run()

    def run(self):
        """
            Each controller has an update function. All those
            are called here at regular intervals after some small delay
        """
        while self.running:
            # self.keyboard_controller.update()
            self.mouse_controller.update()
            sleep(0.001)
            self.running = self.watcher.running
        self.stop()

    def stop(self):
        self.running = False
        # self.keyboard_controller.stop()


class KeyboardController(Socket):
    """
        The keyboard controller.
    """

    def __init__(self, skt: socket, control_lock: Lock) -> None:
        super().__init__(SERVER_ADDRESS, SERVER_PORT, skt)
        self.keys = Queue(0)    # Format example: p345 (pressed code 345) r345 (released code 345)
        self.control_lock = control_lock

    def start(self):
        """
            The key queue is updated every time a key is pressed.
            pynput keyboard listener is used.
        """
        logging.info("Starting Keyboard Controller")
        self.listener = Listener(on_press=self.on_press)
        self.listener.start()

    def stop(self):
        """
            Stop the pynput keyboard listener
        """
        self.listener.stop()

    def on_press(self, key):
        if isinstance(key, Key):
            logging.debug((key.name, key.value))
        elif isinstance(key, KeyCode):
            logging.debug((key.vk, key.combining, key.char))

    def on_release(self, key):
        if isinstance(key, Key):
            logging.debug(key.name, key.value)
        elif isinstance(key, KeyCode):
            logging.debug(key.vk, key.combining, key.char)

    def update(self):
        """
            If key queue is not empty, fetch the keys and send to server.
        """
        if not self.keys.empty():
            with self.control_lock:
                self.send_data(CONTROL_KEYBOARD.encode(self.FORMAT))
                keys = self.get_keys()
                self.send_data(" ".join(keys).encode(self.FORMAT))

    def get_keys(self):
        """
            Gets keys from queue and returns a list containing the keys
        """
        keys = []
        while not self.keys.empty():
            try:
                keys.append(self.keys.get_nowait())
            except Empty:
                break
        return keys


class MouseController(Socket):
    """
        The mouse controller.
        The clicks queue is updated by the GUI.
    """

    def __init__(self, socket: socket, lock: Lock) -> None:
        super().__init__(SERVER_ADDRESS, SERVER_PORT, socket)
        self.clicks = Queue(0)
        self.pos: Tuple[int, int] = (0, 0)
        self.control_lock = lock

    def start(self):
        pass

    def update_mouse_pos(self, _, pos):
        """
            Keep updating the mouse position.
        """
        self.pos = pos

    def get_clicks(self):
        """
            Gets clicks from queue and returns a list containing the clicks
        """
        l = []
        while not self.clicks.empty():
            l.append(self.clicks.get_nowait())
        return l

    def update(self):
        """
            Sends only one click at a time
        """
        if self.clicks.empty():
            return
        click = self.clicks.get_nowait()
        logging.debug(click)
        with self.control_lock:
            self.send_data(CONTROL_MOUSE.encode(self.FORMAT))
            self.send_data(str(click).encode(self.FORMAT))
            self.recv_data()   # Receive acknowledgement

    def stop(self):
        pass


if __name__ == "__main__":
    watcher = Watcher()
    try:
        watcher.start()
    except KeyboardInterrupt:
        watcher.stop()
    logging.info("Watcher stopped")
