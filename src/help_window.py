# /home/johnb/tasma-code-absulut/src/help_window.py
import curses

class HelpWindow:
    def __init__(self, ui, config):
        self.ui = ui
        self.config = config
        self.command_map = self._get_command_map()

    def _format_key(self, key_code):
        """Converte um código de tecla do curses em uma string legível."""
        if not isinstance(key_code, int):
            return str(key_code)

        # Teclas de Função
        if curses.KEY_F0 <= key_code <= curses.KEY_F12:
            return f"F{key_code - curses.KEY_F0}"

        # Teclas Alt (assumindo que meta() está ativo e retorna 128 + código do caractere)
        if key_code >= 128 and key_code < 256:
            char = chr(key_code - 128)
            return f"Alt+{char}"

        # Teclas Ctrl (caracteres de controle ASCII)
        if 1 <= key_code <= 26:
            return f"Ctrl+{chr(ord('A') + key_code - 1)}"

        # Teclas especiais comuns
        specials = {
            curses.KEY_UP: "Up", curses.KEY_DOWN: "Down",
            curses.KEY_LEFT: "Left", curses.KEY_RIGHT: "Right",
            curses.KEY_HOME: "Home", curses.KEY_END: "End",
            curses.KEY_PPAGE: "PageUp", curses.KEY_NPAGE: "PageDown",
            curses.KEY_DC: "Delete", curses.KEY_BACKSPACE: "Backspace",
            9: "Tab", curses.KEY_BTAB: "Shift+Tab",
            10: "Enter", 13: "Enter", 27: "Esc", 32: "Space",
            80: "Shift+P" # Codificado para set_root
        }
        if key_code in specials:
            return specials[key_code]

        # Caracteres imprimíveis
        if 32 < key_code <= 126:
            return chr(key_code)

        return f"Code:{key_code}" # Fallback

    def _get_command_map(self):
        """Agrupa comandos por categoria e formata seus atalhos."""
        keys = self.config.keys
        
        categories = {
            "Arquivo": [
                ("Abrir Arquivo", "open"), ("Abrir Pasta", "open_folder"),
                ("Salvar", "save"), ("Fechar Aba", "close_tab"), ("Sair", "quit"),
            ],
            "Edição": [
                ("Desfazer", "undo"), ("Refazer", "redo"), ("Copiar", "copy"),
                ("Recortar", "cut"), ("Colar", "paste"), ("Duplicar Linha", "duplicate_line"),
                ("Alternar Comentário", "toggle_comment"),
            ],
            "Navegação": [
                ("Achar Arquivo (Fuzzy)", "fuzzy_find_file"), ("Ir para Linha", "goto_line"),
                ("Ir para Símbolo", "goto_symbol"), ("Próximo Marcador", "next_bookmark"),
                ("Anterior Marcador", "prev_bookmark"), ("Mudar Foco", "switch_focus"),
            ],
            "Visualização e Ferramentas": [
                ("Alternar Sidebar", "toggle_sidebar"), ("Alternar Chat IA", "toggle_right_sidebar"),
                ("Alternar Split", "toggle_split"), ("Abrir Configurações", "open_settings"),
                ("Abrir Git", "open_git_window"), ("Mostrar Ajuda", "help"),
            ]
        }
        
        command_map = {}
        for category, commands in categories.items():
            command_map[category] = []
            for desc, key_name in commands:
                key_code = keys.get(key_name)
                if key_code is not None:
                    formatted_key = self._format_key(key_code)
                    command_map[category].append((desc, formatted_key))
        return command_map

    def run(self):
        """Exibe a janela e espera pela tecla Esc para fechar."""
        self.draw()
        while True:
            key = self.ui.get_input()
            key_code = key if isinstance(key, int) else (ord(key) if isinstance(key, str) else -1)
            if key_code == 27: # Esc
                break

    def draw(self):
        h, w = self.ui.height, self.ui.width
        win_h = min(30, h - 4)
        win_w = min(80, w - 6)
        win_y = (h - win_h) // 2
        win_x = (w - win_w) // 2

        win = curses.newwin(win_h, win_w, win_y, win_x)
        win.bkgd(' ', curses.color_pair(5))
        win.box()
        win.addstr(0, 2, " Atalhos (F1) ", curses.A_BOLD)

        y, col_width = 2, (win_w - 5) // 2
        col1_y, col2_y, col_idx = y, y, 0

        for category, commands in self.command_map.items():
            current_y = col1_y if col_idx % 2 == 0 else col2_y
            current_x = 2 if col_idx % 2 == 0 else 3 + col_width
            if current_y >= win_h - 3: continue

            win.addstr(current_y, current_x, category, curses.A_BOLD | curses.A_UNDERLINE)
            current_y += 1

            for desc, key in commands:
                if current_y >= win_h - 3: continue
                line = f"  {desc.ljust(22)} {key}"
                win.addstr(current_y, current_x, line[:col_width])
                current_y += 1
            
            if col_idx % 2 == 0: col1_y = current_y + 1
            else: col2_y = current_y + 1
            col_idx += 1
        
        win.addstr(win_h - 2, 2, "Pressione qualquer tecla para fechar.")
        win.refresh()