#!/usr/bin/env python
import curses
import curses.ascii
import curses.textpad

import subprocess


class processing:
    def Run(self, command):
        proc = subprocess.Popen(command, bufsize=1,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            universal_newlines=True)
        return proc

    def Trace(self, proc):
        ret = []
        while proc.poll() is None:
            line = proc.stdout.readline()
            if line:
                ret.append(line)
        return ret


class main_win(object):
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.text = []
        self.draw()
        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_RED)
        self.iserror_attr = curses.color_pair(1)

    def __addstr(self, s):
        try:
            self.win.addstr(s.rstrip('\n') + '\n')
        except:
            self.win.scroll()
        self.win.refresh()

    def draw(self):
        maxy, maxx = self.stdscr.getmaxyx()
        self.win = self.stdscr.subwin(maxy - 1, maxx, 0, 0)
        self.win.scrollok(True)
        self.win.erase()
        for s in self.text:
            self.__addstr(s)

    def addstr(self, s):
        self.text.append(s)
        self.__addstr(s)


class status_bar(object):
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.stryx = lambda: "y: %d, x: %d" % self.win.getmaxyx()
        self.inpt_str = "$ "
        self.draw()

    def __addstr(self, s):
        try:
            self.win.addstr(s, curses.A_BLINK)
        except:
            self.win.scroll()
        self.win.refresh()

    def draw(self):
        maxy, maxx = self.stdscr.getmaxyx()
        self.win = self.stdscr.subwin(1, maxx, maxy - 1, 0)
        self.win.scrollok(True)

    def reprint(self):
        self.win.erase()
        s = self.inpt_str
        self.__addstr(s)

    def inpt(self, c):
        self.inpt_str = "$ %s" % c
        self.reprint()

    def clearinpt(self):
        self.inpt_str = "$ "
        self.reprint()


class UI(object):
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.main_win = main_win(stdscr)
        self.status_bar = status_bar(stdscr)
        self.proc = processing()

    def redraw(self):
        self.stdscr.clear()
        self.main_win.draw()
        self.status_bar.draw()

    def handle_input(self, c):
        self.main_win.addstr(">>> %s" % c)
        proc = self.proc.Run(c.split(' '))
        while proc.poll() is None:
            line = proc.stdout.readline()
            if line:
                self.main_win.addstr("%s" % str(line))

    def clearinpt(self):
        self.status_bar.clearinpt()

    def refresh(self):
        self.stdscr.refresh()
        self.status_bar.win.refresh()
        self.main_win.win.refresh()


def xx(stdscr):
    stdscr.scrollok(True)
    ui = UI(stdscr)
    inpt = []

    while True:
        c = stdscr.getch()
        if ord('\n') == c:
            in_str = "".join(inpt)
            ui.handle_input(in_str)
            ui.clearinpt()
            del inpt[:]
        elif curses.KEY_RESIZE == c:
            ui.redraw()
        elif curses.KEY_BACKSPACE == c:
            if len(inpt) > 0:
                del inpt[-1]
        else:
            if c < 256:
                inpt.append(chr(c))
        if len(inpt) > 0:
            ui.status_bar.inpt("".join(inpt))
        ui.refresh()


def main(stdscr):
    try:
        xx(stdscr)
    except KeyboardInterrupt:
        pass

curses.wrapper(main)