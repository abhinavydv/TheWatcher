from Base.socket_base import Socket
from Base.settings import SERVER_ADDRESS, SERVER_PORT
from datetime import datetime
from io import BytesIO
import logging
import os
from queue import Queue
from random import randint
from socket import socket
from threading import Lock, Thread
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
            try:
                self.ci = CoreImage(img_io, ext="jpg")
            except Exception:
                self.stop()
            self.img.texture = self.ci.texture

    def start(self):
        logging.info(f"Watching {self.code}")
        self.watcher.watch(self.code)
        self.mouse_controller = self.watcher.controller.mouse_controller
        self.running = True
        self.run_schedule = Clock.schedule_interval(self.run, 0.05)
        Window.bind(mouse_pos=self.mouse_controller.update_mouse_pos)

    def on_touch_down(self, touch: MouseMotionEvent):
        if not self.running:
            return
        img_pos = [(self.img.center_x - self.img.norm_image_size[0]/2), (self.img.center_y - self.img.norm_image_size[1]/2)]
        click_pos = [(touch.pos[0]-img_pos[0])/self.img.norm_image_size[0], (touch.pos[1]-img_pos[1])/self.img.norm_image_size[1]]
        if not (0 <= click_pos[0] <= 1 and 0 <= click_pos[1] <= 1):
            return
        if touch.button == "left":
            self.mouse_controller.clicks.put(("left", click_pos))
        elif touch.button == "right":
            self.mouse_controller.clicks.put(("right", click_pos))

    def stop(self):
        self.running = False
        self.run_schedule.cancel()
        if self.watcher.watching:
            self.watcher.stop_watching()
        Window.unbind(mouse_pos=self.mouse_controller.update_mouse_pos)
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
