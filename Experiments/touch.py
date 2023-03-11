from kivy.config import Config
Config.set('input', 'mouse', 'mouse,multitouch_on_demand')  

from kivy.app import App
from kivy.uix.widget import Widget
from kivy.input.motionevent import MotionEvent
from kivy.input.providers.mtdev import MTDMotionEvent
from kivy.input.providers.mouse import MouseMotionEvent
from kivy.core.window import Window


class TouchTest(Widget):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Window.bind(mouse_pos=lambda *args: print(args))

    def on_touch_down(self, touch: MouseMotionEvent):
        print(type(touch), "DOWN", touch.button, touch.is_double_tap, touch.is_triple_tap)

    def on_touch_up(self, touch: MouseMotionEvent):
        print(type(touch), "UP", touch.button, touch.is_double_tap, touch.is_triple_tap)

    def on_motion(self, etype: str, me: MotionEvent):
        print(etype, me.pos, me.button)

    # def on_touch_move(self, touch: MTDMotionEvent):
    #     print(touch)


class TouchApp(App):

    def build(self):
        return TouchTest()


if __name__ == "__main__":
    TouchApp().run()