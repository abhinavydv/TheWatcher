from kivy.config import Config
# disable red dot that appeared on right click
Config.set('input', 'mouse', 'mouse,multitouch_on_demand')  

from kivymd.app import MDApp
from kivy.uix.screenmanager import ScreenManager
from homescreen import HomeScreen


class TheWatcherApp(MDApp):

    def build(self):
        self.manager = ScreenManager()
        self.homescreen = HomeScreen()
        self.manager.add_widget(self.homescreen)
        self.manager.current = "HomeScreen"
        return self.manager

    def on_stop(self):
        self.manager.current_screen.stop()
        self.homescreen.stop()


if __name__ == "__main__":
    app = TheWatcherApp()
    app.run()