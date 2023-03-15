"""
    This script will be run on every system start.
"""


import os
from time import sleep
import subprocess
from threading import Thread


PATH=os.path.abspath(".")
FILE_PATH=os.path.abspath(__file__)
DIR_PATH=os.path.dirname(FILE_PATH)

"""
    TODO: 1. On many linux systems crontab is not available by default.
        On desktop environments, create a .desktop file in ~/.config/autostart.
        2. Find out a way to run at startup on arch and other non desktop envs.
"""


class Autostart(object):
    def __init__(self):
        pass

    def check_and_configure(self):
        cron = Thread(target=self.check_crontab)
        desk = Thread(target=self.check_config_autostart)
        cron.start()
        desk.start()

        cron.join()
        desk.join()

    def check_crontab(self):
        # check every minute if this script and  there in cron
        this_job = f"@reboot python3 \"{DIR_PATH}/boot.py\"".encode("utf-8")
        try:
            subprocess.run(["crontab", '-l'], capture_output=True)
        except NotADirectoryError:
            return False
        while True:
            jobs = subprocess.run(["crontab", '-l'], capture_output=True)
            present = False
            joblist = jobs.stdout.split(b"\n")
            for job in joblist:
                if job.strip() == this_job:
                    present = True
                    break

            if not present:
                joblist.append(this_job+b"\n")
                subprocess.run(["crontab"], input=b"\n".join(joblist))
            # echo '@reboot '
            sleep(1)

    def check_config_autostart(self):
        """
            creates a desktop file in the ~/.config/autostart 
            folder in desktop environments
        """
        pass


if __name__ == "__main__":
    path = os.path.dirname(__file__) or "."
    os.chdir(path)
    os.system(f"setsid bash main_wrapper.sh >/dev/null 2>&1 < /dev/null &")

    Autostart().check_and_configure()
