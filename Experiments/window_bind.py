from kivy.app import App
from kivy.uix.widget import Widget
from kivy.core.window import Window
from kivy.core.window.window_sdl2 import WindowSDL


Window: WindowSDL


class Test(Widget):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        Window.bind(focus=lambda *args: self.on_focus("focus", args))
        Window.bind(on_drop_begin=lambda *args: self.on_focus("begin", args))
        Window.bind(on_drop_end=lambda *args: self.on_focus("end", args))
        Window.bind(on_drop_file=lambda *args: self.on_focus("file", args))
        Window.bind(on_drop_text=lambda *args: self.on_focus("text", args))
        # Window.bind(on_dropfile=lambda *args: self.on_focus("_file", args))

    def on_focus(self, action, args):
        print(action, args)


class TestApp(App):

    def build(self):
        return Test()


TestApp().run()
