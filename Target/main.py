from time import sleep
from Base.socket_base import Socket, Config
from socket import socket, AF_INET, SOCK_STREAM
from PIL import Image
from threading import Thread
from pynput.keyboard import Controller
from Base.settings import ALREADY_CONNECTED, IMG_FORMAT, SERVER_PORT, SERVER_ADDRESS, \
    TARGET_SCREEN_READER, TARGET_CONTROLLER, DISCONNECT
import logging
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
        self.key_controller = Controller()

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
        while self.controlling:
            sleep(1)
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
        img = img.resize((img.size[0]//3, img.size[1]//3), Image.ANTIALIAS)
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
    pass


if __name__ == "__main__":
    target = Target()
    try:
        target.start()
    except KeyboardInterrupt:
        target.stop()

    logging.info("Stopped Target.")