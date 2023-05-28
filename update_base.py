#!/usr/bin/python

import os
import shutil


path = os.path.abspath(".")
folders = [os.path.join(path, i) for i in ["Watcher/Base", "Server/Base", "Target/Base"]]
for folder in folders:
    if os.path.exists(folder):
        shutil.rmtree(folder)
    shutil.copytree(os.path.join(path, "Base"), folder)
