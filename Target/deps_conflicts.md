### Dependency conflicts
1. pyautogui
    - tkinter (while import)
        - gcc
        - make

2. pynput  (if this is resolved no need of pyautogui)
    - evdev package
        - libpython3-dev  (for Python.h header file)
    - tkinter (while import)

3. pip (resolved)
    - setuptools
        - distutils