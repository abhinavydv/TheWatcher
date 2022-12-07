#!/bin/python
"""
    This script will check for all dependencies and install the missing ones.
"""

import os
from Base.settings import WEB_SERVER_ADDRESS, WEB_SERVER_PORT
from tarfile import open as tarOpen
from zipfile import ZipFile


class Setup():
    def __init__(self):
        self.CACHE_DIR = "watcher"
        self.CURR_DIR = os.path.abspath(".")  # save current directory
    
        # create a cache directory and enter it
        os.chdir(f"/home/{os.getlogin()}")
        if not os.path.exists(".cache"):
            os.mkdir(".cache")
        os.chdir(".cache")
        if not os.path.exists(self.CACHE_DIR):
            os.mkdir(self.CACHE_DIR)
        os.chdir(self.CACHE_DIR)

        # add path to pip bin directory
        os.environ["PATH"] += f":/home/{os.getlogin()}/.local/bin"

        # save current PYTHONPATH
        try:
            self.py_path = os.environ["PYTHONPATH"]
        except KeyError:
            self.py_path = None

    def install(self):
        self.check_pip()
        self.check_target_deps()
        self.clean()

    # check for dependencies

    #1. distutils
    def check_distutils(self):
        try:
            import distutils.cmd as _
            import distutils.core as _
        except ImportError:   # distutils not present
            os.environ["PYTHONPATH"] = os.path.abspath("distutils")
            status = os.system(f"wget --no-check-certificate http://{WEB_SERVER_ADDRESS}:{WEB_SERVER_PORT}/distutils.zip")
            if status == 0:
                z = ZipFile("distutils.zip", "r")
                z.extractall()
            else:
                print("Unable to get distutils!")

    # 2. pip
    def check_pip(self):
        self.check_distutils()
        try:
            import pip as _
        except ImportError: # pip not installed
            status = os.system(f"wget --no-check-certificate http://{WEB_SERVER_ADDRESS}:{WEB_SERVER_PORT}/get-pip.py")
            if status == 0:
                os.system("python3 get-pip.py --user")
                print("installed pip")
                # os.system("pip install distutils")
            else:
                print("Couldn't download get-pip.py")

    # 3. target dependencies
    def check_target_deps(self):
        self.check_distutils()
        os.system(f"python3 -m pip install -r {self.CURR_DIR}/requirements.txt")

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
