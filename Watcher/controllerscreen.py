from datetime import datetime
from io import BytesIO
import logging
import os
from queue import Queue
from random import randint
from threading import Thread
from time import sleep
from typing import Tuple
from watcher import Watcher

from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.core.window import Window
from kivy.input.providers.mouse import MouseMotionEvent
from kivy.lang import Builder
from kivy.properties import BooleanProperty, ObjectProperty
from kivy.uix.image import Image
from kivy.uix.scatterlayout import ScatterLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.label import MDLabel


Builder.load_file("controllerscreen.kv")


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
        self.mouse_controller = MouseController()
        self.mouse_controller.controller = self

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
        self.img_pos_lbl.text = str(self.img.to_window(*self.img.pos))
        if "img" in dir(self.watcher.screen_reader):
            img_io = BytesIO(self.watcher.screen_reader.img)
            self.ci = CoreImage(img_io, ext="jpg")
            self.img.texture = self.ci.texture

    def start(self):
        logging.info(f"Watching {self.code}")
        self.watcher.watch(self.code)
        self.running = True
        self.run_schedule = Clock.schedule_interval(self.run, 0.05)
        self.mouse_controller.start()
        Thread(target=self.run_update_loop).start()

    def run_update_loop(self):
        while self.running:
            self.mouse_controller.update()
            sleep(0.01)

    def on_touch_down(self, touch: MouseMotionEvent):
        # logging.debug(str(self.img.norm_image_size))
        # logging.debug(str(self.img.center_x - self.img.norm_image_size[0]/2))
        # logging.debug(str(self.img.center_y - self.img.norm_image_size[1]/2))
        img_pos = [(self.img.center_x - self.img.norm_image_size[0]/2), (self.img.center_y - self.img.norm_image_size[1]/2)]
        click_pos = [(touch.pos[0]-img_pos[0])/self.img.norm_image_size[0], (touch.pos[1]-img_pos[1])/self.img.norm_image_size[1]]
        logging.debug(str(click_pos))
        if touch.button == "left":
            self.mouse_controller.clicks.put(("left", click_pos))
        elif touch.button == "right":
            self.mouse_controller.clicks.put(("right", click_pos))

    def stop(self):
        self.running = False
        self.run_schedule.cancel()
        if self.watcher.watching:
            self.watcher.stop_watching()
        self.mouse_controller.stop()
        # logging.info(f"Watching stopped")

    def close(self):
        self.manager.remove_widget(self)

    def on_enter(self, *args):
        self.start()
        return super().on_enter(*args)

    def on_leave(self, *args):
        self.stop()
        # logging.info("Leaving ControllerScreen")
        return super().on_leave(*args)


class MouseController(object):

    def __init__(self) -> None:
        self.clicks = Queue(0)
        self.pos: Tuple[int, int] = (0, 0)
        self.controller: ControllerScreen = None

    def start(self):
        self.mouse_pos_lbl = self.controller.mouse_pos_lbl
        Window.bind(mouse_pos=self.update_mouse_pos)

    def update_mouse_pos(self, _, pos):
        self.pos = pos
        self.mouse_pos_lbl.text = str(pos)

    def get_clicks(self):
        l = []
        while not self.clicks.empty():
            l.append(self.clicks.get_nowait())
        return l

    def update(self):
        pass

    def stop(self):
        Window.unbind(mouse_pos=self.update_mouse_pos)
