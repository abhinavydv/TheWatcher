from Base.constants import DeviceEvents
from datetime import datetime
from io import BytesIO
import logging
import os
from random import randint
import traceback
from watcher import Watcher

# kivy imoprts
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.core.window import Window
from kivy.core.window.window_sdl2 import WindowSDL
from kivy.input.providers.mouse import MouseMotionEvent
from kivy.lang import Builder
from kivy.properties import BooleanProperty, ObjectProperty
from kivy.uix.image import Image
from kivy.uix.scatterlayout import ScatterLayout
from kivy.uix.screenmanager import Screen

# kivymd imports
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.label import MDLabel
from kivymd.toast import toast


Builder.load_file("controllerscreen.kv")
Window: WindowSDL


class ControllerScreen(Screen):
    paused: bool = BooleanProperty(False)
    img: Image = ObjectProperty(None)
    status_bar: MDBoxLayout = ObjectProperty(None)
    img_pos_lbl: MDLabel = ObjectProperty(None)
    img_scatter: ScatterLayout = ObjectProperty(None)
    float_layout: MDFloatLayout = ObjectProperty(None)
    mouse_pos_lbl: MDLabel = ObjectProperty(None)

    def __init__(self, code: str, watcher: Watcher, **kw):
        super().__init__(**kw)
        self.code = code
        self.watcher = watcher
        self.running = False

    def resume(self):
        self.run_schedule = Clock.schedule_interval(self.run, 0.05)
        self.paused = False

    def pause(self):
        self.run_schedule.cancel()
        self.paused = True

    def save_img(self):
        if not os.path.exists("./images"):
            os.mkdir("./images")
        file = datetime.datetime.isoformat(datetime.datetime.now())
        if "ci" in dir(self):
            self.ci.save(f"images/img_{file}_{randint(0, 100000)}.jpg")

    def run(self, _):
        """
            Update the target screen image
        """
        # self.img_pos_lbl.text = str(self.img.to_window(*self.img.pos))
        if "img" in dir(self.watcher.screen_reader):
            img_io = BytesIO(self.watcher.screen_reader.img)
            try:
                self.ci = CoreImage(img_io, ext="jpg")
            except Exception:
                logging.error(traceback.format_exc())
                toast("Image not received completely. Watching stopped")
                self.close()
            self.img.texture = self.ci.texture

    def start(self):
        """
            Start watching and controlling the target
        """
        logging.info(f"Watching {self.code}")
        self.watcher.watch(self.code)
        self.mouse_controller = self.watcher.controller.mouse_controller
        self.running = True
        self.run_schedule = Clock.schedule_interval(self.run, 0.05)
        Window.bind(mouse_pos=self.on_pointer_move)
        Window.bind(focus=self.on_focus_change)

    def on_focus_change(self, _, value):
        self.watcher.controller.keyboard_controller.window_in_focus = value

    def on_touch_down(self, touch: MouseMotionEvent):
        """
            As of now only left and right mouse clicks are supported
            (No hold and drag or any other motion or button click)
            TODO: simulate mouse button down in on_touch_down
                  and mouse button up in on_touch_up. In on_touch_move
                  only move target's mouse pointer.
        """
        if not self.running:
            return
        if touch.button is not None:
            self.mouse_controller.button_down = True
            self.put_touch_event(touch, DeviceEvents.MOUSE_DOWN)

    def on_touch_up(self, touch: MouseMotionEvent):
        if not self.running:
            return
        if touch.button is not None:
            self.mouse_controller.button_down = False
            self.put_touch_event(touch, DeviceEvents.MOUSE_UP)

    def on_pointer_move(self, _, pos):
        mouse_pos = self.get_click_pos(pos)
        if not (0 <= mouse_pos[0] <= 1 and 0 <= mouse_pos[1] <= 1):
            return
        if self.mouse_controller.button_down:
            self.mouse_controller.events.put((DeviceEvents.MOUSE_MOVE,
                                             None, mouse_pos))

    def put_touch_event(self, touch: MouseMotionEvent, type):
        click_pos = self.get_click_pos(touch.pos)
        if not (0 <= click_pos[0] <= 1 and 0 <= click_pos[1] <= 1):
            return

        self.mouse_controller.events.put((type, touch.button, click_pos))

    def get_click_pos(self, pos):
        img_pos = [(self.img.center_x - self.img.norm_image_size[0]/2),
                   (self.img.center_y - self.img.norm_image_size[1]/2)]

        # get relative click position (0, 0) is bottom left and
        # (1, 1) is top right of target screen
        click_pos = [(pos[0]-img_pos[0])/self.img.norm_image_size[0],
                     (pos[1]-img_pos[1])/self.img.norm_image_size[1]]
        return click_pos

    def stop(self):
        # stop watching the target
        self.running = False
        self.run_schedule.cancel()
        if self.watcher.watching:
            self.watcher.stop_watching()
        Window.unbind(mouse_pos=self.mouse_controller.update_mouse_pos)
        Window.unbind(focus=self.on_focus_change)

    def close(self):
        if self.manager is not None:
            self.manager.remove_widget(self)

    def on_enter(self, *args):
        self.start()
        return super().on_enter(*args)

    def on_leave(self, *args):
        self.stop()
        # logging.info("Leaving ControllerScreen")
        return super().on_leave(*args)
