from datetime import datetime
from io import BytesIO
import logging
import os
from random import randint
from watcher import Watcher

from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.lang import Builder
from kivy.properties import BooleanProperty, ObjectProperty
from kivy.uix.image import Image
from kivy.uix.screenmanager import Screen


Builder.load_file("controllerscreen.kv")


class ControllerScreen(Screen):
    paused = BooleanProperty(False)
    img: Image = ObjectProperty(None)

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
        if "img" in dir(self.watcher.screen_reader):
            img_io = BytesIO(self.watcher.screen_reader.img)
            self.ci = CoreImage(img_io, ext="jpg")
            self.img.texture = self.ci.texture

    def start(self):
        logging.info(f"Watching {self.code}")
        self.watcher.watch(self.code)
        self.running = True
        self.run_schedule = Clock.schedule_interval(self.run, 0.05)

    def stop(self):
        self.running = False
        self.run_schedule.cancel()
        self.watcher.stop_watching()
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
