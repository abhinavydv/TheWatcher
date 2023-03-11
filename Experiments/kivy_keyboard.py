from kivy.app import App
from kivy.uix.widget import Widget
from kivy.core.window import Window


class Test(Widget):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        Window.bind(on_key_down=self.on_key_down)

    def on_key_down(self, *args):
        print(args)


class TestApp(App):

    def build(self):
        return Test()


TestApp().run()
