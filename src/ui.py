# /home/johnb/tasma-code-absulut/src/ui.py
import curses
import keyword
import os
import icons
from status_bar import StatusBar
from help_window import HelpWindow

class UI:
    """
    Responsabilidade: Renderizar o estado do editor no terminal e capturar input.
    Gerencia rolagem (scrolling) visual.
    """
    def __init__(self, stdscr, config):
        self.stdscr = stdscr
        self.config = config
        self.height, self.width = stdscr.getmaxyx()
        self.right_sidebar_plugin = None # Plugin registrado para a direita
        self.left_sidebar_plugin = None # Plugin registrado para a esquerda
        self.status_bar = StatusBar()
        
        # Configurações do Curses
        curses.use_default_colors()
        curses.noecho()
        curses.raw()
        curses.nonl() # Desabilita tradução automática de Enter(13) para Newline(10)
        curses.meta(1) # Habilita suporte a teclas Alt (8-bit)
        self.stdscr.keypad(True)
        curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
        
        # Cores para Syntax Highlighting
        self._initialize_colors()

        self.PYTHON_KEYWORDS = set(keyword.kwlist)
        
        # Estado anterior para detectar mudanças de layout
        self.last_sidebar_visible = False
        self.last_split_mode = 0

    def _initialize_colors(self):
        """(Re)Initializes all color pairs based on the current config."""
        config = self.config
        if curses.has_colors():
            curses.init_pair(1, config.get_color_code(config.colors["keyword"]), -1)  # Keywords
            curses.init_pair(2, config.get_color_code(config.colors["string"]), -1)   # Strings
            curses.init_pair(3, config.get_color_code(config.colors["comment"]), -1)    # Comments
            curses.init_pair(4, config.get_color_code(config.colors["active_tab_fg"]), config.get_color_code(config.colors["active_tab_bg"])) # Active Tab
            curses.init_pair(5, config.get_color_code(config.colors["inactive_tab_fg"]), config.get_color_code(config.colors["inactive_tab_bg"])) # Inactive Tab / Sidebar
            curses.init_pair(6, config.get_color_code(config.colors["number"]), -1) # Numbers/Decorators
            curses.init_pair(7, config.get_color_code(config.colors["class"]), -1)     # Class/Self
            curses.init_pair(8, curses.COLOR_RED, -1)     # Linter Error
            # Status Bar
            curses.init_pair(9, config.get_color_code(config.colors["statusbar_fg"]), config.get_color_code(config.colors["statusbar_bg"]))
            self.statusbar_pair = curses.color_pair(9)
            
            self.color_map = {
                "YELLOW": curses.COLOR_YELLOW, "GREEN": curses.COLOR_GREEN,
                "CYAN": curses.COLOR_CYAN, "RED": curses.COLOR_RED,
                "BLUE": curses.COLOR_BLUE, "MAGENTA": curses.COLOR_MAGENTA,
                "WHITE": curses.COLOR_WHITE, "BLACK": curses.COLOR_BLACK
            }
            
            self.sidebar_pairs = {}
            self.active_tab_pairs = {}
            self.statusbar_icon_pairs = {}
            
            base_sidebar = 10
            base_active = 20
            base_statusbar_icon = 30

            for i, (name, color_const) in enumerate(self.color_map.items()):
                curses.init_pair(base_sidebar + i, color_const, config.get_color_code(config.colors["sidebar_bg"]))
                self.sidebar_pairs[name] = curses.color_pair(base_sidebar + i)
                
                curses.init_pair(base_active + i, color_const, config.get_color_code(config.colors["active_tab_bg"]))
                self.active_tab_pairs[name] = curses.color_pair(base_active + i)

                curses.init_pair(base_statusbar_icon + i, color_const, config.get_color_code(config.colors["statusbar_bg"]))
                self.statusbar_icon_pairs[name] = curses.color_pair(base_statusbar_icon + i)

    def get_file_icon(self, name, is_dir):
        """
        Retorna (icone, par_cor_sidebar, par_cor_active_tab).
        Delega para o módulo icons e mapeia para os pares de cores do curses.
        """
        icon, color_name = icons.get_icon_info(name, is_dir)
        sidebar_color = self.sidebar_pairs.get(color_name, curses.color_pair(5))
        active_color = self.active_tab_pairs.get(color_name, curses.color_pair(4))
        return icon, sidebar_color, active_color

    def get_input(self):
        """Captura uma tecla pressionada."""
        try:
            return self.stdscr.get_wch()
        except (AttributeError, curses.error):
            return self.stdscr.getch()

    def update_dimensions(self):
        """Atualiza dimensões se o terminal for redimensionado."""
        self.height, self.width = self.stdscr.getmaxyx()

    def get_mouse_click(self, content_start_y, gutter_width, split_mode, active_split, split_dims):
        """Traduz evento de mouse para coordenadas do arquivo."""
        try:
            _, mx, my, _, _ = curses.getmouse()
            
            # Determina em qual split o clique ocorreu
            clicked_split = 0
            if split_mode == 1: # Vertical
                if mx >= split_dims['sep']:
                    clicked_split = 1
            elif split_mode == 2: # Horizontal
                if my >= split_dims['sep']:
                    clicked_split = 1
            
            return clicked_split, my, mx
        except curses.error:
            return None

    def get_tab_click_index(self, mx, my, tab_info, sidebar_width):
        """Retorna o índice da aba clicada ou -1."""
        if my != 0: return -1 # Abas estão na linha 0
        
        current_x = sidebar_width
        for i, tab in enumerate(tab_info):
            filename = os.path.basename(tab['filepath'])
            # Cálculo de largura deve bater com _draw_tabs:
            # " " (1) + icon (1) + " " + filename + flags + " " (len) + "|" (1)
            display_name = f" {filename}{'*' if tab['is_modified'] else ''} "
            tab_width = 2 + len(display_name) + 1
            
            if current_x <= mx < current_x + tab_width:
                return i
            current_x += tab_width
        return -1

    def _draw_python_line(self, y, line, offset_x, gutter_width):
        """Desenha uma linha com realce de sintaxe Python básico."""
        i = 0
        while i < len(line):
            screen_x = i - offset_x + gutter_width
            if screen_x >= self.width -1:
                break

            # Strings
            if line[i] in "\"'":
                quote_char = line[i]
                j = i + 1
                while j < len(line) and line[j] != quote_char:
                    j += 1
                j = min(j + 1, len(line))
                token = line[i:j]
                self._addstr_clipped(y, screen_x, token, curses.color_pair(2), min_x=gutter_width)
                i = j
                continue
            
            # Comentários
            if line[i] == '#':
                token = line[i:]
                self._addstr_clipped(y, screen_x, token, curses.color_pair(3), min_x=gutter_width)
                break

            # Decoradores (@foo)
            if line[i] == '@':
                j = i + 1
                while j < len(line) and (line[j].isalnum() or line[j] == '_'): j += 1
                token = line[i:j]
                self._addstr_clipped(y, screen_x, token, curses.color_pair(6), min_x=gutter_width)
                i = j
                continue

            # Números
            if line[i].isdigit():
                self._addstr_clipped(y, screen_x, line[i], curses.color_pair(6), min_x=gutter_width)
                i += 1
                continue

            # Palavras-chave e identificadores
            if line[i].isalpha() or line[i] == '_':
                j = i
                while j < len(line) and (line[j].isalnum() or line[j] == '_'):
                    j += 1
                token = line[i:j]
                color = curses.color_pair(1) if token in self.PYTHON_KEYWORDS else 0
                if token == 'self': color = curses.color_pair(7)
                elif token[0].isupper(): color = curses.color_pair(7) # Classes simples
                
                self._addstr_clipped(y, screen_x, token, color, min_x=gutter_width)
                i = j
                continue

            # Outros caracteres
            self._addstr_clipped(y, screen_x, line[i], min_x=gutter_width)
            i += 1

    def _addstr_clipped(self, y, x, text, attr=0, min_x=0):
        """Helper para adicionar string que pode ser cortada pela borda da tela."""
        if x >= self.width -1 or x + len(text) <= min_x:
            return
        if x < min_x:
            text = text[min_x - x:]
            x = min_x
        if x + len(text) > self.width - 1:
            text = text[:self.width - 1 - x]
        
        if text:
            try:
                self.stdscr.addstr(y, x, text, attr)
            except curses.error: pass

    def _draw_tabs(self, tab_info):
        """Desenha a barra de abas no topo da tela."""
        if not tab_info:
            return

        tab_line_y = 0
        current_x = 0
        for tab in tab_info:
            filename = os.path.basename(tab['filepath']) # Just filename
            icon, _, active_icon_color = self.get_file_icon(filename, False)
            
            # Define cores base
            base_color = curses.color_pair(4) if tab['is_current'] else curses.color_pair(5)
            icon_color = active_icon_color if tab['is_current'] else curses.color_pair(5) # Inactive usa preto/branco padrão
            
            try:
                self.stdscr.addstr(tab_line_y, current_x, " ", base_color)
                self.stdscr.addstr(tab_line_y, current_x + 1, icon, icon_color)
                display_name = f" {filename}{'*' if tab['is_modified'] else ''} "
                self.stdscr.addstr(tab_line_y, current_x + 2, display_name, base_color)
                current_x += 2 + len(display_name)
                
                self.stdscr.addstr(tab_line_y, current_x, "|", curses.color_pair(5))
                current_x += len(display_name)
            except curses.error:
                break # Ran out of screen space

        # Fill remaining space on tab line
        try:
            self.stdscr.addstr(tab_line_y, current_x, " " * (self.width - current_x), curses.color_pair(5))
        except curses.error:
            pass

    def draw_sidebar(self, items, selection_index, focus, width, current_path):
        """Desenha a barra lateral de arquivos."""
        # Fundo da sidebar
        for y in range(self.height - 1):
            try:
                self.stdscr.addstr(y, 0, " " * width, curses.color_pair(5))
                self.stdscr.addch(y, width, '│')
            except curses.error: pass
        
        # Cabeçalho (Path)
        path_str = f" {os.path.basename(os.path.abspath(current_path))}/"
        self._addstr_clipped(0, 0, path_str, curses.color_pair(5) | curses.A_BOLD, min_x=0)
        try: self.stdscr.addstr(1, 0, "─" * width)
        except curses.error: pass

        # Itens
        start_y = 2
        max_items = self.height - 3
        scroll = 0
        if selection_index >= max_items:
            scroll = selection_index - max_items + 1
            
        for i, item in enumerate(items[scroll:]):
            if i >= max_items: break
            y = start_y + i
            style = curses.color_pair(5)
            if i + scroll == selection_index:
                style = curses.A_REVERSE | (curses.color_pair(4) if focus else curses.color_pair(5))
            
            # Adiciona ícone e nome
            if isinstance(item, tuple):
                name, is_dir = item
                icon, sidebar_icon_color, _ = self.get_file_icon(name, is_dir)
                display_name = f" {name}"
            elif isinstance(item, dict):
                # Resultado de busca
                name = os.path.basename(item['file'])
                line_num = item['line']
                is_dir = False
                icon, sidebar_icon_color, _ = self.get_file_icon(name, is_dir)
                display_name = f" {name}:{line_num}"
            else:
                continue

            if len(display_name) > width - 2:
                display_name = display_name[:width-3] + "…"
            
            try:
                if i + scroll == selection_index:
                    # Item selecionado: tudo com cor de seleção (geralmente reverso)
                    self.stdscr.addstr(y, 1, f"{icon}{display_name}", style)
                else:
                    # Item normal: ícone colorido, texto padrão
                    self.stdscr.addstr(y, 1, icon, sidebar_icon_color)
                    self.stdscr.addstr(y, 2, display_name, style)
            except curses.error: pass
            except curses.error: pass

    def draw(self, editors, active_split, split_mode, status_message="", filepaths=None, tab_info=None, 
             sidebar_items=None, sidebar_selection=0, sidebar_focus=False, show_sidebar=False, sidebar_path=".", system_info=""):
        """Renderiza o texto, cursor e barra de status, e abas."""
        self.update_dimensions()
        
        # Detecta mudança de layout que exige limpeza total
        layout_changed = (show_sidebar != self.last_sidebar_visible) or (split_mode != self.last_split_mode)
        if layout_changed:
            self.stdscr.erase()
            for ed in editors: ed.mark_all_dirty()
            self.last_sidebar_visible = show_sidebar
            self.last_split_mode = split_mode

        if filepaths is None: filepaths = [""]

        sidebar_width = 0
        if self.left_sidebar_plugin and self.left_sidebar_plugin.is_visible:
            sidebar_width = 25
            self.left_sidebar_plugin.draw(self.stdscr, 0, 0, self.height - 1, sidebar_width)
        elif show_sidebar:
            sidebar_width = 25
            self.draw_sidebar(sidebar_items, sidebar_selection, sidebar_focus, sidebar_width - 1, sidebar_path)

        # Ajuste da área do editor
        editor_base_x = sidebar_width

        # Lógica da Sidebar Direita (IA Chat)
        right_sidebar_w = 0
        if self.right_sidebar_plugin and self.right_sidebar_plugin.is_visible:
            right_sidebar_w = 35
            # Garante espaço mínimo para o editor
            if self.width - editor_base_x - right_sidebar_w < 20:
                right_sidebar_w = 0

        # Draw tabs first
        if tab_info:
            # Tabs precisam ser desenhadas com offset se sidebar estiver aberta?
            # Geralmente tabs ficam acima do editor. Vamos mover as tabs para a direita também.
            # Mas _draw_tabs usa coordenadas absolutas. Vamos ajustar _draw_tabs ou apenas desenhar a partir de editor_base_x.
            # Para simplicidade, vamos desenhar tabs a partir de editor_base_x manualmente aqui ou ajustar _draw_tabs.
            # Vamos ajustar _draw_tabs para aceitar offset X, mas como não quero mudar a assinatura dele agora,
            # vou fazer um hack rápido: desenhar tabs normalmente e a sidebar vai sobrescrever a esquerda se for desenhada depois?
            # Não, sidebar já foi desenhada. Vamos redesenhar tabs com offset.
            
            # Melhor: Ajustar _draw_tabs para começar em editor_base_x
            tab_line_y = 0
            current_x = editor_base_x
            for tab in tab_info:
                filename = os.path.basename(tab['filepath'])
                display_name = f" {filename}{'*' if tab['is_modified'] else ''} "
                color_pair = curses.color_pair(4) if tab['is_current'] else curses.color_pair(5)
                try:
                    self.stdscr.addstr(tab_line_y, current_x, display_name, color_pair)
                    current_x += len(display_name)
                    self.stdscr.addstr(tab_line_y, current_x, "|", curses.color_pair(5))
                    current_x += 1
                except curses.error: break
            
            # Fill rest
            try: self.stdscr.addstr(tab_line_y, current_x, " " * (self.width - current_x), curses.color_pair(5))
            except curses.error: pass

            content_start_y = 1 # Content starts below tabs
            display_height = self.height - 2 # Account for tabs and status bar
        else:
            content_start_y = 0
            display_height = self.height - 1 # Account for status bar only

        # Split Logic
        # split_mode: 0=None, 1=Vertical, 2=Horizontal
        
        available_w = self.width - editor_base_x - right_sidebar_w
        available_h = display_height
        
        pane1_rect = [content_start_y, editor_base_x, available_h, available_w]
        pane2_rect = None
        
        if split_mode == 1: # Vertical
            mid = available_w // 2
            pane1_rect = [content_start_y, editor_base_x, available_h, mid]
            pane2_rect = [content_start_y, editor_base_x + mid + 1, available_h, available_w - mid - 1]
            # Draw separator
            for i in range(available_h):
                try: self.stdscr.addch(content_start_y + i, editor_base_x + mid, '│', curses.color_pair(5))
                except: pass
                
        elif split_mode == 2: # Horizontal
            mid = available_h // 2
            pane1_rect = [content_start_y, editor_base_x, mid, available_w]
            pane2_rect = [content_start_y + mid + 1, editor_base_x, available_h - mid - 1, available_w]
            # Draw separator
            try: self.stdscr.addstr(content_start_y + mid, editor_base_x, "─" * available_w, curses.color_pair(5))
            except: pass

        # Draw Panes
        self._draw_editor_pane(editors[0], pane1_rect, filepaths[0], active_split == 0)
        if split_mode != 0 and len(editors) > 1 and pane2_rect:
            self._draw_editor_pane(editors[1], pane2_rect, filepaths[1], active_split == 1)

        # Draw Right Sidebar
        if right_sidebar_w > 0:
            # Passa se está focado ou não (precisamos saber se right_sidebar_focus é True, mas ui não sabe disso diretamente aqui, vamos assumir que o plugin sabe ou passamos um flag extra se necessário. Por enquanto, o plugin desenha igual)
            # Melhoria: Atualizar a assinatura do draw do plugin para aceitar focus
            pass # O plugin já desenha. Se quisermos passar foco, teríamos que alterar a chamada no main ou passar aqui.
            # Vamos assumir que o plugin gerencia seu estado visual ou simplificar.
            # Na verdade, o plugin não sabe se tem foco global. Vamos alterar a chamada no main.py para passar o foco?
            # Não, o UI.draw é chamado pelo main. Vamos adicionar um parametro opcional no UI.draw ou deixar o plugin desenhar o cursor se tiver texto.
            self.right_sidebar_plugin.draw(self.stdscr, self.width - right_sidebar_w, content_start_y, display_height, right_sidebar_w)

        # Barra de Status (Global)
        active_editor = editors[active_split]
        active_filepath = filepaths[active_split] if filepaths else ""
        
        self.status_bar.draw(self, active_editor, active_split, system_info, status_message, active_filepath)

        # Posicionar Cursor Físico
        cursor_rect = pane1_rect if active_split == 0 else pane2_rect
        if cursor_rect:
            y, x, h, w = cursor_rect
            
            line_count = len(active_editor.lines)
            line_num_width = len(str(line_count))
            gutter_width = line_num_width + 2
            
            screen_y = y + active_editor.cy - active_editor.scroll_offset_y
            screen_x = x + gutter_width + active_editor.cx - active_editor.scroll_offset_x
            
            if y <= screen_y < y + h and x + gutter_width <= screen_x < x + w:
                try: self.stdscr.move(screen_y, screen_x)
                except: pass

        self.stdscr.noutrefresh()
        curses.doupdate()

    def _draw_editor_pane(self, editor, rect, filepath, is_active):
        y, x, h, w = rect
        
        visual_indices = editor.get_visual_indices()
        
        # Lógica de Rolagem Vertical
        # Encontrar índice visual do cursor
        try:
            vis_cursor_y = visual_indices.index(editor.cy)
        except ValueError:
            vis_cursor_y = 0
        
        old_scroll_y = editor.scroll_offset_y
        if vis_cursor_y < editor.scroll_offset_y:
            editor.scroll_offset_y = vis_cursor_y
        if vis_cursor_y >= editor.scroll_offset_y + h:
            editor.scroll_offset_y = vis_cursor_y - (h - 1)

        # Calcular largura da calha (gutter) para numeração de linhas
        line_count = len(editor.lines)
        line_num_width = len(str(line_count))
        gutter_width = line_num_width + 3 # Espaço para número + fold + separador
        total_left_margin = x + gutter_width

        old_scroll_x = editor.scroll_offset_x
        # Lógica de Rolagem Horizontal
        screen_width = w - gutter_width # Largura efetiva para o texto
        if editor.cx < editor.scroll_offset_x:
            editor.scroll_offset_x = editor.cx
        if editor.cx >= editor.scroll_offset_x + screen_width:
            editor.scroll_offset_x = editor.cx - screen_width + 1

        # Se houve rolagem, força redesenho total deste painel
        if editor.scroll_offset_y != old_scroll_y or editor.scroll_offset_x != old_scroll_x:
            editor.mark_all_dirty()

        # Get normalized selection once for drawing
        selection = editor.get_normalized_selection()
        
        # Get matching bracket
        matching_bracket = editor.get_matching_bracket()

        # Determina quais linhas desenhar
        lines_to_draw = range(h)
        if not editor.needs_full_redraw:
            # Filtra apenas linhas sujas que estão visíveis
            lines_to_draw = [i for i in range(h) if (i + editor.scroll_offset_y) < len(visual_indices) and 
                             visual_indices[i + editor.scroll_offset_y] in editor.dirty_lines]

        # Desenhar linhas visíveis
        for i in lines_to_draw:
            vis_idx = i + editor.scroll_offset_y
            if vis_idx >= len(visual_indices):
                break
            
            file_line_idx = visual_indices[vis_idx]
            line_content = editor.lines[file_line_idx]
            
            if file_line_idx in editor.folds:
                line_content += " ..."
            
            # Adjust y-coordinate for content drawing
            screen_y_for_content = y + i

            # Desenhar número da linha
            if self.config.settings.get("relative_line_numbers", False):
                if file_line_idx == editor.cy:
                    line_num_str = str(file_line_idx + 1).rjust(line_num_width)
                else:
                    line_num_str = str(abs(file_line_idx - editor.cy)).rjust(line_num_width)
            else:
                line_num_str = str(file_line_idx + 1).rjust(line_num_width)
            
            line_attr = curses.color_pair(3)
            if file_line_idx == editor.cy:
                line_attr = curses.A_BOLD | curses.color_pair(1) # Realce linha atual
            
            # Marcadores
            if file_line_idx in editor.bookmarks:
                line_attr = curses.color_pair(7) | curses.A_BOLD # Vermelho para bookmark
            
            # Linter Errors
            linter_char = "│"
            if file_line_idx in editor.linter_errors:
                linter_char = "E"
                line_attr = curses.color_pair(8) | curses.A_BOLD
            
            fold_char = "+" if file_line_idx in editor.folds else " "
            
            try:
                self.stdscr.addstr(screen_y_for_content, x, f"{line_num_str}{fold_char}{linter_char}", line_attr)
                # Limpa o resto da linha antes de desenhar o conteúdo (importante para redesenho parcial)
                self.stdscr.clrtoeol() 
            except curses.error: pass

            if filepath.endswith(".py") and curses.has_colors():
                self._draw_python_line(screen_y_for_content, line_content, editor.scroll_offset_x, total_left_margin)
            else:
                visible_text = line_content[editor.scroll_offset_x : editor.scroll_offset_x + screen_width]
                try:
                    self.stdscr.addstr(screen_y_for_content, total_left_margin, visible_text)
                except curses.error:
                    pass

            # Overlay selection highlight
            if selection:
                (sel_start_y, sel_start_x), (sel_end_y, sel_end_x) = selection
                if sel_start_y <= file_line_idx <= sel_end_y:
                    highlight_start_pos = sel_start_x if file_line_idx == sel_start_y else 0
                    highlight_end_pos = sel_end_x if file_line_idx == sel_end_y else len(line_content)
                    
                    highlight_text = line_content[highlight_start_pos:highlight_end_pos]
                    screen_x_for_highlight = highlight_start_pos - editor.scroll_offset_x + total_left_margin
                    
                    if highlight_text:
                        self._addstr_clipped(screen_y_for_content, screen_x_for_highlight, highlight_text, curses.A_REVERSE, min_x=total_left_margin)
            
            # Highlight matching bracket
            if matching_bracket:
                mb_y, mb_x = matching_bracket
                if mb_y == file_line_idx:
                    mb_screen_x = mb_x - editor.scroll_offset_x + total_left_margin
                    self._addstr_clipped(screen_y_for_content, mb_screen_x, editor.lines[mb_y][mb_x], curses.A_BOLD | curses.A_REVERSE, min_x=total_left_margin)

        # Limpar área vazia abaixo do texto (se arquivo for menor que a tela)
        if editor.needs_full_redraw:
            lines_drawn = min(len(visual_indices) - editor.scroll_offset_y, h)
            for i in range(lines_drawn, h):
                try: self.stdscr.move(y + i, x); self.stdscr.clrtoeol()
                except: pass

        # Scrollbar Visual (lado direito)
        if len(editor.lines) > h:
            scroll_pct = editor.scroll_offset_y / max(1, len(visual_indices) - h)
            bar_pos = int(min(1.0, scroll_pct) * (h - 1)) + y
            try:
                self.stdscr.addch(bar_pos, x + w - 1, '║', curses.color_pair(5))
            except curses.error: pass

    def show_help(self):
        """Exibe uma janela de ajuda."""
        help_win = HelpWindow(self, self.config)
        help_win.run()

    def prompt(self, message=""):
        """
        Exibe um prompt na barra de status e retorna a entrada do usuário.
        Retorna None se a entrada for vazia.
        """
        # Garante que o prompt espere o input do usuário (modo bloqueante)
        self.stdscr.timeout(-1)
        
        self.stdscr.attron(curses.A_REVERSE)
        self.stdscr.addstr(self.height - 1, 0, message)
        self.stdscr.addstr(self.height - 1, len(message), " " * (self.width - len(message) - 1))
        self.stdscr.attroff(curses.A_REVERSE)
        
        curses.echo()
        self.stdscr.keypad(False)
        
        self.stdscr.move(self.height - 1, len(message))
        input_str = self.stdscr.getstr(self.height - 1, len(message)).decode('utf-8')
        
        curses.noecho()
        self.stdscr.keypad(True)
        
        return input_str if input_str else None

    def draw_autocomplete(self, items, selected_idx, editor, content_start_y, total_left_margin):
        """Desenha o menu popup de autocompletar."""
        if not items: return
        
        max_len = min(max(len(i) for i in items), 40)
        h = min(len(items), 8) + 2
        w = max_len + 4
        
        # Calcular posição na tela
        screen_y = content_start_y + editor.cy - editor.scroll_offset_y + 1
        screen_x = editor.cx - editor.scroll_offset_x + total_left_margin
        
        # Ajustar se sair da tela
        if screen_y + h > self.height:
            screen_y = screen_y - h - 1 # Desenha acima
        
        if screen_x + w > self.width:
            screen_x = self.width - w
            
        try:
            win = curses.newwin(h, w, int(screen_y), int(screen_x))
            win.box()
            for i, item in enumerate(items[:8]): # Mostrar max 8
                style = curses.A_REVERSE if i == selected_idx else curses.A_NORMAL
                win.addstr(i + 1, 2, item[:max_len].ljust(max_len), style)
            win.refresh()
        except curses.error: pass

    def draw_symbol_picker(self, symbols, selected_idx):
        """Desenha o popup de seleção de símbolos."""
        if not symbols: return
        
        h = min(len(symbols), 15) + 2
        w = min(self.width - 4, 60)
        y = (self.height - h) // 2
        x = (self.width - w) // 2
        
        try:
            win = curses.newwin(h, w, y, x)
            win.box()
            win.addstr(0, 2, " Go to Symbol ")
            
            max_display = h - 2
            start_idx = 0
            if selected_idx >= max_display:
                start_idx = selected_idx - max_display + 1
            
            for i in range(max_display):
                data_idx = start_idx + i
                if data_idx >= len(symbols): break
                line_num, content = symbols[data_idx]
                display_text = f"{line_num+1}: {content.strip()}"[:w-4]
                style = curses.A_REVERSE if data_idx == selected_idx else curses.A_NORMAL
                win.addstr(i + 1, 2, display_text.ljust(w-4), style)
            win.refresh()
        except curses.error: pass
