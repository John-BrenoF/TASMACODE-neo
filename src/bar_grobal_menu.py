import curses

class GlobalMenuBar:
    def __init__(self, ui):
        self.ui = ui
        self.menus = [
            {"label": "Arquivos", "options": [
                {"label": "Novo...", "submenu": ["Novo Arquivo", "Nova Pasta"]},
                "Abrir Arquivo", "Abrir Pasta", "Salvar", "Exportar HTML", "Fechar Aba", "Sair"
            ]},
            {"label": "Editar", "options": ["Desfazer", "Refazer", "Copiar", "Colar", "Recortar", "Selecionar Tudo", "Duplicar Linha", "Deletar Linha"]},
            {"label": "Exibição", "options": ["Sidebar", "Chat IA", "Estrutura", "Split Vertical", "Split Horizontal"]},
            {"label": "Navegação", "options": ["Ir para Linha", "Ir para Símbolo", "Definição", "Buscar", "Substituir", "Buscar em Arquivos"]},
            {"label": "Plugins", "options": ["Loja (F2)", "Gerenciar"]},

        ]
        self.active_menu_index = -1
        self.selected_option_index = -1
        self.selected_submenu_index = -1
        self.rects = []
        self.focus_on_submenu = False

    def draw(self, stdscr, width):
        # Draw bar background
        bar_attr = curses.color_pair(5) | curses.A_REVERSE
        try:
            stdscr.attron(bar_attr)
            stdscr.addstr(0, 0, " " * width)
            stdscr.attroff(bar_attr)
        except curses.error: pass

        current_x = 1
        self.rects = []
        
        for i, menu in enumerate(self.menus):
            attr = bar_attr
            if i == self.active_menu_index:
                attr = curses.color_pair(4) | curses.A_BOLD | curses.A_REVERSE
                label = f" {menu['label']} ▼ "
            else:
                label = f" {menu['label']} "
            
            try:
                stdscr.addstr(0, current_x, label, attr)
            except curses.error: pass
            
            self.rects.append((current_x, len(label)))
            current_x += len(label)

        # Draw dropdown if active
        if self.active_menu_index != -1:
            self._draw_dropdown(stdscr, self.active_menu_index)

    def _draw_dropdown(self, stdscr, index):
        menu = self.menus[index]
        x = self.rects[index][0]
        y = 1
        options = menu['options']
        
        # Calcula largura baseada no item mais longo
        max_len = 0
        for o in options:
            txt = o['label'] if isinstance(o, dict) else o
            max_len = max(max_len, len(txt))
        max_len += 6 # Espaço para padding e setas
        
        for i, option in enumerate(options):
            style = curses.color_pair(5) | curses.A_REVERSE
            if i == self.selected_option_index:
                style = curses.color_pair(4) | curses.A_BOLD | curses.A_REVERSE
            
            label = option['label'] if isinstance(option, dict) else option
            display_text = f" {label} ".ljust(max_len)
            
            # Adiciona indicador de submenu
            if isinstance(option, dict) and 'submenu' in option:
                display_text = display_text[:-2] + "► "

            try:
                # Shadow/Background
                stdscr.addstr(y + i, x, display_text, style)
            except curses.error: pass

        # Desenha Submenu se ativo
        if self.selected_option_index != -1:
            selected_opt = options[self.selected_option_index]
            if isinstance(selected_opt, dict) and 'submenu' in selected_opt:
                self._draw_submenu(stdscr, x + max_len, y + self.selected_option_index, selected_opt['submenu'])

    def _draw_submenu(self, stdscr, x, y, options):
        max_len = max(len(o) for o in options) + 4
        for i, option in enumerate(options):
            style = curses.color_pair(5) | curses.A_REVERSE
            # Simples highlight no hover do submenu (pode ser melhorado com active_submenu_index)
            if i == self.selected_submenu_index:
                style = curses.color_pair(4) | curses.A_BOLD | curses.A_REVERSE
            try:
                stdscr.addstr(y + i, x, f" {option} ".ljust(max_len), style)
            except curses.error: pass

    def handle_mouse(self, mx, my, event_type):
        # Click on Top Bar
        if my == 0:
            if event_type == 'click':
                for i, (x, w) in enumerate(self.rects):
                    if x <= mx < x + w:
                        if self.active_menu_index == i:
                            self.active_menu_index = -1 # Toggle Close
                        else:
                            self.active_menu_index = i # Switch/Open
                        self.selected_option_index = -1
                        self.selected_submenu_index = -1
                        self.focus_on_submenu = False
                        return True, None
                # Clicked on top bar but not on a menu -> Close
                if self.active_menu_index != -1:
                    self.active_menu_index = -1
                    self.selected_option_index = -1
                    self.selected_submenu_index = -1
                    self.focus_on_submenu = False
                    return True, None
            
            elif event_type == 'move':
                # Switch on hover only if a menu is already open
                if self.active_menu_index != -1:
                    for i, (x, w) in enumerate(self.rects):
                        if x <= mx < x + w:
                            if self.active_menu_index != i:
                                # Fecha o anterior e abre o novo (comportamento de deslizar)
                                self.active_menu_index = i
                                self.selected_option_index = -1
                                self.selected_submenu_index = -1
                                self.focus_on_submenu = False
                                return True, None
            return False, None

        # Interaction with Dropdown
        if self.active_menu_index != -1:
            menu = self.menus[self.active_menu_index]
            x = self.rects[self.active_menu_index][0]
            options = menu['options']
            
            max_len = 0
            for o in options:
                txt = o['label'] if isinstance(o, dict) else o
                max_len = max(max_len, len(txt))
            max_len += 6
            
            # Check if inside dropdown
            if 1 <= my <= len(options) and x <= mx < x + max_len:
                option_idx = my - 1
                if event_type == 'move':
                    if self.selected_option_index != option_idx:
                        self.selected_option_index = option_idx
                        self.selected_submenu_index = -1 # Reset submenu selection when changing main item
                        self.focus_on_submenu = False
                        return True, None
                elif event_type == 'click':
                    selected = options[option_idx]
                    if isinstance(selected, dict):
                        return True, None # Clicked on submenu parent, do nothing (wait for submenu click)
                    else:
                        self.active_menu_index = -1 # Close on action
                        self.selected_option_index = -1
                        self.selected_submenu_index = -1
                        self.focus_on_submenu = False
                        return True, selected
            
            # Check if inside Submenu (if open)
            elif self.selected_option_index != -1:
                selected_opt = options[self.selected_option_index]
                if isinstance(selected_opt, dict) and 'submenu' in selected_opt:
                    sub_options = selected_opt['submenu']
                    sub_x = x + max_len
                    sub_y = 1 + self.selected_option_index
                    sub_w = max(len(o) for o in sub_options) + 4
                    
                    if sub_y <= my < sub_y + len(sub_options) and sub_x <= mx < sub_x + sub_w:
                        sub_idx = my - sub_y
                        if event_type == 'move':
                            if self.selected_submenu_index != sub_idx:
                                self.selected_submenu_index = sub_idx
                                self.focus_on_submenu = True
                                return True, None
                        elif event_type == 'click':
                            self.active_menu_index = -1
                            self.selected_option_index = -1
                            self.selected_submenu_index = -1
                            self.focus_on_submenu = False
                            return True, sub_options[sub_idx]
                    else:
                        # Click outside closes menu
                        if event_type == 'click':
                            self.active_menu_index = -1
                            self.selected_option_index = -1
                            self.selected_submenu_index = -1
                            self.focus_on_submenu = False
                            return True, None
            else:
                # Click outside closes menu
                if event_type == 'click':
                    self.active_menu_index = -1
                    self.selected_option_index = -1
                    self.selected_submenu_index = -1
                    self.focus_on_submenu = False
                    return True, None
            
            
        return False, None

    def handle_key(self, key):
        if self.active_menu_index == -1: return False, None

        # --- SUBMENU NAVIGATION ---
        if self.focus_on_submenu:
            current_option = self.menus[self.active_menu_index]['options'][self.selected_option_index]
            submenu_options = current_option.get('submenu', [])
            if not submenu_options: # Should not happen if focus_on_submenu is true
                self.focus_on_submenu = False
                return True, None

            if key == curses.KEY_UP:
                self.selected_submenu_index = (self.selected_submenu_index - 1) % len(submenu_options)
                return True, None
            elif key == curses.KEY_DOWN:
                self.selected_submenu_index = (self.selected_submenu_index + 1) % len(submenu_options)
                return True, None
            elif key == curses.KEY_LEFT:
                self.focus_on_submenu = False
                self.selected_submenu_index = -1
                return True, None
            elif key in (10, 13): # Enter
                if self.selected_submenu_index != -1:
                    action = submenu_options[self.selected_submenu_index]
                    self.active_menu_index = -1; self.selected_option_index = -1; self.focus_on_submenu = False; self.selected_submenu_index = -1
                    return True, action
            elif key == 27: # Esc
                self.focus_on_submenu = False
                self.selected_submenu_index = -1
                return True, None
            return True # Consume other keys

        # --- MAIN DROPDOWN / TOP-LEVEL NAVIGATION ---
        options = self.menus[self.active_menu_index]['options']
        
        if key == curses.KEY_UP:
            if self.selected_option_index == -1: self.selected_option_index = len(options)
            self.selected_option_index = (self.selected_option_index - 1) % len(options)
            return True, None
        elif key == curses.KEY_DOWN:
            self.selected_option_index = (self.selected_option_index + 1) % len(options)
            return True, None
        elif key == curses.KEY_LEFT:
            self.active_menu_index = (self.active_menu_index - 1) % len(self.menus)
            self.selected_option_index = -1
            return True, None
        elif key == curses.KEY_RIGHT:
            if self.selected_option_index != -1:
                option = options[self.selected_option_index]
                if isinstance(option, dict) and 'submenu' in option:
                    self.focus_on_submenu = True
                    self.selected_submenu_index = 0
                    return True, None
            self.active_menu_index = (self.active_menu_index + 1) % len(self.menus)
            self.selected_option_index = -1
            return True, None
        elif key in (10, 13): # Enter
            if self.selected_option_index != -1:
                option = options[self.selected_option_index]
                if isinstance(option, dict) and 'submenu' in option:
                    self.focus_on_submenu = True
                    self.selected_submenu_index = 0
                    return True, None
                else:
                    action = option
                    self.active_menu_index = -1; self.selected_option_index = -1
                    return True, action
        elif key == 27: # Esc
            self.active_menu_index = -1; self.selected_option_index = -1
            return True, None
            
        return False, None