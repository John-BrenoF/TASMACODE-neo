import curses
import os

class VersionViewer:
    def __init__(self, ui, path):
        self.ui = ui
        self.path = path

    def run(self):
        self.ui.stdscr.refresh()
        max_y, max_x = self.ui.stdscr.getmaxyx()
        h = 20
        w = 60
        if max_y < h: h = max_y
        if max_x < w: w = max_x
        y = (max_y - h) // 2
        x = (max_x - w) // 2
        win = curses.newwin(h, w, y, x)
        win.keypad(True)
        try:
            win.bkgd(' ', curses.color_pair(5))
        except:
            pass
        win.box()
        win.addstr(0, 2, " Version (Ctrl+G) ")
        lines = []
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    lines = f.read().splitlines()
            except:
                lines = ["Erro ao ler arquivo"]
        else:
            lines = ["Arquivo nao encontrado"]
        for i, line in enumerate(lines):
            if i >= h - 2:
                break
            try:
                win.addstr(i + 1, 2, line[:w - 4])
            except:
                pass
        win.refresh()
        curses.flushinp()
        win.nodelay(False)
        win.getch()

def register(context):
    ui = context.get("ui")
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "../../docs/vession.txt")
    viewer = VersionViewer(ui, path)
    context["global_commands"][7] = viewer.run
