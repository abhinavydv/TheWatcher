from pynput.keyboard import Listener

with Listener(on_press=print) as l:
    print(l._KEYPAD_KEYS)
    l.join()
