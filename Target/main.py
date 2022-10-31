from Base.constants import ALREADY_CONNECTED, CONTROL_MOUSE, TARGET_SCREEN_READER, \
    TARGET_CONTROLLER, DISCONNECT
from Base.settings import IMG_FORMAT, SERVER_PORT, SERVER_ADDRESS
from Base.socket_base import Socket, Config
import logging
from PIL import Image
from pynput.keyboard import Controller as KeyController
from pynput.mouse import Controller as MouseController, Button as MouseButton
from queue import Queue, Empty
from socket import socket, AF_INET, SOCK_STREAM
import subprocess
from threading import Thread
from time import sleep
import traceback

try:
    import gi
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk
    from gi.overrides.GdkPixbuf import Pixbuf
except:
    pass


class Target(Socket):

    def __init__(self) -> None:
        super().__init__(SERVER_ADDRESS, SERVER_PORT)
        self.watched = False    # Set to True if screenshot is to be sent
        self.controlling = False

        self.config = Config()

        self.control_thread = None

    def start_screen_reader(self):
        self.screen_reader = ScreenReader()
        self.controlling = self.screen_reader.init()
        if not self.controlling:
            logging.info("Screen reader cannot connect to server. " + 
            "Either already connected or got disconnected after connection")

        while self.controlling:
            sleep(0.01)
            self.controlling = self.screen_reader.send_screenshot()
        self.screen_reader.stop()
        logging.info("Stoping screen reader client")

    def start_controller(self):
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
        self.control_thread = Thread(target=self.start_controller)
        self.control_thread.start()
        self.start_screen_reader()

    def run(self):
        # Run a loop which connects to the server and waits for clients
        while self.running:
            try:
                self.socket.close()
                self.socket = socket(AF_INET, SOCK_STREAM)
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
                if data == b"OK":
                    logging.info("Starting ScreenReader and Controller clients")
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
                logging.critical(f"OSError Occured\n{traceback.format_exc()}\n")
            except KeyboardInterrupt:
                self.stop()
                return
            sleep(1)

    def start(self):
        if not self.controlling:
            self.running = True
            self.run()

    def stop(self):
        self.running = False
        self.controlling = False
        if "controller" in dir(self):
            self.controller.stop()


class ScreenReader(Socket):

    def __init__(self) -> None:
        super().__init__(SERVER_ADDRESS, SERVER_PORT)
        self.config = Config()
        self.prev_img = None

    def init(self) -> bool:
        self.socket.connect(self.addr)
        self.send_data(TARGET_SCREEN_READER.encode(self.FORMAT))
        self.send_data(self.config.code.encode(self.FORMAT))
        data = self.recv_data()
        if data == b"OK":
            return True
        elif data == ALREADY_CONNECTED:
            return False
        return False

    def send_screenshot(self) -> bool:
        img = self.take_screenshot()
        # temp = img
        # if self.prev_img is not None:
            # img = Image.fromarray(np.array(img)-np.array(self.prev_img))
        # self.prev_img = temp

        try:
            self.send_data(self.image2bin(img))  # send the image
            ack = self.recv_data()   # Reveive "OK" (acknowledgement)
        except (ConnectionResetError, BrokenPipeError):
            return False

        if not ack:
            return False
        if ack.decode(self.FORMAT) == DISCONNECT:
            return False
        return True

    def stop(self) -> None:
        self.socket.close()

    def take_screenshot(self) -> Image:
        if 'linux' in self.platform:
            img = self.take_screenshot_linux()
        else:
            img = self.take_screenshot_other()

        return img
        # return self.take_screenshot_other()

    def take_screenshot_linux(self) -> Image:
        window = Gdk.get_default_root_window()
        x, y, width, height = window.get_geometry()
        pb: Pixbuf = Gdk.pixbuf_get_from_window(window, x, y, width, height)
        img = self.pixbuf2image(pb)
        img = img.resize((img.size[0]//2, img.size[1]//2), Image.ANTIALIAS)
        return img

    def take_screenshot_other(self) -> Image:
        from PIL import ImageGrab
        return ImageGrab.grab()

    def pixbuf2image(self, pix: Pixbuf) -> Image:
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
        import io
        bio = io.BytesIO()
        img.save(bio, format=IMG_FORMAT, optimize=True)
        return bio.getvalue()

    def pixbuf_to_bin(self, pb) -> bytes:
        return self.image2bin(self.pixbuf2image(pb))


class Controller(Socket):
    
    def __init__(self) -> None:
        super().__init__(SERVER_ADDRESS, SERVER_PORT)

        self.config = Config()
        self.mouse = Mouse()
        self.keyboard = Keyboard()

    def init(self) -> bool:
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
        control_type = self.recv_data().decode(self.FORMAT)

        if control_type == CONTROL_MOUSE:
            click = self.recv_data().decode(self.FORMAT)
            # logging.debug(click)
            self.mouse.clicks.put(click)
            self.send_data(b"OK")
        return True

    def run_update_loop(self):
        logging.info("Starting update loop")
        self.running = True
        while self.running:
            self.mouse.update()
            sleep(0.001)

    def stop(self):
        self.running = False


class Keyboard(object):

    def __init__(self) -> None:
        self.key_controller = KeyController()


class Mouse(object):

    def __init__(self) -> None:
        self.mouse_controller = MouseController()
        self.clicks = Queue()
        self.screen_size = self.get_screen_size()
        logging.debug(self.screen_size)

    def update(self):
        if self.clicks.empty():
            return
        click = eval(self.clicks.get())
        logging.debug(str(click))
        btn = click[0]
        pos = click[1]
        self.mouse_controller.position = pos[0]*self.screen_size[0], (1-pos[1])*self.screen_size[1]
        if btn == "left":
            self.mouse_controller.click(MouseButton.left)
            logging.debug("left click")
        elif btn == "left":
            self.mouse_controller.click(MouseButton.right)


    def get_clicks(self):
        clicks = []
        while not self.clicks.empty():
            try:
                clicks.append(self.clicks.get_nowait())
            except Empty:
                break
        return clicks

    def get_screen_size(self):
        cmd = ['xrandr']
        cmd2 = ['grep', '*']
        xrandr = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        grep = subprocess.Popen(cmd2, stdin=xrandr.stdout, stdout=subprocess.PIPE)
        res, junk = grep.communicate()
        resolution = res.split()[0].decode("utf-8")
        return [int(i) for i in resolution.split('x')]


if __name__ == "__main__":
    target = Target()
    try:
        target.start()
    except KeyboardInterrupt:
        target.stop()

    logging.info("Stopped Target.")