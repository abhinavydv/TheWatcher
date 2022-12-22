from Base.constants import ALREADY_CONNECTED, CONTROL_MOUSE, \
    TARGET_SCREEN_READER, TARGET_CONTROLLER, DISCONNECT, ImageSendModes, \
    ControlEvents
from Base.settings import ACKNOWLEDGEMENT_ITERATION, \
    SERVER_PORT, SERVER_ADDRESS, IMAGE_SEND_MODE
from Base.socket_base import Socket, Config
import logging
import numpy as np
from PIL import Image, ImageChops
from pynput.mouse import Controller as MouseController, Button as MouseButton
from queue import Queue, Empty
import subprocess
from threading import Thread
from time import sleep, time
import traceback


try:
    from mss import mss
except ImportError:
    logging.info("Cannot import mss")

try:
    import gi
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk
    from gi.overrides.GdkPixbuf import Pixbuf
except:
    logging.info("Cannot import gi")


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
        self.start_screen_reader()

    def run(self):
        """
            Run a loop which connects to the server and waits for watcher 
            clients.
            Stops if another client for this target is already connected
        """
        while self.running:
            try:
                self.socket.close()
                self.socket = self.new_socket()
                logging.info("Connecting")
                self.socket.connect(self.addr)
                logging.info("Connected")
                # After the connection is established send Hi
                self.send_data(b"Hi!")
                # Send unique code
                self.send_data(self.config.code.encode(self.FORMAT))
                data = b"WAIT"
                logging.info("Waiting")
                while data == b"WAIT":
                    data = self.recv_data()
                if data == ALREADY_CONNECTED.encode(self.FORMAT):
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
        if "controller" in dir(self):
            self.controller.stop()


class ScreenReader(Socket):
    # TODO:
    # 1. Send the image as a diff and not the whole data
    # 2. implement fallback from mss to gi (for linux) and from gi to PIL

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
        self.socket.connect(self.addr)
        self.send_data(TARGET_SCREEN_READER.encode(self.FORMAT))
        self.send_data(self.config.code.encode(self.FORMAT))
        data = self.recv_data()
        if data == b"OK":
            return True
        elif data == ALREADY_CONNECTED:
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
        self.socket.connect(self.addr)
        self.send_data(TARGET_CONTROLLER.encode(self.FORMAT))
        self.send_data(self.config.code.encode(self.FORMAT))
        data = self.recv_data()
        if data == b"OK":
            self.running = True
            return True
        elif data == ALREADY_CONNECTED:
            return False
        return False

    def control(self):
        """
            Receive control requests and put them in corresponding
            queues based on `control_type`
        """
        control_type = self.recv_data().decode(self.FORMAT)

        if control_type == CONTROL_MOUSE:
            click = self.recv_data().decode(self.FORMAT)
            # logging.debug(click)
            self.mouse.clicks.put(click)

            # TODO: remove acknowledgement as it slows down communication #done
            # self.send_data(b"OK")
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

    def __init__(self) -> None:
        # self.key_controller = KeyController()
        pass

    def update(self):
        pass


class Mouse(object):

    def __init__(self) -> None:
        self.mouse_controller = MouseController()
        self.clicks = Queue()
        self.screen_size = self.get_screen_size()
        logging.debug(self.screen_size)
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
        if self.clicks.empty():
            return
        self.screen_size = self.get_screen_size()
        click = eval(self.clicks.get())
        # logging.debug(str(click))
        ev_type = click[0]
        btn = click[1]
        rel_pos = click[2]
        pos = (
            rel_pos[0]*self.screen_size[0],
            (1-rel_pos[1])*self.screen_size[1]
        )
        self.mouse_controller.position = pos
        if ev_type == ControlEvents.MOUSE_DOWN:
            self.mouse_controller.press(self.btns[btn])
        elif ev_type == ControlEvents.MOUSE_UP:
            self.mouse_controller.release(self.btns[btn])

    def get_clicks(self):
        """
            Fetches requests from queue and returns them as a list
        """
        clicks = []
        while not self.clicks.empty():
            try:
                clicks.append(self.clicks.get_nowait())
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