from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import BooleanProperty, ObjectProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.screenmanager import Screen
from kivymd.uix.boxlayout import MDBoxLayout

from watcher import Watcher
from controllerscreen import ControllerScreen
import logging
from threading import Thread
from time import sleep

Builder.load_file("homescreen.kv")


class TargetListItem(MDBoxLayout):
    """
        Shows info about one item in target list
    """
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
    """
        Widget that displays a list of targets
    """
    homescreen = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.root_layout = BoxLayout(orientation='vertical')
        self.watcher: Watcher = None
        self.target_list = []

    def update(self):
        self.data = [{"text": i, "code": i, "homescreen": self.homescreen}
            for i in self.watcher.target_list]
        if not self.data:
            self.homescreen.connection_lbl.text = "No target connected"
        else:
            self.homescreen.connection_lbl.text = ""


class HomeScreen(Screen):
    running = BooleanProperty(False)
    target_list_view: TargetListView = ObjectProperty(None)
    connection_lbl = ObjectProperty(None)

    def __init__(self, **kw):
        super().__init__(**kw)
        self.watcher = Watcher()
        self.updating = False

    def start(self):
        # start the watcher
        self.target_list_view.homescreen = self

        # give reference of watcher to the target list view
        self.target_list_view.watcher = self.watcher
        self.running = True
        Thread(target=self.start_watcher).start()
        Thread(target=self.run_update_loop).start()

    def start_watcher(self):
        if not self.watcher.start():
            self.connection_lbl.text = "Cannot connect to server"
        else:
            self.connection_lbl.text = ""

    def stop(self):
        # stop the watcher
        self.watcher.stop()
        self.running = False
        self.updating = False
        self.target_list_view.data = []

    def update(self):
        self.target_list_view.update()      # keep updating list of targets
        self.running = self.watcher.running
        self.updating = self.running

    def run_update_loop(self):
        if self.updating:
            logging.info("Already updating data")
            return
        self.updating = True
        while self.updating:
            if self.running:
                self.update()
            sleep(0.1)

    def on_leave(self, *args):
        self.updating = False
        return super().on_leave(*args)

    def on_enter(self, *args):
        Thread(target=self.run_update_loop).start()
        # Clock.schedule_once(lambda dt: Thread(target=self.run_update_loop)
        #     .start(), 0)
        return super().on_enter(*args)

