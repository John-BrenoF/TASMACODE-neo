# /home/johnb/tasma-code-absulut/src/config.py
import json
import os
import curses

class Config:
    def __init__(self, filepath="config.json"):
        self.user_config_path = filepath
        # Define o diretório de temas relativo à raiz do projeto
        base_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(base_dir)
        self.theme_dir = os.path.join(project_root, "themes")
        if not os.path.exists(self.theme_dir):
            os.makedirs(self.theme_dir)
        self.settings = {
            "confirm_navigation": True,
            "relative_line_numbers": False
        }
        self.colors = {
            "keyword": "YELLOW",
            "string": "GREEN",
            "comment": "CYAN",
            "active_tab_fg": "WHITE",
            "active_tab_bg": "BLUE",
            "inactive_tab_fg": "BLACK",
            "inactive_tab_bg": "WHITE",
            "number": "MAGENTA",
            "class": "RED",
            "sidebar_fg": "BLACK",
            "sidebar_bg": "WHITE",
            "statusbar_fg": "WHITE",
            "statusbar_bg": "BLUE"
        }
        self.keys = {
            "save": 19,
            "quit": 17,
            "find": 6,
            "find_next": 231, # Alt+g (swapped with open_git_window)
            "replace": 242, # Alt+r (was replace_regex)
            "copy": 3,
            "paste": 22,
            "cut": 24,
            "undo": 26,
            "redo": 25,
            "open": 15,
            "goto_line": 12,
            "close_tab": 23,
            "toggle_sidebar": 2,
            "autocomplete": 0,
            "duplicate_line": 4,
            "delete_line": 11,
            "select_all": 1,
            "toggle_comment": 31,
            "help": curses.KEY_F1,
            "macro_rec": curses.KEY_F8,
            "macro_play": curses.KEY_F9,
            "definition": curses.KEY_F12,
            "rename": curses.KEY_F2,
            "refresh": ord('r'),
            "new_file": ord('n'),
            "new_dir": ord('N'),
            "toggle_hidden": ord('h'),
            "delete_file": curses.KEY_DC,
            "delete_forward": curses.KEY_DC,
            "toggle_bookmark": curses.KEY_F3,
            "next_bookmark": curses.KEY_F4,
            "prev_bookmark": curses.KEY_F5,
            "jump_bracket": 29, # Ctrl+],
            "prev_tab": 545, # Ctrl+Left
            "next_tab": 560, # Ctrl+Right
            "move_word_left": curses.KEY_PPAGE,
            "move_word_right": curses.KEY_NPAGE,
            "toggle_split": 240, # Alt+P
            "switch_focus": curses.KEY_F11,
            "toggle_fold": curses.KEY_F10,
            "export_html": curses.KEY_F7,
            "open_config": 234, # Alt+j (106 + 128)
            "goto_symbol": 20, # Ctrl+T
            "find_regex": 230, # Alt+f (102 + 128)
            "replace_regex": 243, # Alt+s (115 + 128) - Moved to make room for replace
            "toggle_right_sidebar": 8, # Ctrl+H
            "open_settings": curses.KEY_F6,
            "open_git_window": 7, # Ctrl+G
            "open_folder": 239, # Alt+o
            "set_root": 80, # Shift+P
            "fuzzy_find_file": 16, # Ctrl+P
            "toggle_structure": 18, # Ctrl+R
            "import_theme": 5 # Ctrl+E
        }
        self.snippets = {
            "def": "def name(args):\n    pass",
            "class": "class Name:\n    def __init__(self):\n        pass",
            "if": "if condition:\n    pass",
            "for": "for item in iterable:\n    pass",
            "while": "while condition:\n    pass",
            "print": "print()",
            "main": "if __name__ == \"__main__\":\n    main()"
        }
        self.load()

    def load(self):
        if os.path.exists(self.user_config_path):
            try:
                with open(self.user_config_path, 'r') as f:
                    data = json.load(f)
                    
                    # Carrega tema se especificado
                    if "theme" in data:
                        theme_path = os.path.join(self.theme_dir, f"{data['theme']}.json")
                        if os.path.exists(theme_path):
                            with open(theme_path, 'r') as tf:
                                theme_data = json.load(tf)
                                if "colors" in theme_data:
                                    self.colors.update(theme_data["colors"])

                    if "colors" in data:
                        self.colors.update(data["colors"])
                    if "settings" in data:
                        self.settings.update(data["settings"])
                    if "keys" in data:
                        self.keys.update(data["keys"])
                    if "snippets" in data:
                        self.snippets.update(data["snippets"])
            except Exception:
                pass

    def save_to_user_config(self):
        """Saves the current keys and colors to the user config file."""
        data_to_save = {
            "colors": self.colors,
            "keys": self.keys,
            "snippets": self.snippets,
            "settings": self.settings
        }
        try:
            with open(self.user_config_path, 'w') as f:
                json.dump(data_to_save, f, indent=4, sort_keys=True)
        except Exception:
            pass # Falha silenciosa por enquanto

    def get_color_code(self, color_name):
        if isinstance(color_name, int):
            return color_name
        return getattr(curses, f"COLOR_{color_name.upper()}", curses.COLOR_WHITE)

    def get_key(self, name):
        return self.keys.get(name, -1)

    def get_available_themes(self):
        """Retorna lista de temas disponíveis na pasta themes."""
        if not os.path.exists(self.theme_dir): return []
        return sorted([f[:-5] for f in os.listdir(self.theme_dir) if f.endswith('.json')])

    def apply_theme(self, theme_name):
        """Carrega e aplica um tema pelo nome."""
        path = os.path.join(self.theme_dir, f"{theme_name}.json")
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    if "colors" in data:
                        self.colors.update(data["colors"])
                        return True
            except: pass
        return False

    def export_theme(self, theme_name):
        """Exports the current colors to a new theme file."""
        if not theme_name: return False
        if not theme_name.endswith('.json'):
            theme_name += '.json'
        
        path = os.path.join(self.theme_dir, theme_name)
        data = {"colors": self.colors}
        
        try:
            with open(path, 'w') as f:
                json.dump(data, f, indent=4, sort_keys=True)
            return True
        except Exception:
            return False