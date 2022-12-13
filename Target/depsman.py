#!/bin/python
"""
    `Dependency manager`
    This script will check for all dependencies and install the missing ones.
    Run by boot.py

    TODO: If internet connection isn't available all the functions will fail
        create an error handler and return False in Setup().install() if
        something could not be installed.
"""

import os
from Base.settings import WEB_SERVER_ADDRESS, WEB_SERVER_PORT
from zipfile import ZipFile
import sys


class Setup():
    def __init__(self):
        self.CACHE_DIR = "watcher"
        self.CURR_DIR = os.path.abspath(".")  # save current directory
        self.python_version_number = (f"{sys.version_info.major}."
            f"{sys.version_info.minor}")
        self.VIRTUALENV = (f"{os.path.dirname(self.CURR_DIR)}"
            f"/.watchenv{self.python_version_number}")
        self.ENV_ACTIVATE_FILE = f"{self.VIRTUALENV}/bin/activate_this.py"

        # create a cache directory and enter it
        os.chdir(f"/home/{os.getlogin()}")
        if not os.path.exists(".cache"):
            os.mkdir(".cache")
        os.chdir(".cache")
        if not os.path.exists(self.CACHE_DIR):
            os.mkdir(self.CACHE_DIR)
        os.chdir(self.CACHE_DIR)
        print(os.path.abspath("."))

        # add path to pip bin directory
        os.environ["PATH"] += f":/home/{os.getlogin()}/.local/bin"

        # save current PYTHONPATH
        try:
            self.py_path = os.environ["PYTHONPATH"]
        except KeyError:
            self.py_path = ""

    def install(self):
        self.check_pip()
        self.enable_virtualenv()
        self.check_target_deps()
        self.clean()

    #1. distutils
    def check_distutils(self):
        try:
            import distutils.cmd as _
            import distutils.core as _
            if os.system("pip") != 0:
                raise ImportError("Distutils not installed properly")
        except ImportError:   # distutils.cmd and core not present
            status = os.system(f"wget --no-check-certificate http://"
                f"{WEB_SERVER_ADDRESS}:{WEB_SERVER_PORT}/distutils.zip")
            if status == 0:
                z = ZipFile("distutils.zip", "r")
                z.extractall()
                os.environ["PYTHONPATH"] = f'{self.py_path}:{os.path.abspath("distutils")}'
            else:
                print("Unable to get distutils!")
                return False
        return True

    # 2. pip
    def check_pip(self):
        self.check_distutils()
        try:
            import pip as _
        except ImportError: # pip not installed
            status = os.system(f"wget --no-check-certificate http://"
                f"{WEB_SERVER_ADDRESS}:{WEB_SERVER_PORT}/get-pip.py")
            if status == 0:
                os.system("python3 get-pip.py --user")
                print("installed pip")
                # os.system("pip install distutils")
            else:
                print("Couldn't download get-pip.py")
                return False
        return True

    # 3. virtual environment
    def enable_virtualenv(self):
        # remember: value of LD_LIBRARY_PATH is set in main_wrapper.sh
        # so change it too if changing `self.VIRTUALENV`
        if not os.path.exists(self.ENV_ACTIVATE_FILE):
            # install virtualenv
            os.system("python3 -m pip install virtualenv")
            os.system(f"python3 -m virtualenv {self.VIRTUALENV}")

        # enable virtualenv
        exec(open(self.ENV_ACTIVATE_FILE).read(), 
            {'__file__': self.ENV_ACTIVATE_FILE})

    # 4. target dependencies
    def check_target_deps(self):
        # install mss, numpy and pillow
        print("Installing mss, numpy and pillow")
        os.system("python3 -m pip install mss numpy pillow")
        print("Installed mss, numpy and pillow")

        # install pynput if not installed
        version = f"python{sys.version_info.major}.{sys.version_info.minor}"
        INSTALL_DIR=os.path.abspath(".")
        print("Checking pynput")
        try:
            # this will raise ImportError if tkinter not installed
            import pynput as _
        except ImportError:
            print("installing pynput")
            if not os.path.exists(f"/usr/include/{version}/Python.h"):
                print(f"downloading lib{version}-dev")
                os.system(f"apt download lib{version}-dev")
                print(f"downloaded lib{version}-dev")
                print(f"extracting lib{version}-dev")
                os.system(f"dpkg -x lib{version}-dev* .")
                print(f"extracted lib{version}-dev")
                os.environ["CPATH"] = f"{INSTALL_DIR}/usr/include:{INSTALL_DIR}/usr/include/{version}"
            os.system("python3 -m pip install pynput")
            print("installed pynput")

        # install tkinter (required by pynput)
        try:
            # Problem: if this fails then even after installing
            #         tkinter, import will fail for this python
            #         instance do something for it to work ( may be caused
            #         by module caching)
            import tkinter as _
        except ImportError:   # install tkinter here
            print("Installing tkinter")
            if not os.path.exists("tk"):
                os.mkdir("tk")
            os.chdir("tk")
            if os.listdir():
                os.system("rm -r ./*")
            os.system("apt download blt libtcl8.6 libtk8.6 tk8.6-blt2.5 python3-tk")
            for i in os.listdir("."):
                os.system(f"dpkg -x {i} .")
            os.system(f"cp -r usr/lib {self.VIRTUALENV}")
            os.system(f"cp -r usr/share {self.VIRTUALENV}")
            print("Installed tkinter")
            os.chdir("..")


    # clean up and reset
    def clean(self):
        if "PYTHONPATH" in os.environ:
            if self.py_path is None:
                del os.environ["PYTHONPATH"]
            else:
                os.environ["PYTHONPATH"] = self.py_path

        os.chdir("..")
        os.system(f"rm -r {self.CACHE_DIR}")
        os.chdir(self.CURR_DIR)


if __name__ == "__main__":
    Setup().install()
