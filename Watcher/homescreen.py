from kivy.lang import Builder
from kivy.properties import BooleanProperty, ObjectProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRectangleFlatButton
from kivymd.uix.widget import MDWidget

from watcher import Watcher
from controllerscreen import ControllerScreen
import logging
from threading import Thread
from time import sleep

Builder.load_file("homescreen.kv")


class TargetListItem(MDBoxLayout):
    text = StringProperty("")
    homescreen = ObjectProperty(None)
    code = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.homescreen: HomeScreen

    def start_watching(self):
        target_list_view: TargetListView = self.parent.parent
        cs = ControllerScreen(self.code, target_list_view.watcher)
        self.homescreen.manager.add_widget(cs)
        self.homescreen.manager.current = cs.name


class TargetListView(RecycleView):
    homescreen = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.root_layout = BoxLayout(orientation='vertical')
        self.watcher: Watcher = None
        self.target_list = []

    def update(self):
        self.data = [{"text": i, "code": i, "homescreen": self.homescreen} for i in self.watcher.target_list]
        if not self.data:
            self.homescreen.connection_lbl.text = "No target connected"
        else:
            self.homescreen.connection_lbl.text = ""
        # logging.debug(str(self.data))
        # logging.debug(str(self.data))
        # print(self.data)


class HomeScreen(Screen):
    running = BooleanProperty(False)
    target_list_view: TargetListView = ObjectProperty(None)
    connection_lbl = ObjectProperty(None)

    def __init__(self, **kw):
        super().__init__(**kw)
        self.watcher = Watcher()
        self.updating = False

    def start(self):
        self.target_list_view.homescreen = self
        self.target_list_view.watcher = self.watcher
        Thread(target=self.start_watcher).start()
        Thread(target=self.run_update_loop).start()
        self.running = True

    def start_watcher(self):
        if not self.watcher.start():
            self.connection_lbl.text = "Cannot connect to server"
        else:
            self.connection_lbl.text = ""


    def stop(self):
        self.watcher.stop()
        self.running = False
        self.updating = False
        self.target_list_view.data = []

    def update(self):
        self.target_list_view.update()
        self.running = self.watcher.running

    def run_update_loop(self):
        if self.updating:
            logging.info("Already updating data")
            return
        self.updating = True
        while self.updating:
            if self.running and "watcher" in dir(self):
                self.update()
            sleep(0.1)

    def on_leave(self, *args):
        self.updating = False
        return super().on_leave(*args)

    def on_enter(self, *args):
        Thread(target=self.run_update_loop).start()
        return super().on_enter(*args)
        
