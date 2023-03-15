import os
import shutil


path = os.path.abspath(".")
shutil.copy(os.path.join(path, "../Target/main.py"), os.path.join("main.py"))

if os.path.exists(os.path.join(path, "Base")):
    shutil.rmtree(os.path.join(path, "Base"))
shutil.copytree(os.path.join(path, "../Base"), os.path.join(path, "Base"))
