from kivy.app import App
from kivy.lang import Builder
from kivy.properties import StringProperty
from kivy.uix.recycleview import RecycleView
from kivy.uix.widget import Widget
from kivy.uix.label import Label


Builder.load_string('''
<RV>:
    viewclass: 'MyClass'
    RecycleBoxLayout:
        default_size: None, dp(56)
        default_size_hint: 1, None
        size_hint_y: None
        height: self.minimum_height
        orientation: 'vertical'

<MyClass>:
    Label:
        text: root.text
''')


class MyClass(Label):
    text = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class RV(RecycleView):
    def __init__(self, **kwargs):
        super(RV, self).__init__(**kwargs)
        self.data = [{'text': str(x)} for x in range(100)]


class TestApp(App):
    def build(self):
        return RV()

if __name__ == '__main__':
    TestApp().run()