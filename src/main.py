# /home/johnb/tasma-code-absulut/src/main.py
import sys
import curses
import os
import argparse
import shutil
import tempfile
from editor import Editor
from ui import UI
from file_handler import FileHandler
from config import Config
from config_window import ConfigWindow
from fuzzy_finder import FuzzyFinderWindow
import locale
import time
from linter import Linter
from plugin_manager import PluginManager
from html_exporter import HtmlExporter
from session_manager import SessionManager
from extractor import ThemeExtractor
from file_picker import FilePicker
import json
import importlib
from key_handler import KeyHandler
try:
    import psutil
except ImportError:
    psutil = None

class TabManager:
    """
    Responsabilidade: Gerenciar múltiplos arquivos abertos como abas.
    Mantém uma lista de objetos Editor e o índice da aba ativa.
    """
    def __init__(self, initial_filepath, file_handler):
        self.file_handler = file_handler
        self.open_tabs = [] # List of {'filepath': str, 'editor': Editor}
        self.current_tab_index = -1
        self.open_file(initial_filepath) # Open the initial file

    def open_file(self, filepath):
        # Check if file is already open
        for i, tab in enumerate(self.open_tabs):
            if tab['filepath'] == filepath:
                self.current_tab_index = i
                return tab['editor']

        # If not open, load it and create a new editor
        try:
            initial_lines = self.file_handler.load_file(filepath)
            editor = Editor(initial_lines)
            self.open_tabs.append({'filepath': filepath, 'editor': editor})
            self.current_tab_index = len(self.open_tabs) - 1
            return editor
        except Exception as e:
            # Re-raise for main to handle status_msg
            raise e

    def get_current_editor(self):
        if self.open_tabs and 0 <= self.current_tab_index < len(self.open_tabs):
            return self.open_tabs[self.current_tab_index]['editor']
        return None

    def get_current_filepath(self):
        if self.open_tabs and 0 <= self.current_tab_index < len(self.open_tabs):
            return self.open_tabs[self.current_tab_index]['filepath']
        return None

    def switch_tab(self, direction): # direction: 1 for next, -1 for previous
        if not self.open_tabs:
            return
        self.current_tab_index = (self.current_tab_index + direction) % len(self.open_tabs)

    def get_tab_info(self):
        info = []
        for i, tab in enumerate(self.open_tabs):
            info.append({
                'filepath': tab['filepath'],
                'is_modified': tab['editor'].is_modified,
                'is_current': (i == self.current_tab_index)
            })
        return info

    def save_current_file(self):
        editor = self.get_current_editor()
        filepath = self.get_current_filepath()
        if editor and filepath:
            self.file_handler.save_file(filepath, editor.lines)
            editor.is_modified = False # Reset modified flag after saving
            return True
        return False

    def check_all_modified(self):
        for tab in self.open_tabs:
            if tab['editor'].is_modified:
                return True
        return False

    def close_current_tab(self):
        """Fecha a aba atual e ajusta o índice. Retorna True se bem-sucedido."""
        if not self.open_tabs:
            return False
        
        del self.open_tabs[self.current_tab_index]
        
        if not self.open_tabs:
            self.current_tab_index = -1
            return True
        
        if self.current_tab_index >= len(self.open_tabs):
            self.current_tab_index = len(self.open_tabs) - 1
        
        return True

    def rename_open_file(self, old_path, new_path):
        for tab in self.open_tabs:
            if tab['filepath'] == old_path:
                tab['filepath'] = new_path

    def move_tab(self, from_idx, to_idx):
        if 0 <= from_idx < len(self.open_tabs) and 0 <= to_idx < len(self.open_tabs):
            if from_idx == to_idx: return
            
            if self.current_tab_index == from_idx:
                self.current_tab_index = to_idx
            elif from_idx < self.current_tab_index <= to_idx:
                self.current_tab_index -= 1
            elif to_idx <= self.current_tab_index < from_idx:
                self.current_tab_index += 1
                
            item = self.open_tabs.pop(from_idx)
            self.open_tabs.insert(to_idx, item)

class TasmaApp:
    def __init__(self, stdscr, filepath):
        self.stdscr = stdscr
        self.filepath = filepath
        self.should_exit = False
        
        # Components
        self.config = Config()
        self.ui = UI(stdscr, self.config)
        self.file_handler = FileHandler()
        self.tab_manager = TabManager(filepath, self.file_handler)
        self.key_handler = KeyHandler(self.config)
        self.session_manager = SessionManager()
        self.linter = Linter()
        self.plugin_manager = PluginManager(plugin_dir=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugins"))
        self.html_exporter = HtmlExporter()
        self.theme_extractor = ThemeExtractor(self.config.theme_dir)
        
        # State
        self.status_msg = f"Arquivo: {self.tab_manager.get_current_filepath()}"
        self.sidebar_visible = False
        self.sidebar_focus = False
        self.show_hidden = False
        self.sidebar_path = self.session_manager.load_sidebar_path()
        self.project_root = self.sidebar_path
        self.sidebar_items = self.file_handler.list_directory(self.sidebar_path, self.show_hidden)
        self.sidebar_idx = 0
        self.sidebar_clipboard = None
        self.sidebar_mode = 'files'
        self.right_sidebar_focus = False
        self.left_plugin_focus = False
        
        self.split_mode = 0
        self.active_split = 0
        self.split_tab_indices = [0, 0]
        self.previous_split_tab_indices = list(self.split_tab_indices)
        
        self.sidebar_undo_stack = []
        self.sidebar_redo_stack = []
        self.trash_dir = os.path.join(tempfile.gettempdir(), 'tasma_trash')
        if not os.path.exists(self.trash_dir): os.makedirs(self.trash_dir)
        
        self.macro_keys = []
        self.recording_macro = False
        self.current_macro_buffer = []
        self.input_queue = []
        self.dragging_tab_idx = None
        self.split_ratio = 0.5
        self.dragging_split = False
        
        self.global_commands = {}
        
        # Stats
        self.last_keypress_time = time.time()
        self.lint_needed = True
        self.last_stats_time = 0
        self.system_status = ""
        self.current_process = psutil.Process(os.getpid()) if psutil else None

        # Load Plugins
        self.last_menu_index = -1
        self.load_plugins()
        
        # Register Actions
        self.register_actions()

    def load_plugins(self):
        plugin_context = {
            'ui': self.ui, 'file_handler': self.file_handler, 'tab_manager': self.tab_manager,
            'config': self.config, 'global_commands': self.global_commands
        }
        self.plugin_manager.load_plugins(plugin_context)
        
        # Load TasmaStore
        try:
            plugins_path = self.plugin_manager.plugin_dir
            project_root = os.path.dirname(plugins_path)
            if project_root not in sys.path:
                sys.path.append(project_root)
            
            if os.path.exists(os.path.join(project_root, "tasmatore", "__init__.py")):
                if 'tasmatore' in sys.modules:
                    import tasmatore
                    importlib.reload(tasmatore)
                else:
                    import tasmatore
                tasmatore.register(plugin_context)
        except Exception as e:
            self.status_msg = f"Erro ao carregar TasmaStore: {e}"

    @property
    def current_editor(self):
        idx = self.split_tab_indices[self.active_split]
        if idx < len(self.tab_manager.open_tabs):
            return self.tab_manager.open_tabs[idx]['editor']
        return None

    @property
    def current_filepath(self):
        idx = self.split_tab_indices[self.active_split]
        if idx < len(self.tab_manager.open_tabs):
            return self.tab_manager.open_tabs[idx]['filepath']
        return None

    def register_actions(self):
        kh = self.key_handler
        
        # File / App
        kh.register_action("save", self.action_save)
        kh.register_action("quit", self.action_quit)
        kh.register_action("open", self.action_open)
        kh.register_action("open_folder", self.action_open_folder)
        kh.register_action("open_config", self.action_open_config)
        kh.register_action("open_settings", self.action_open_settings)
        kh.register_action("export_html", self.action_export_html)
        kh.register_action("import_theme", self.action_import_theme)
        
        # Edit
        kh.register_action("undo", self.action_undo)
        kh.register_action("redo", self.action_redo)
        kh.register_action("copy", self.action_copy)
        kh.register_action("cut", self.action_cut)
        kh.register_action("paste", self.action_paste)
        kh.register_action("select_all", self.action_select_all)
        kh.register_action("duplicate_line", self.action_duplicate_line)
        kh.register_action("delete_line", self.action_delete_line)
        kh.register_action("toggle_comment", self.action_toggle_comment)
        kh.register_action("delete_forward", self.action_delete_general)
        kh.register_action("delete_file", self.action_delete_general)
        kh.register_action("autocomplete", self.action_autocomplete)
        
        # Navigation
        kh.register_action("find", self.action_find)
        kh.register_action("find_next", self.action_find_next)
        kh.register_action("find_regex", self.action_find_regex)
        kh.register_action("replace", self.action_replace)
        kh.register_action("replace_regex", self.action_replace_regex)
        kh.register_action("goto_line", self.action_goto_line)
        kh.register_action("goto_symbol", self.action_goto_symbol)
        kh.register_action("fuzzy_find_file", self.action_fuzzy_find)
        
        # Tabs / Splits
        kh.register_action("close_tab", self.action_close_tab)
        kh.register_action("prev_tab", self.action_prev_tab, fixed_keys=[540, 545])
        kh.register_action("next_tab", self.action_next_tab, fixed_keys=[555, 560])
        kh.register_action("toggle_split", self.action_toggle_split)
        kh.register_action("switch_focus", self.action_switch_focus)
        
        # UI / Sidebar
        kh.register_action("toggle_sidebar", self.action_toggle_sidebar)
        kh.register_action("toggle_right_sidebar", self.action_toggle_right_sidebar)
        kh.register_action("toggle_structure", self.action_toggle_structure)
        kh.register_action("refresh", self.action_sidebar_refresh)
        kh.register_action("toggle_hidden", self.action_sidebar_toggle_hidden)
        kh.register_action("set_root", self.action_sidebar_set_root)
        kh.register_action("rename", self.action_sidebar_rename)
        kh.register_action("new_file", self.action_sidebar_new_file)
        kh.register_action("new_dir", self.action_sidebar_new_dir)
        
        # Macros
        kh.register_action("macro_rec", self.action_macro_rec)
        kh.register_action("macro_play", self.action_macro_play)
        
        # Help
        kh.register_action("help", self.action_help)
        
        # Generic UI
        kh.register_action("ui_up", self.action_ui_up, fixed_keys=curses.KEY_UP)
        kh.register_action("ui_down", self.action_ui_down, fixed_keys=curses.KEY_DOWN)
        kh.register_action("ui_left", self.action_ui_left, fixed_keys=curses.KEY_LEFT)
        kh.register_action("ui_right", self.action_ui_right, fixed_keys=curses.KEY_RIGHT)
        kh.register_action("ui_enter", self.action_ui_enter, fixed_keys=10)
        kh.register_action("ui_enter_alt", self.action_ui_enter, fixed_keys=13)
        kh.register_action("ui_enter_curses", self.action_ui_enter, fixed_keys=curses.KEY_ENTER)
        kh.register_action("ui_esc", self.action_ui_esc, fixed_keys=27)
        kh.register_action("ui_backspace", self.action_ui_backspace, fixed_keys=curses.KEY_BACKSPACE)
        kh.register_action("ui_tab", self.action_ui_tab, fixed_keys=9)
        kh.register_action("ui_shift_tab", self.action_ui_shift_tab, fixed_keys=curses.KEY_BTAB)
        
        kh.register_action("move_word_left", self.action_move_word_left)
        kh.register_action("move_word_right", self.action_move_word_right)
        
        kh.register_action("definition", self.action_definition)
        kh.register_action("toggle_bookmark", lambda: (self.current_editor.toggle_bookmark(), None)[1])
        kh.register_action("next_bookmark", lambda: (self.current_editor.next_bookmark(), None)[1])
        kh.register_action("prev_bookmark", lambda: (self.current_editor.prev_bookmark(), None)[1])
        kh.register_action("jump_bracket", self.action_jump_bracket)
        kh.register_action("toggle_fold", lambda: self.current_editor.toggle_fold())

    def handle_menu_action(self, action):
        """Executa ações vindas do menu global."""
        if not action: return
        
        # Arquivos
        if action == "Novo Arquivo": self.action_sidebar_new_file()
        elif action == "Nova Pasta": self.action_sidebar_new_dir()
        elif action == "Abrir Arquivo": self.action_open()
        elif action == "Abrir Pasta": self.action_open_folder()
        elif action == "Salvar": self.action_save()
        elif action == "Exportar HTML": self.action_export_html()
        elif action == "Fechar Aba": self.action_close_tab()
        elif action == "Sair": self.action_quit()
        
        # Editar
        elif action == "Desfazer": self.action_undo()
        elif action == "Refazer": self.action_redo()
        elif action == "Copiar": self.action_copy()
        elif action == "Colar": self.action_paste()
        elif action == "Recortar": self.action_cut()
        elif action == "Selecionar Tudo": self.action_select_all()
        elif action == "Duplicar Linha": self.action_duplicate_line()
        elif action == "Deletar Linha": self.action_delete_line()
        
        # Exibição
        elif action == "Sidebar": self.action_toggle_sidebar()
        elif action == "Chat IA": self.action_toggle_right_sidebar()
        elif action == "Estrutura": self.action_toggle_structure()
        elif action == "Split Vertical": 
            self.split_mode = 1
            self.status_msg = "Split Vertical"
        elif action == "Split Horizontal": 
            self.split_mode = 2
            self.status_msg = "Split Horizontal"

        # Navegação
        elif action == "Ir para Linha": self.action_goto_line()
        elif action == "Ir para Símbolo": self.action_goto_symbol()
        elif action == "Definição": self.action_definition()
        elif action == "Buscar": self.action_find()
        elif action == "Substituir": self.action_replace()
        elif action == "Buscar em Arquivos": 
            if not self.sidebar_visible:
                self.action_toggle_sidebar()
            self.sidebar_focus = True
            self.input_queue.append(ord('/')) # Simula atalho de busca na sidebar
            
        # Outros
        elif action == "Loja (F2)": 
            if curses.KEY_F2 in self.global_commands: self.global_commands[curses.KEY_F2]()
        elif action == "Gerenciar":
            if curses.KEY_F2 in self.global_commands: self.global_commands[curses.KEY_F2]()
        elif action == "Abrir Configurações": self.action_open_settings()
        elif action == "Importar Tema": self.action_import_theme()
        elif action == "Ajuda (F1)": self.action_help()
        elif action == "Sobre": self.action_about()

    def action_fuzzy_find(self):
        finder = FuzzyFinderWindow(self.ui, self.project_root, self.tab_manager, self.show_hidden)
        finder.run()
        self.stdscr.clear()
        self.status_msg = "Fuzzy finder closed."

    def action_macro_rec(self):
        if self.recording_macro:
            self.recording_macro = False
            self.macro_keys = list(self.current_macro_buffer)
            self.status_msg = f"Macro gravada ({len(self.macro_keys)} teclas)."
        else:
            self.recording_macro = True
            self.current_macro_buffer = []
            self.status_msg = "Gravando macro..."

    def action_import_theme(self):
        picker = FilePicker(self.ui, start_path=".", allowed_extensions=['.json', '.zip'])
        path = picker.run()
        self.stdscr.clear()
        if path:
            self.status_msg = "Importando..."
            # Redraw to show status
            self.ui.draw([self.current_editor], self.active_split, self.split_mode, self.status_msg)
            success, msg = self.theme_extractor.import_themes(path)
            self.status_msg = msg
        else:
            self.status_msg = "Importação cancelada."

    def action_about(self):
        h, w = 12, 50
        y, x = (self.ui.height - h) // 2, (self.ui.width - w) // 2
        win = curses.newwin(h, w, y, x)
        win.box()
        win.bkgd(' ', curses.color_pair(5))
        win.addstr(1, 2, "Sobre TasmaCode", curses.A_BOLD)
        win.addstr(3, 2, "Editor de Texto TUI em Python")
        win.addstr(4, 2, "Versão: 0.2 Alpha")
        win.addstr(5, 2, "Criado por: John Breno")
        win.addstr(7, 2, "Licença MIT")
        win.addstr(9, 2, "Pressione qualquer tecla para fechar...", curses.A_DIM)
        win.refresh()
        win.getch()
        self.stdscr.clear()

    def action_toggle_structure(self):
        if self.ui.left_sidebar_plugin:
            if not self.ui.left_sidebar_plugin.is_visible:
                self.ui.left_sidebar_plugin.is_visible = True
                self.left_plugin_focus = True
                self.sidebar_visible = False
                self.status_msg = "Estrutura aberta"
            else:
                if self.left_plugin_focus:
                    self.ui.left_sidebar_plugin.is_visible = False
                    self.left_plugin_focus = False
                    self.status_msg = "Estrutura fechada"
                else:
                    self.left_plugin_focus = True
                    self.status_msg = "Foco na Estrutura"

    def action_macro_play(self):
        if self.macro_keys:
            self.input_queue.extend(self.macro_keys)
            self.status_msg = "Reproduzindo macro..."
        else:
            self.status_msg = "Nenhuma macro gravada."

    def action_toggle_sidebar(self):
        self.sidebar_visible = not self.sidebar_visible
        if self.sidebar_visible:
            self.sidebar_focus = True
            self.sidebar_items = self.file_handler.list_directory(self.sidebar_path, self.show_hidden)
        else:
            self.sidebar_focus = False

    def action_toggle_right_sidebar(self):
        if self.ui.right_sidebar_plugin:
            if not self.ui.right_sidebar_plugin.is_visible:
                self.ui.right_sidebar_plugin.is_visible = True
                self.right_sidebar_focus = True
                self.status_msg = "Chattovex aberto (Focado)"
            else:
                if self.right_sidebar_focus:
                    self.ui.right_sidebar_plugin.is_visible = False
                    self.right_sidebar_focus = False
                    self.status_msg = "Chattovex fechado"
                else:
                    self.right_sidebar_focus = True
                    self.status_msg = "Foco no Chat"
        else:
            self.status_msg = "Nenhum plugin de chat carregado."

    def action_autocomplete(self):
        completions, prefix = self.current_editor.get_completions()
        if completions:
            idx = 0
            while True:
                # Simplified draw call for autocomplete loop
                self.ui.draw([self.current_editor], self.active_split, self.split_mode, "Autocompletar...")
                
                # Calculate positions
                line_count = len(self.current_editor.lines)
                gutter_width = len(str(line_count)) + 2
                sidebar_w = 25 if self.sidebar_visible else 0
                total_margin = sidebar_w + gutter_width
                content_start_y = 1 if self.tab_manager.open_tabs else 0
                
                self.ui.draw_autocomplete(completions, idx, self.current_editor, content_start_y, total_margin)
                ch = self.ui.get_input()
                if ch == curses.KEY_UP: idx = (idx - 1) % len(completions)
                elif ch == curses.KEY_DOWN: idx = (idx + 1) % len(completions)
                elif isinstance(ch, int) and ch in (10, 13, 9):
                    completion = completions[idx]
                    remainder = completion[len(prefix):]
                    for c in remainder: self.current_editor.insert_char(c)
                    break
                elif ch == 27: break
                else: break
            self.stdscr.clear()

    def action_help(self):
        self.ui.show_help()
        self.stdscr.clear()

    def action_select_all(self):
        self.current_editor.select_all()
        self.status_msg = "Selecionado tudo"

    def action_duplicate_line(self):
        self.current_editor.duplicate_line()
        self.status_msg = "Linha duplicada"

    def action_delete_line(self):
        self.current_editor.delete_current_line()
        self.status_msg = "Linha deletada"

    def action_toggle_comment(self):
        self.current_editor.toggle_comment()
        self.status_msg = "Comentário alternado"

    def action_delete_general(self):
        if self.sidebar_focus and self.sidebar_visible:
            if self.sidebar_items:
                name, is_dir = self.sidebar_items[self.sidebar_idx]
                if name != "..":
                    target_path = os.path.join(self.sidebar_path, name)
                    confirm = self.ui.prompt(f"Deletar '{name}'? (s/n): ")
                    if confirm and confirm.lower() == 's':
                        trash_path = os.path.join(self.trash_dir, os.path.basename(target_path) + "_" + str(os.getpid()))
                        if self.file_handler.move_file(target_path, trash_path):
                            self.sidebar_undo_stack.append({'type': 'delete', 'original': target_path, 'trash': trash_path})
                            self.sidebar_redo_stack.clear()
                            self.sidebar_items = self.file_handler.list_directory(self.sidebar_path, self.show_hidden)
                            self.status_msg = "Deletado (movido para lixeira)"
                        else:
                            self.status_msg = "Erro ao deletar"
        else:
            self.current_editor.delete_forward()

    def action_save(self):
        try:
            self.tab_manager.save_current_file()
            self.status_msg = "Arquivo salvo com sucesso!"
        except Exception as e:
            self.status_msg = f"Erro ao salvar: {str(e)}"

    def action_find(self):
        query = self.ui.prompt("Find: ")
        if query:
            location = self.current_editor.find(query)
            if location:
                self.current_editor.cy, self.current_editor.cx = location
                self.status_msg = f"Encontrado em Ln {location[0]+1}, Col {location[1]+1}"
            else:
                self.status_msg = f"'{query}' não encontrado"

    def action_find_regex(self):
        query = self.ui.prompt("Regex Find: ")
        if query:
            location = self.current_editor.find_regex(query)
            if location:
                self.current_editor.cy, self.current_editor.cx = location
                self.status_msg = f"Regex encontrado em Ln {location[0]+1}, Col {location[1]+1}"
            else:
                self.status_msg = f"Regex '{query}' não encontrado"

    def action_find_next(self):
        location = self.current_editor.find_next()
        if location:
            self.current_editor.cy, self.current_editor.cx = location
            self.status_msg = f"Encontrado em Ln {location[0] + 1}, Col {location[1] + 1}"
        else:
            self.status_msg = f"Nenhuma ocorrência encontrada"

    def action_replace(self):
        find_str = self.ui.prompt("Substituir: ")
        if find_str:
            replace_str = self.ui.prompt(f"Substituir '{find_str}' por: ")
            if replace_str is not None:
                count = self.current_editor.replace_all(find_str, replace_str)
                self.status_msg = f"{count} ocorrências substituídas."
            else:
                self.status_msg = "Substituição cancelada."

    def action_replace_regex(self):
        find_str = self.ui.prompt("Regex Substituir: ")
        if find_str:
            replace_str = self.ui.prompt(f"Substituir Regex '{find_str}' por: ")
            if replace_str is not None:
                count = self.current_editor.replace_all_regex(find_str, replace_str)
                if count == -1: self.status_msg = "Erro na expressão regular."
                else: self.status_msg = f"{count} ocorrências substituídas (Regex)."
            else:
                self.status_msg = "Substituição cancelada."

    def action_copy(self):
        if self.sidebar_focus and self.sidebar_visible:
            if self.sidebar_items:
                name, is_dir = self.sidebar_items[self.sidebar_idx]
                if name != "..":
                    self.sidebar_clipboard = os.path.join(self.sidebar_path, name)
                    self.status_msg = f"Copiado para área de transferência: {name}"
        else:
            self.current_editor.copy()
            self.status_msg = "Copiado para a área de transferência"

    def action_cut(self):
        self.current_editor.cut()
        self.status_msg = "Recortado para a área de transferência"

    def action_paste(self):
        if self.sidebar_focus and self.sidebar_visible:
            if self.sidebar_clipboard and os.path.exists(self.sidebar_clipboard):
                src = self.sidebar_clipboard
                dst_name = os.path.basename(src)
                dst = os.path.join(self.sidebar_path, dst_name)
                if os.path.exists(dst):
                    base, ext = os.path.splitext(dst_name)
                    dst = os.path.join(self.sidebar_path, f"{base}_copy{ext}")
                if self.file_handler.copy_path(src, dst):
                    self.sidebar_items = self.file_handler.list_directory(self.sidebar_path, self.show_hidden)
                    self.sidebar_undo_stack.append({'type': 'copy', 'dest': dst})
                    self.sidebar_redo_stack.clear()
                    self.status_msg = f"Colado: {os.path.basename(dst)}"
                else:
                    self.status_msg = "Erro ao colar arquivo"
            elif self.sidebar_clipboard:
                self.status_msg = "Arquivo de origem não encontrado"
            else:
                self.status_msg = "Nada para colar"
        else:
            self.current_editor.paste()
            self.status_msg = "Colado"

    def action_undo(self):
        if self.sidebar_focus and self.sidebar_visible:
            if self.sidebar_undo_stack:
                action = self.sidebar_undo_stack.pop()
                self.sidebar_redo_stack.append(action)
                if action['type'] == 'rename':
                    self.file_handler.move_file(action['new'], action['old'])
                    self.tab_manager.rename_open_file(action['new'], action['old'])
                    self.status_msg = f"Desfeito: Renomear"
                elif action['type'] == 'delete':
                    self.file_handler.move_file(action['trash'], action['original'])
                    self.status_msg = f"Desfeito: Deletar"
                elif action['type'] == 'copy':
                    trash_path = os.path.join(self.trash_dir, os.path.basename(action['dest']) + "_undo_" + str(os.getpid()))
                    self.file_handler.move_file(action['dest'], trash_path)
                    self.status_msg = f"Desfeito: Copiar"
                self.sidebar_items = self.file_handler.list_directory(self.sidebar_path, self.show_hidden)
            else:
                self.status_msg = "Nada para desfazer na sidebar"
        else:
            if self.current_editor.undo(): self.status_msg = "Desfeito"
            else: self.status_msg = "Nada para desfazer"

    def action_redo(self):
        if self.sidebar_focus and self.sidebar_visible:
            if self.sidebar_redo_stack:
                self.status_msg = "Refazer não implementado totalmente para arquivos."
        else:
            if self.current_editor.redo(): self.status_msg = "Refeito"
            else: self.status_msg = "Nada para refazer"

    def action_open(self):
        filename_to_open = self.ui.prompt("Abrir arquivo: ")
        if filename_to_open:
            try:
                self.tab_manager.open_file(filename_to_open)
                self.status_msg = f"Arquivo '{filename_to_open}' aberto."
            except Exception as e:
                self.status_msg = f"Erro ao abrir arquivo: {str(e)}"

    def action_goto_line(self):
        line_str = self.ui.prompt("Ir para linha: ")
        if line_str:
            try:
                line_num = int(line_str)
                if self.current_editor.goto_line(line_num): self.status_msg = f"Movido para linha {line_num}"
                else: self.status_msg = "Número de linha inválido"
            except ValueError: self.status_msg = "Entrada inválida"

    def action_quit(self):
        if self.tab_manager.check_all_modified():
            self.status_msg = "Arquivo modificado! Ctrl+S para salvar ou Ctrl+Q novamente para forçar saída."
            # Redraw to show message
            self.ui.draw([self.current_editor], self.active_split, self.split_mode, self.status_msg)
            confirm = self.ui.get_input()
            if confirm == self.config.get_key("quit"):
                self.should_exit = True
            elif confirm == self.config.get_key("save"):
                self.tab_manager.save_current_file()
                self.should_exit = True
        else:
            self.should_exit = True

    def action_close_tab(self):
        editor_to_close = self.tab_manager.get_current_editor()
        if editor_to_close.is_modified:
            prompt_msg = f"Salvar '{self.tab_manager.get_current_filepath()}'? (s/n/c): "
            choice = (self.ui.prompt(prompt_msg) or "").lower()
            if choice == 's':
                try:
                    self.tab_manager.save_current_file()
                except Exception as e:
                    self.status_msg = f"Erro ao salvar: {e}"
                    return
            elif choice == 'c':
                self.status_msg = "Fechamento cancelado."
                return
        if self.tab_manager.close_current_tab():
            self.status_msg = "Aba fechada."
            if self.split_tab_indices[self.active_split] >= len(self.tab_manager.open_tabs):
                self.split_tab_indices[self.active_split] = max(0, len(self.tab_manager.open_tabs) - 1)

    def action_sidebar_set_root(self):
        if self.sidebar_focus and self.sidebar_visible and self.sidebar_items:
            name, is_dir = self.sidebar_items[self.sidebar_idx]
            if is_dir and name != "..":
                self.sidebar_path = os.path.join(self.sidebar_path, name)
                self.project_root = self.sidebar_path
                self.session_manager.save_sidebar_path(self.sidebar_path)
                self.sidebar_items = self.file_handler.list_directory(self.sidebar_path, self.show_hidden)
                self.sidebar_idx = 0
                self.status_msg = f"Raiz definida para: {self.sidebar_path}"
            elif name == "..":
                self.sidebar_path = os.path.dirname(self.sidebar_path)
                self.project_root = self.sidebar_path
                self.session_manager.save_sidebar_path(self.sidebar_path)
                self.sidebar_items = self.file_handler.list_directory(self.sidebar_path, self.show_hidden)
                self.sidebar_idx = 0
                self.status_msg = f"Raiz definida para: {self.sidebar_path}"

    def action_sidebar_rename(self):
        if self.sidebar_focus and self.sidebar_visible and self.sidebar_items:
            name, is_dir = self.sidebar_items[self.sidebar_idx]
            if name != "..":
                old_path = os.path.join(self.sidebar_path, name)
                new_name = self.ui.prompt(f"Renomear '{name}' para: ")
                if new_name:
                    new_path = os.path.join(self.sidebar_path, new_name)
                    if self.file_handler.move_file(old_path, new_path):
                        self.tab_manager.rename_open_file(old_path, new_path)
                        self.sidebar_undo_stack.append({'type': 'rename', 'old': old_path, 'new': new_path})
                        self.sidebar_redo_stack.clear()
                        self.sidebar_items = self.file_handler.list_directory(self.sidebar_path, self.show_hidden)
                        self.status_msg = "Renomeado com sucesso"
                    else:
                        self.status_msg = "Erro ao renomear"

    def action_sidebar_new_file(self):
        name = self.ui.prompt("Novo arquivo: ")
        if name:
            path = os.path.join(self.sidebar_path, name)
            if self.file_handler.create_file(path):
                if self.sidebar_visible:
                    self.sidebar_items = self.file_handler.list_directory(self.sidebar_path, self.show_hidden)
                self.status_msg = f"Arquivo criado: {name}"
            else:
                self.status_msg = "Erro ao criar arquivo"

    def action_sidebar_new_dir(self):
        name = self.ui.prompt("Nova pasta: ")
        if name:
            path = os.path.join(self.sidebar_path, name)
            if self.file_handler.create_directory(path):
                if self.sidebar_visible:
                    self.sidebar_items = self.file_handler.list_directory(self.sidebar_path, self.show_hidden)
                self.status_msg = f"Pasta criada: {name}"
            else:
                self.status_msg = "Erro ao criar pasta"

    def action_sidebar_toggle_hidden(self):
        if self.sidebar_focus and self.sidebar_visible:
            self.show_hidden = not self.show_hidden
            self.sidebar_items = self.file_handler.list_directory(self.sidebar_path, self.show_hidden)
            self.sidebar_idx = 0
            self.status_msg = f"Arquivos ocultos: {'Visíveis' if self.show_hidden else 'Escondidos'}"

    def action_sidebar_refresh(self):
        if self.sidebar_focus and self.sidebar_visible:
            self.sidebar_items = self.file_handler.list_directory(self.sidebar_path, self.show_hidden)
            self.status_msg = "Sidebar atualizada."

    def action_ui_up(self):
        if self.sidebar_focus and self.sidebar_visible:
            self.sidebar_idx = max(0, self.sidebar_idx - 1)
        elif self.right_sidebar_focus:
            pass 
        else:
            self.current_editor.move_cursor(0, -1)

    def action_ui_down(self):
        if self.sidebar_focus and self.sidebar_visible:
            self.sidebar_idx = min(len(self.sidebar_items) - 1, self.sidebar_idx + 1)
        else:
            self.current_editor.move_cursor(0, 1)

    def action_ui_left(self):
        if not self.sidebar_focus:
            self.current_editor.move_cursor(-1, 0)

    def action_ui_right(self):
        if not self.sidebar_focus:
            self.current_editor.move_cursor(1, 0)

    def action_ui_enter(self):
        if self.sidebar_focus and self.sidebar_visible:
            if not self.sidebar_items: return
            
            if self.sidebar_mode == 'search':
                item = self.sidebar_items[self.sidebar_idx]
                try:
                    editor = self.tab_manager.open_file(item['file'])
                    editor.goto_line(item['line'])
                    self.sidebar_focus = False
                    self.status_msg = f"Aberto: {os.path.basename(item['file'])}:{item['line']}"
                except Exception as e:
                    self.status_msg = f"Erro: {e}"
            else:
                name, is_dir = self.sidebar_items[self.sidebar_idx]
                full_path = os.path.join(self.sidebar_path, name)
                
                if name == "..":
                    self.sidebar_path = os.path.dirname(self.sidebar_path)
                    self.session_manager.save_sidebar_path(self.sidebar_path)
                    self.sidebar_items = self.file_handler.list_directory(self.sidebar_path, self.show_hidden)
                    self.sidebar_idx = 0
                elif is_dir:
                    confirm_nav = self.config.settings.get("confirm_navigation", True)
                    if confirm_nav:
                        target_abs = os.path.abspath(full_path)
                        root_abs = os.path.abspath(self.project_root)
                        is_inside = (target_abs == root_abs) or target_abs.startswith(os.path.join(root_abs, ""))
                        if not is_inside:
                            confirm = self.ui.prompt(f"Entrar na pasta '{name}'? (s/n): ")
                            if not confirm or confirm.lower() != 's':
                                self.status_msg = "Navegação cancelada."
                                return
                    self.sidebar_path = full_path
                    self.session_manager.save_sidebar_path(self.sidebar_path)
                    self.sidebar_items = self.file_handler.list_directory(self.sidebar_path, self.show_hidden)
                    self.sidebar_idx = 0
                else:
                    try:
                        self.tab_manager.open_file(full_path)
                        self.sidebar_focus = False
                        self.status_msg = f"Aberto: {name}"
                    except Exception as e:
                        self.status_msg = f"Erro: {e}"
        else:
            self.current_editor.insert_newline()

    def action_ui_esc(self):
        if self.right_sidebar_focus:
            self.right_sidebar_focus = False
            self.status_msg = "Foco no Editor"
        elif self.sidebar_focus:
            if self.sidebar_mode == 'search':
                self.sidebar_mode = 'files'
                self.sidebar_items = self.file_handler.list_directory(self.sidebar_path, self.show_hidden)
                self.sidebar_idx = 0
                self.status_msg = "Modo de arquivos."
            else:
                self.sidebar_focus = False
        elif self.current_editor.has_selection():
            self.current_editor.clear_selection()

    def action_ui_backspace(self):
        if not self.sidebar_focus:
            self.current_editor.delete_char()

    def action_ui_tab(self):
        if not self.sidebar_focus:
            if not self.current_editor.expand_snippet(self.config.snippets):
                self.current_editor.indent_selection()

    def action_ui_shift_tab(self):
        if not self.sidebar_focus:
            self.current_editor.dedent_selection()

    def action_prev_tab(self):
        if len(self.tab_manager.open_tabs) > 1:
            self.split_tab_indices[self.active_split] = (self.split_tab_indices[self.active_split] - 1 + len(self.tab_manager.open_tabs)) % len(self.tab_manager.open_tabs)
            new_filepath = self.tab_manager.open_tabs[self.split_tab_indices[self.active_split]]['filepath']
            self.status_msg = f"Aba: {os.path.basename(new_filepath)}"

    def action_next_tab(self):
        if len(self.tab_manager.open_tabs) > 1:
            self.split_tab_indices[self.active_split] = (self.split_tab_indices[self.active_split] + 1) % len(self.tab_manager.open_tabs)
            new_filepath = self.tab_manager.open_tabs[self.split_tab_indices[self.active_split]]['filepath']
            self.status_msg = f"Aba: {os.path.basename(new_filepath)}"

    def action_move_word_left(self):
        self.current_editor.move_word_left()

    def action_move_word_right(self):
        self.current_editor.move_word_right()

    def action_definition(self):
        loc = self.current_editor.find_definition(self.current_editor.get_word_under_cursor())
        if loc:
            self.current_editor.cy = loc[0]
            self.current_editor.cx = loc[1]

    def action_jump_bracket(self):
        match = self.current_editor.get_matching_bracket()
        if match:
            self.current_editor.cy = match[0]
            self.current_editor.cx = match[1]

    def action_toggle_split(self):
        self.split_mode = (self.split_mode + 1) % 3
        self.status_msg = f"Modo Split: {['Nenhum', 'Vertical', 'Horizontal'][self.split_mode]}"

    def action_switch_focus(self):
        if self.split_mode != 0: self.active_split = 1 - self.active_split

    def action_export_html(self):
        default_name = os.path.basename(self.current_filepath) + ".html"
        out_path = self.ui.prompt(f"Exportar HTML para ({default_name}): ")
        if not out_path: out_path = default_name
        if self.html_exporter.export(self.current_editor.lines, out_path): self.status_msg = f"Exportado para {out_path}"
        else: self.status_msg = "Erro ao exportar HTML."

    def action_open_config(self):
        try:
            self.tab_manager.open_file(os.path.abspath(self.config.user_config_path))
            self.status_msg = "Configuração aberta."
        except Exception as e: self.status_msg = f"Erro ao abrir configuração: {e}"

    def action_open_settings(self):
        config_win = ConfigWindow(self.ui, self.config)
        config_win.run()
        self.status_msg = "Settings closed. Restart to apply all changes."
        self.stdscr.clear()

    def action_open_folder(self):
        folder_path = self.ui.prompt("Abrir Pasta: ")
        if folder_path:
            folder_path = os.path.expanduser(folder_path)
            if os.path.isdir(folder_path):
                self.sidebar_path = os.path.abspath(folder_path)
                self.project_root = self.sidebar_path
                self.session_manager.save_sidebar_path(self.sidebar_path)
                self.sidebar_items = self.file_handler.list_directory(self.sidebar_path, self.show_hidden)
                self.sidebar_idx = 0
                self.status_msg = f"Pasta de trabalho: {self.sidebar_path}"
            else: self.status_msg = "Diretório inválido."

    def action_goto_symbol(self):
        symbols = self.current_editor.get_symbols()
        if symbols:
            idx = 0
            while True:
                self.ui.draw([self.current_editor], self.active_split, self.split_mode, "Go to Symbol...")
                self.ui.draw_symbol_picker(symbols, idx)
                ch = self.ui.get_input()
                if ch == curses.KEY_UP: idx = (idx - 1) % len(symbols)
                elif ch == curses.KEY_DOWN: idx = (idx + 1) % len(symbols)
                elif isinstance(ch, int) and ch in (10, 13):
                    line_num = symbols[idx][0]
                    self.current_editor.goto_line(line_num + 1)
                    self.status_msg = f"Saltou para símbolo na linha {line_num + 1}"
                    break
                elif ch == 27: break
            self.stdscr.clear()
        else: self.status_msg = "Nenhum símbolo encontrado."

    def run(self):
        while not self.should_exit:
            if not self.tab_manager.open_tabs:
                break
                
            # Sync state
            if self.tab_manager.current_tab_index != self.split_tab_indices[self.active_split]:
                self.split_tab_indices[self.active_split] = self.tab_manager.current_tab_index

            for i in range(len(self.split_tab_indices)):
                if self.split_tab_indices[i] >= len(self.tab_manager.open_tabs):
                    self.split_tab_indices[i] = max(0, len(self.tab_manager.open_tabs) - 1)

            self.tab_manager.current_tab_index = self.split_tab_indices[self.active_split]

            # Fix Menu Ghosting: Se o menu mudou de estado, força redesenho do editor abaixo dele
            if self.ui.global_menu.active_menu_index != self.last_menu_index:
                for tab in self.tab_manager.open_tabs:
                    tab['editor'].mark_all_dirty()
                self.last_menu_index = self.ui.global_menu.active_menu_index

            # Prepare drawing
            editors_to_draw = [self.tab_manager.open_tabs[self.split_tab_indices[0]]['editor']]
            filepaths_to_draw = [self.tab_manager.open_tabs[self.split_tab_indices[0]]['filepath']]
            if self.split_mode != 0:
                idx2 = self.split_tab_indices[1] if self.split_tab_indices[1] < len(self.tab_manager.open_tabs) else 0
                editors_to_draw.append(self.tab_manager.open_tabs[idx2]['editor'])
                filepaths_to_draw.append(self.tab_manager.open_tabs[idx2]['filepath'])
            
            if self.previous_split_tab_indices != self.split_tab_indices:
                self.stdscr.clear()
                for editor in editors_to_draw:
                    editor.mark_all_dirty()
            self.previous_split_tab_indices = list(self.split_tab_indices)

            tab_info = self.tab_manager.get_tab_info()

            # Stats
            if psutil and (time.time() - self.last_stats_time > 2.0):
                cpu = self.current_process.cpu_percent(interval=None)
                mem_mb = self.current_process.memory_info().rss / 1024 / 1024
                self.system_status = f"CPU: {cpu:.1f}% RAM: {mem_mb:.1f}MB"
                self.last_stats_time = time.time()
            elif not psutil:
                self.system_status = "psutil not installed"

            self.ui.draw(editors_to_draw, self.active_split, self.split_mode, self.split_ratio, self.status_msg, filepaths_to_draw, tab_info,
                    self.sidebar_items, self.sidebar_idx, self.sidebar_focus, self.sidebar_visible, self.sidebar_path, self.system_status)
            
            for tab in self.tab_manager.open_tabs:
                tab['editor'].clean_dirty()

            if self.lint_needed and (time.time() - self.last_keypress_time > 1.0):
                self.linter.lint(self.current_editor, self.current_filepath)
                self.lint_needed = False

            if self.input_queue:
                key = self.input_queue.pop(0)
                curses.napms(10)
            else:
                key = self.ui.get_input()
                
            if key is not None:
                self.last_keypress_time = time.time()
                self.lint_needed = True

            if key is None:
                continue

            key_code = key
            if isinstance(key, str):
                key_code = ord(key)

            # Global Menu Keyboard Handling
            if self.ui.global_menu.active_menu_index != -1:
                handled, action = self.ui.global_menu.handle_key(key_code)
                if handled:
                    if action:
                        self.handle_menu_action(action)
                    continue
                
            handler_context = {'global_commands': self.global_commands}
            if self.key_handler.handle_key(key_code, handler_context):
                continue

            self.status_msg = ""

            if self.left_plugin_focus and self.ui.left_sidebar_plugin and self.ui.left_sidebar_plugin.is_visible:
                if hasattr(self.ui.left_sidebar_plugin, 'handle_input'):
                    self.ui.left_sidebar_plugin.handle_input(key_code)
                continue

            if self.recording_macro:
                self.current_macro_buffer.append(key)

            if self.right_sidebar_focus and self.ui.right_sidebar_plugin and self.ui.right_sidebar_plugin.is_visible:
                if hasattr(self.ui.right_sidebar_plugin, 'handle_input'):
                    self.ui.right_sidebar_plugin.handle_input(key_code)
                continue

            if self.sidebar_focus and self.sidebar_visible:
                if key_code == ord('/'):
                    query = self.ui.prompt("Grep: ")
                    if query:
                        self.sidebar_items = self.file_handler.search_in_files(self.sidebar_path, query, self.show_hidden)
                        self.sidebar_mode = 'search'
                        self.sidebar_idx = 0
                        self.status_msg = f"Busca: '{query}' ({len(self.sidebar_items)} resultados)"
                    else:
                        self.status_msg = "Busca cancelada."
                    continue

            # Mouse
            if key_code == curses.KEY_MOUSE:
                try:
                    id, mx, my, z, bstate = curses.getmouse()
                except curses.error:
                    continue

                # Global Menu Handling
                event_type = 'move'
                if bstate & (curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED | curses.BUTTON1_RELEASED):
                    event_type = 'click'
                
                handled, action = self.ui.global_menu.handle_mouse(mx, my, event_type)
                if handled:
                    if action:
                        self.handle_menu_action(action)
                    continue

                line_count = len(self.current_editor.lines)
                gutter_width = len(str(line_count)) + 2
                sidebar_w = 0
                if self.ui.left_sidebar_plugin and self.ui.left_sidebar_plugin.is_visible:
                    sidebar_w = 25
                elif self.sidebar_visible:
                    sidebar_w = 25
                total_margin = sidebar_w + gutter_width
                content_start_y = (1 if tab_info else 0) + 1 # +1 for menu bar

                split_dims = {'sep': 0}
                available_w = self.ui.width - total_margin
                available_h = self.ui.height - 1 - content_start_y
                if self.split_mode == 1: split_dims['sep'] = int(available_w * self.split_ratio) + total_margin
                elif self.split_mode == 2: split_dims['sep'] = int(available_h * self.split_ratio) + content_start_y
                
                # Tab Interaction
                if my == 1: # Tabs are now at y=1
                    tab_idx, is_close = self.ui.get_tab_click_index(mx, my, tab_info, sidebar_w, tab_y=1)
                    
                    if bstate & curses.BUTTON1_PRESSED:
                        if tab_idx != -1:
                            if is_close:
                                self.split_tab_indices[self.active_split] = tab_idx
                                self.tab_manager.current_tab_index = tab_idx
                                self.action_close_tab()
                            else:
                                self.dragging_tab_idx = tab_idx
                                self.split_tab_indices[self.active_split] = tab_idx
                                self.tab_manager.current_tab_index = tab_idx
                    
                    elif bstate & curses.BUTTON1_RELEASED:
                        if self.dragging_tab_idx is not None:
                            if tab_idx != -1 and tab_idx != self.dragging_tab_idx:
                                self.tab_manager.move_tab(self.dragging_tab_idx, tab_idx)
                                self.split_tab_indices[self.active_split] = self.tab_manager.current_tab_index
                            self.dragging_tab_idx = None
                    
                    elif bstate & curses.BUTTON1_CLICKED:
                        if tab_idx != -1:
                            if is_close:
                                self.split_tab_indices[self.active_split] = tab_idx
                                self.tab_manager.current_tab_index = tab_idx
                                self.action_close_tab()
                            else:
                                self.split_tab_indices[self.active_split] = tab_idx
                                self.tab_manager.current_tab_index = tab_idx
                    continue

                # Split Dragging Logic
                if self.split_mode != 0:
                    is_on_sep = False
                    if self.split_mode == 1 and mx == split_dims['sep']: is_on_sep = True
                    elif self.split_mode == 2 and my == split_dims['sep']: is_on_sep = True

                    if bstate & curses.BUTTON1_PRESSED:
                        if is_on_sep:
                            self.dragging_split = True
                    
                    elif bstate & curses.BUTTON1_RELEASED:
                        self.dragging_split = False
                    
                    if self.dragging_split and (bstate & (curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED | curses.BUTTON1_RELEASED)):
                        # Update ratio
                        if self.split_mode == 1: # Vertical
                            rel_x = mx - total_margin
                            self.split_ratio = max(0.1, min(0.9, rel_x / available_w))
                        elif self.split_mode == 2: # Horizontal
                            rel_y = my - content_start_y
                            self.split_ratio = max(0.1, min(0.9, rel_y / available_h))
                        continue

                # Editor Interaction
                click_result = self.ui.translate_mouse_to_editor(mx, my, content_start_y, total_margin, self.split_mode, self.active_split, split_dims, self.split_ratio)
                
                if click_result:
                    clicked_split, target_y, target_x = click_result
                    
                    if clicked_split != self.active_split and self.split_mode != 0:
                        self.active_split = clicked_split
                        # Não continue aqui, permita que o clique posicione o cursor também

                    pane_y, pane_x = content_start_y, total_margin
                    
                    if self.split_mode == 1 and self.active_split == 1:
                        pane_x = split_dims['sep'] + 1
                    elif self.split_mode == 2 and self.active_split == 1:
                        pane_y = split_dims['sep'] + 1

                    file_y = (target_y - pane_y) + self.current_editor.scroll_offset_y
                    file_x = (target_x - pane_x - gutter_width) + self.current_editor.scroll_offset_x

                    if 0 <= file_y < len(self.current_editor.lines):
                        self.current_editor.cy = file_y
                        self.current_editor.cx = max(0, min(file_x, len(self.current_editor.lines[file_y])))

            # Fallback keys
            elif key_code in (curses.KEY_SLEFT, curses.KEY_SRIGHT, curses.KEY_SR, curses.KEY_SF):
                if not self.current_editor.has_selection():
                    self.current_editor.start_selection()
                
                if key_code == curses.KEY_SLEFT: self.current_editor.move_cursor(-1, 0)
                elif key_code == curses.KEY_SRIGHT: self.current_editor.move_cursor(1, 0)
                elif key_code == curses.KEY_SR: self.current_editor.move_cursor(0, -1)
                elif key_code == curses.KEY_SF: self.current_editor.move_cursor(0, 1)
                self.status_msg = "Selecionando texto"

            elif key_code == curses.KEY_HOME:
                self.current_editor.go_to_start_of_line()
            elif key_code == curses.KEY_END:
                self.current_editor.go_to_end_of_line()

            elif key_code in (530, 535):
                if key_code == 530: self.current_editor.go_to_start_of_file()
                else: self.current_editor.go_to_end_of_file()

            elif key_code in (566, 525):
                if key_code == 566: self.current_editor.move_line_up()
                else: self.current_editor.move_line_down()
            
            elif (isinstance(key, str) and key.isprintable()) or (isinstance(key_code, int) and 32 <= key_code <= 126):
                char = key if isinstance(key, str) else chr(key_code)
                line = self.current_editor.lines[self.current_editor.cy]
                if self.current_editor.cx < len(line) and line[self.current_editor.cx] == char and char in ")]}'\"":
                    self.current_editor.cx += 1
                else:
                    self.current_editor.insert_char(char, auto_close=True)

if __name__ == "__main__":
    locale.setlocale(locale.LC_ALL, '')
    parser = argparse.ArgumentParser(description="Tasma Code Editor")
    parser.add_argument("filename", help="Nome do arquivo para editar", nargs='?', default="novo_arquivo.txt")
    args = parser.parse_args()

    try:
        def main_wrapper(stdscr):
            app = TasmaApp(stdscr, args.filename)
            app.run()
        curses.wrapper(main_wrapper)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Ocorreu um erro fatal: {e}")
