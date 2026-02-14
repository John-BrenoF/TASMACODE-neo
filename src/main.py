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

def main(stdscr, filepath):
    # Inicialização dos módulos
    config = Config()
    ui = UI(stdscr, config) # Initialize UI once
    file_handler = FileHandler()
    tab_manager = TabManager(filepath, file_handler) # Initialize TabManager
    status_msg = f"Arquivo: {tab_manager.get_current_filepath()}"
    
    # Sidebar State
    sidebar_visible = False
    sidebar_focus = False
    show_hidden = False
    
    # Session Management (SRP: Delegado para SessionManager)
    session_manager = SessionManager()
    sidebar_path = session_manager.load_sidebar_path()
    project_root = sidebar_path
    sidebar_items = file_handler.list_directory(sidebar_path, show_hidden)
    sidebar_idx = 0
    sidebar_clipboard = None # Armazena o caminho do arquivo copiado
    sidebar_mode = 'files' # 'files' ou 'search'
    right_sidebar_focus = False # Foco no chat
    left_plugin_focus = False # Foco no plugin da esquerda
    
    # Linter & Plugins
    linter = Linter()
    # Caminho absoluto para a pasta plugins na raiz do projeto
    plugins_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugins")
    plugin_manager = PluginManager(plugin_dir=plugins_path)
    
    # Carrega plugins passando contexto
    global_commands = {}
    plugin_context = {
        'ui': ui, 'file_handler': file_handler, 'tab_manager': tab_manager,
        'config': config, 'global_commands': global_commands
    }
    plugin_manager.load_plugins(plugin_context)
    
    # Carrega TasmaStore manualmente
    try:
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
        status_msg = f"Erro ao carregar TasmaStore: {e}"

    last_keypress_time = time.time()
    lint_needed = True
    last_stats_time = 0
    system_status = ""
    current_process = psutil.Process(os.getpid()) if psutil else None
    
    # Split View State
    split_mode = 0 # 0: None, 1: Vertical, 2: Horizontal
    active_split = 0 # 0 or 1
    split_tab_indices = [0, 0] # Tab index for each split
    
    # Exporter
    html_exporter = HtmlExporter()

    # Theme Extractor
    theme_extractor = ThemeExtractor(config.theme_dir)

    # Sidebar Undo/Redo State
    sidebar_undo_stack = []
    sidebar_redo_stack = []
    trash_dir = os.path.join(tempfile.gettempdir(), 'tasma_trash')
    if not os.path.exists(trash_dir): os.makedirs(trash_dir)
    
    # Macro State
    macro_keys = []
    recording_macro = False
    current_macro_buffer = []
    input_queue = []

    # Loop Principal
    while True:
        # Ensure tab indices are valid
        if not tab_manager.open_tabs:
            break # Sai se não houver mais abas abertas
            
        # Sync tab manager with active split
        tab_manager.current_tab_index = split_tab_indices[active_split]
        if tab_manager.current_tab_index >= len(tab_manager.open_tabs):
             tab_manager.current_tab_index = len(tab_manager.open_tabs) - 1
             split_tab_indices[active_split] = tab_manager.current_tab_index

        # Prepare editors for drawing
        editors_to_draw = [tab_manager.open_tabs[split_tab_indices[0]]['editor']]
        filepaths_to_draw = [tab_manager.open_tabs[split_tab_indices[0]]['filepath']]
        if split_mode != 0:
            idx2 = split_tab_indices[1] if split_tab_indices[1] < len(tab_manager.open_tabs) else 0
            editors_to_draw.append(tab_manager.open_tabs[idx2]['editor'])
            filepaths_to_draw.append(tab_manager.open_tabs[idx2]['filepath'])
        
        current_editor = editors_to_draw[active_split]
        current_filepath = filepaths_to_draw[active_split]
        tab_info = tab_manager.get_tab_info()

        # Update System Stats (every 2 seconds)
        if psutil and (time.time() - last_stats_time > 2.0):
            # Coleta métricas do processo atual
            cpu = current_process.cpu_percent(interval=None)
            mem_mb = current_process.memory_info().rss / 1024 / 1024
            system_status = f"CPU: {cpu:.1f}% RAM: {mem_mb:.1f}MB"
            last_stats_time = time.time()
        elif not psutil:
            system_status = "psutil not installed"

        ui.draw(editors_to_draw, active_split, split_mode, status_msg, filepaths_to_draw, tab_info,
                sidebar_items, sidebar_idx, sidebar_focus, sidebar_visible, sidebar_path, system_status)
        
        # Limpa estado de sujo após o desenho
        for tab in tab_manager.open_tabs:
            tab['editor'].clean_dirty()

        # Linter Logic (Debounce)
        if lint_needed and (time.time() - last_keypress_time > 1.0):
            linter.lint(current_editor, current_filepath)
            lint_needed = False

        # Input Handling
        if input_queue:
            key = input_queue.pop(0)
            # Pequeno delay visual opcional para ver a macro executando
            curses.napms(10)
        else:
            key = ui.get_input()
            
        # Se houve input, atualiza timer do linter
        if key is not None:
            last_keypress_time = time.time()
            lint_needed = True

        if key is None:
            continue

        # Normaliza a tecla para comparação (int para códigos, str para texto)
        key_code = key
        if isinstance(key, str):
            key_code = ord(key)
            
        # Check for global plugin commands first
        if key_code in global_commands:
            global_commands[key_code]()
            # Force a full redraw after plugin window closes
            stdscr.clear()
            status_msg = "Plugin window closed."
            continue

        # Ctrl+P (Fuzzy Find File)
        elif key_code == config.get_key("fuzzy_find_file"):
            finder = FuzzyFinderWindow(ui, project_root, tab_manager, show_hidden)
            finder.run()
            # Force redraw after window closes
            stdscr.clear()
            status_msg = "Fuzzy finder closed."
            continue
            
        status_msg = "" # Limpa a mensagem de status a cada iteração

        # Macro Controls
        if key_code == config.get_key("macro_rec"):
            if recording_macro:
                recording_macro = False
                macro_keys = list(current_macro_buffer)
                status_msg = f"Macro gravada ({len(macro_keys)} teclas)."
            else:
                recording_macro = True
                current_macro_buffer = []
                status_msg = "Gravando macro..."
            continue
        
        # Ctrl+E (Import Theme)
        elif key_code == config.get_key("import_theme"):
            picker = FilePicker(ui, start_path=".", allowed_extensions=['.json', '.zip'])
            path = picker.run()
            
            # Força limpeza da tela após fechar o picker
            stdscr.clear()
            
            if path:
                status_msg = "Importando..."
                # Força desenho para mostrar status "Importando..."
                ui.draw(editors_to_draw, active_split, split_mode, status_msg, filepaths_to_draw, tab_info,
                        sidebar_items, sidebar_idx, sidebar_focus, sidebar_visible, sidebar_path, system_status)
                success, msg = theme_extractor.import_themes(path)
                status_msg = msg
            else:
                status_msg = "Importação cancelada."
            continue

        # Ctrl+R (Toggle Structure Sidebar)
        elif key_code == config.get_key("toggle_structure"):
            if ui.left_sidebar_plugin:
                if not ui.left_sidebar_plugin.is_visible:
                    ui.left_sidebar_plugin.is_visible = True
                    left_plugin_focus = True
                    sidebar_visible = False # Esconde a sidebar de arquivos padrão
                    status_msg = "Estrutura aberta"
                else:
                    if left_plugin_focus:
                        ui.left_sidebar_plugin.is_visible = False
                        left_plugin_focus = False
                        status_msg = "Estrutura fechada"
                    else:
                        left_plugin_focus = True
                        status_msg = "Foco na Estrutura"
            continue

        # Lógica da Sidebar Esquerda (Plugin)
        elif left_plugin_focus and ui.left_sidebar_plugin and ui.left_sidebar_plugin.is_visible:
            if hasattr(ui.left_sidebar_plugin, 'handle_input'):
                ui.left_sidebar_plugin.handle_input(key_code)
            continue

        elif key_code == config.get_key("macro_play"):
            if macro_keys:
                input_queue.extend(macro_keys)
                status_msg = "Reproduzindo macro..."
            else:
                status_msg = "Nenhuma macro gravada."
            continue

        if recording_macro:
            current_macro_buffer.append(key)

        # Ctrl+B (Toggle Sidebar) - ASCII 2
        if key_code == config.get_key("toggle_sidebar"):
            sidebar_visible = not sidebar_visible
            if sidebar_visible:
                sidebar_focus = True
                sidebar_items = file_handler.list_directory(sidebar_path, show_hidden)
            else:
                sidebar_focus = False
            continue

        # Toggle Right Sidebar (Ctrl+H)
        elif key_code == config.get_key("toggle_right_sidebar"):
            if ui.right_sidebar_plugin:
                if not ui.right_sidebar_plugin.is_visible:
                    ui.right_sidebar_plugin.is_visible = True
                    right_sidebar_focus = True # Foca ao abrir
                    status_msg = "Chattovex aberto (Focado)"
                else:
                    # Se já visível, alterna foco ou fecha
                    if right_sidebar_focus:
                        ui.right_sidebar_plugin.is_visible = False
                        right_sidebar_focus = False
                        status_msg = "Chattovex fechado"
                    else:
                        right_sidebar_focus = True
                        status_msg = "Foco no Chat"
            else:
                status_msg = "Nenhum plugin de chat carregado."
        
        # Lógica da Sidebar Direita (Chat)
        elif right_sidebar_focus and ui.right_sidebar_plugin and ui.right_sidebar_plugin.is_visible:
            if key_code == 27: # Esc para sair do foco
                right_sidebar_focus = False
                status_msg = "Foco no Editor"
            else:
                # Passa input para o plugin
                if hasattr(ui.right_sidebar_plugin, 'handle_input'):
                    ui.right_sidebar_plugin.handle_input(key_code)
            continue

        # Lógica da Sidebar Esquerda (Arquivos)
        elif sidebar_focus and sidebar_visible:
            if key_code == curses.KEY_UP:
                sidebar_idx = max(0, sidebar_idx - 1)
            elif key_code == curses.KEY_DOWN:
                sidebar_idx = min(len(sidebar_items) - 1, sidebar_idx + 1)
            elif key_code in (10, 13): # Enter
                if not sidebar_items: continue
                
                if sidebar_mode == 'search':
                    item = sidebar_items[sidebar_idx]
                    try:
                        editor = tab_manager.open_file(item['file'])
                        editor.goto_line(item['line'])
                        sidebar_focus = False
                        status_msg = f"Aberto: {os.path.basename(item['file'])}:{item['line']}"
                    except Exception as e:
                        status_msg = f"Erro: {e}"
                else:
                    name, is_dir = sidebar_items[sidebar_idx]
                    full_path = os.path.join(sidebar_path, name)
                    
                    if name == "..":
                        sidebar_path = os.path.dirname(sidebar_path)
                        session_manager.save_sidebar_path(sidebar_path)
                        sidebar_items = file_handler.list_directory(sidebar_path, show_hidden)
                        sidebar_idx = 0
                    elif is_dir:
                        confirm_nav = config.settings.get("confirm_navigation", True)
                        if confirm_nav:
                            # Verifica se o destino está dentro da raiz do projeto
                            target_abs = os.path.abspath(full_path)
                            root_abs = os.path.abspath(project_root)
                            is_inside = (target_abs == root_abs) or target_abs.startswith(os.path.join(root_abs, ""))
                            
                            if not is_inside:
                                confirm = ui.prompt(f"Entrar na pasta '{name}'? (s/n): ")
                                if not confirm or confirm.lower() != 's':
                                    status_msg = "Navegação cancelada."
                                    continue
                        sidebar_path = full_path
                        session_manager.save_sidebar_path(sidebar_path)
                        sidebar_items = file_handler.list_directory(sidebar_path, show_hidden)
                        sidebar_idx = 0
                    else:
                        try:
                            tab_manager.open_file(full_path)
                            sidebar_focus = False # Retorna foco ao editor
                            status_msg = f"Aberto: {name}"
                        except Exception as e:
                            status_msg = f"Erro: {e}"
            elif key_code == 27: # Esc
                sidebar_focus = False
            
            # Shift+P (Set Root)
            elif key_code == config.get_key("set_root"):
                if sidebar_items:
                    name, is_dir = sidebar_items[sidebar_idx]
                    if is_dir and name != "..":
                        sidebar_path = os.path.join(sidebar_path, name)
                        project_root = sidebar_path
                        session_manager.save_sidebar_path(sidebar_path)
                        sidebar_items = file_handler.list_directory(sidebar_path, show_hidden)
                        sidebar_idx = 0
                        status_msg = f"Raiz definida para: {sidebar_path}"
                    elif name == "..":
                        sidebar_path = os.path.dirname(sidebar_path)
                        project_root = sidebar_path
                        session_manager.save_sidebar_path(sidebar_path)
                        sidebar_items = file_handler.list_directory(sidebar_path, show_hidden)
                        sidebar_idx = 0
                        status_msg = f"Raiz definida para: {sidebar_path}"
            
            # F2 (Rename)
            elif key_code == config.get_key("rename"):
                if sidebar_items:
                    name, is_dir = sidebar_items[sidebar_idx]
                    if name != "..":
                        old_path = os.path.join(sidebar_path, name)
                        new_name = ui.prompt(f"Renomear '{name}' para: ")
                        if new_name:
                            new_path = os.path.join(sidebar_path, new_name)
                            if file_handler.move_file(old_path, new_path):
                                tab_manager.rename_open_file(old_path, new_path)
                                sidebar_undo_stack.append({'type': 'rename', 'old': old_path, 'new': new_path})
                                sidebar_redo_stack.clear()
                                sidebar_items = file_handler.list_directory(sidebar_path, show_hidden)
                                status_msg = "Renomeado com sucesso"
                            else:
                                status_msg = "Erro ao renomear"

            # Delete (KEY_DC)
            elif key_code == config.get_key("delete_file"):
                if sidebar_items:
                    name, is_dir = sidebar_items[sidebar_idx]
                    if name != "..":
                        target_path = os.path.join(sidebar_path, name)
                        confirm = ui.prompt(f"Deletar '{name}'? (s/n): ")
                        if confirm and confirm.lower() == 's':
                            trash_path = os.path.join(trash_dir, os.path.basename(target_path) + "_" + str(os.getpid()))
                            if file_handler.move_file(target_path, trash_path):
                                sidebar_undo_stack.append({'type': 'delete', 'original': target_path, 'trash': trash_path})
                                sidebar_redo_stack.clear()
                                sidebar_items = file_handler.list_directory(sidebar_path, show_hidden)
                                status_msg = "Deletado (movido para lixeira)"
                            else:
                                status_msg = "Erro ao deletar"

            # Ctrl+Z (Undo Sidebar)
            elif key_code == config.get_key("undo"):
                if sidebar_undo_stack:
                    action = sidebar_undo_stack.pop()
                    sidebar_redo_stack.append(action)
                    if action['type'] == 'rename':
                        file_handler.move_file(action['new'], action['old'])
                        tab_manager.rename_open_file(action['new'], action['old'])
                        status_msg = f"Desfeito: Renomear"
                    elif action['type'] == 'delete':
                        file_handler.move_file(action['trash'], action['original'])
                        status_msg = f"Desfeito: Deletar"
                    elif action['type'] == 'copy':
                        trash_path = os.path.join(trash_dir, os.path.basename(action['dest']) + "_undo_" + str(os.getpid()))
                        file_handler.move_file(action['dest'], trash_path)
                        status_msg = f"Desfeito: Copiar"
                    sidebar_items = file_handler.list_directory(sidebar_path, show_hidden)
                else:
                    status_msg = "Nada para desfazer na sidebar"

            # Ctrl+Y (Redo Sidebar)
            elif key_code == config.get_key("redo"):
                if sidebar_redo_stack:
                    # Implementação simplificada de redo (re-executar a ação inversa do undo)
                    status_msg = "Refazer não implementado totalmente para arquivos."
            
            # h (Toggle Hidden Files)
            elif key_code == config.get_key("toggle_hidden"):
                show_hidden = not show_hidden
                sidebar_items = file_handler.list_directory(sidebar_path, show_hidden)
                sidebar_idx = 0
                status_msg = f"Arquivos ocultos: {'Visíveis' if show_hidden else 'Escondidos'}"

            # r (Refresh)
            elif key_code == config.get_key("refresh"):
                sidebar_items = file_handler.list_directory(sidebar_path, show_hidden)
                status_msg = "Sidebar atualizada."

            # n (New File)
            elif key_code == config.get_key("new_file"):
                name = ui.prompt("Novo arquivo: ")
                if name:
                    path = os.path.join(sidebar_path, name)
                    if file_handler.create_file(path):
                        sidebar_items = file_handler.list_directory(sidebar_path, show_hidden)
                        status_msg = f"Arquivo criado: {name}"
                    else:
                        status_msg = "Erro ao criar arquivo"

            # N (New Directory) - Shift+n
            elif key_code == config.get_key("new_dir"):
                name = ui.prompt("Nova pasta: ")
                if name:
                    path = os.path.join(sidebar_path, name)
                    if file_handler.create_directory(path):
                        sidebar_items = file_handler.list_directory(sidebar_path, show_hidden)
                        status_msg = f"Pasta criada: {name}"
                    else:
                        status_msg = "Erro ao criar pasta"

            # Ctrl+C (Copy File)
            elif key_code == config.get_key("copy"):
                if sidebar_items:
                    name, is_dir = sidebar_items[sidebar_idx]
                    if name != "..":
                        sidebar_clipboard = os.path.join(sidebar_path, name)
                        status_msg = f"Copiado para área de transferência: {name}"

            # Ctrl+V (Paste File)
            elif key_code == config.get_key("paste"):
                if sidebar_clipboard and os.path.exists(sidebar_clipboard):
                    src = sidebar_clipboard
                    dst_name = os.path.basename(src)
                    dst = os.path.join(sidebar_path, dst_name)
                    
                    # Evitar sobrescrever se já existir
                    if os.path.exists(dst):
                        base, ext = os.path.splitext(dst_name)
                        dst = os.path.join(sidebar_path, f"{base}_copy{ext}")
                    
                    if file_handler.copy_path(src, dst):
                        sidebar_items = file_handler.list_directory(sidebar_path, show_hidden)
                        # Adicionar ao undo stack (Undo de copy é deletar o destino)
                        sidebar_undo_stack.append({'type': 'copy', 'dest': dst})
                        sidebar_redo_stack.clear()
                        status_msg = f"Colado: {os.path.basename(dst)}"
                    else:
                        status_msg = "Erro ao colar arquivo"
                elif sidebar_clipboard:
                    status_msg = "Arquivo de origem não encontrado"
                else:
                    status_msg = "Nada para colar"
            
            # / (Grep Search)
            elif key_code == ord('/'):
                query = ui.prompt("Grep: ")
                if query:
                    sidebar_items = file_handler.search_in_files(sidebar_path, query, show_hidden)
                    sidebar_mode = 'search'
                    sidebar_idx = 0
                    status_msg = f"Busca: '{query}' ({len(sidebar_items)} resultados)"
                else:
                    status_msg = "Busca cancelada."

            # Esc (Sair do modo de busca ou da sidebar)
            elif key_code == 27:
                if sidebar_mode == 'search':
                    sidebar_mode = 'files'
                    sidebar_items = file_handler.list_directory(sidebar_path, show_hidden)
                    sidebar_idx = 0
                    status_msg = "Modo de arquivos."
                else:
                    sidebar_focus = False

            continue

        # Se sidebar visível mas não focada, permite voltar o foco com Ctrl+E ou algo assim?
        # Vamos usar Ctrl+B para fechar ou re-focar?
        # Por enquanto, se clicar ou usar atalho, volta.
        
        # Calcular gutter width para uso no mouse (ajustado para sidebar)
        line_count = len(current_editor.lines)
        gutter_width = len(str(line_count)) + 2
        sidebar_w = 25 if sidebar_visible else 0
        total_margin = sidebar_w + gutter_width
        content_start_y = 1 if tab_info else 0

        # Ctrl+Space (Autocomplete) - ASCII 0
        if key_code == config.get_key("autocomplete"):
            completions, prefix = current_editor.get_completions()
            if completions:
                idx = 0
                while True:
                    # Redesenha editor e depois o popup
                    ui.draw(editors_to_draw, active_split, split_mode, "Autocompletar...", filepaths_to_draw, tab_info,
                            sidebar_items, sidebar_idx, sidebar_focus, sidebar_visible, sidebar_path)
                    
                    ui.draw_autocomplete(completions, idx, current_editor, content_start_y, total_margin)
                    
                    ch = ui.get_input()
                    
                    if ch == curses.KEY_UP: # get_input agora pode retornar int ou str, mas KEY_UP é int
                        idx = (idx - 1) % len(completions)
                    elif ch == curses.KEY_DOWN:
                        idx = (idx + 1) % len(completions)
                    elif isinstance(ch, int) and ch in (10, 13, 9): # Enter ou Tab
                        completion = completions[idx]
                        # Insere o restante da palavra
                        remainder = completion[len(prefix):]
                        for c in remainder:
                            current_editor.insert_char(c)
                        break
                    elif ch == 27: # Esc (int)
                        break
                    else:
                        # Sai do modo autocomplete e processa a tecla normalmente no próximo loop?
                        # Para simplicidade, apenas sai.
                        break
            continue

        # F1 (Help)
        if key_code == config.get_key("help"):
            ui.show_help()
        
        # Mouse Handling
        elif key_code == curses.KEY_MOUSE:
            # Calculate split dimensions for mouse click
            split_dims = {'sep': 0}
            if split_mode == 1: split_dims['sep'] = (ui.width - total_margin) // 2 + total_margin
            elif split_mode == 2: split_dims['sep'] = (ui.height - 1 - content_start_y) // 2 + content_start_y
            
            click_result = ui.get_mouse_click(content_start_y, total_margin, split_mode, active_split, split_dims)
            
            if click_result:
                clicked_split, target_y, target_x = click_result
                
                # Switch focus if clicked on other split
                if clicked_split != active_split and split_mode != 0:
                    active_split = clicked_split
                    continue

                # Verifica clique nas abas
                tab_idx = ui.get_tab_click_index(target_x, target_y, tab_info, sidebar_w)
                if tab_idx != -1:
                    split_tab_indices[active_split] = tab_idx
                    continue

                # Calcular posição relativa ao painel ativo
                available_w = ui.width - total_margin
                available_h = ui.height - 1 - content_start_y
                pane_y, pane_x = content_start_y, total_margin
                
                if split_mode == 1 and active_split == 1: # Vertical Split 2
                    pane_x += (available_w // 2) + 1
                elif split_mode == 2 and active_split == 1: # Horizontal Split 2
                    pane_y += (available_h // 2) + 1

                # Traduzir para coordenadas do arquivo
                file_y = (target_y - pane_y) + current_editor.scroll_offset_y
                file_x = (target_x - pane_x - gutter_width) + current_editor.scroll_offset_x

                if 0 <= file_y < len(current_editor.lines):
                    current_editor.cy = file_y
                    current_editor.cx = max(0, min(file_x, len(current_editor.lines[file_y])))

        # Mapeamento de Teclas
        # Seleção com Shift
        elif key_code in (curses.KEY_SLEFT, curses.KEY_SRIGHT, curses.KEY_SR, curses.KEY_SF):
            if not current_editor.has_selection():
                current_editor.start_selection()
            
            if key_code == curses.KEY_SLEFT: current_editor.move_cursor(-1, 0)
            elif key_code == curses.KEY_SRIGHT: current_editor.move_cursor(1, 0)
            elif key_code == curses.KEY_SR: current_editor.move_cursor(0, -1)
            elif key_code == curses.KEY_SF: current_editor.move_cursor(0, 1)
            status_msg = "Selecionando texto"

        # Navegação Básica
        elif key_code in (curses.KEY_UP, curses.KEY_DOWN, curses.KEY_LEFT, curses.KEY_RIGHT):
            # Cancela a seleção se uma seta normal for pressionada
            if current_editor.has_selection():
                current_editor.clear_selection()

            if key_code == curses.KEY_UP:
                current_editor.move_cursor(0, -1)
            elif key_code == curses.KEY_DOWN:
                current_editor.move_cursor(0, 1)
            elif key_code == curses.KEY_LEFT:
                current_editor.move_cursor(-1, 0)
            elif key_code == curses.KEY_RIGHT:
                current_editor.move_cursor(1, 0)

        # Home / End (Início/Fim da Linha)
        elif key_code == curses.KEY_HOME:
            current_editor.go_to_start_of_line()
        elif key_code == curses.KEY_END:
            current_editor.go_to_end_of_line()

        # Ctrl+Home / Ctrl+End (Início/Fim do Arquivo) - Códigos comuns
        elif key_code in (530, 535): # Códigos variam, mas estes são comuns para Ctrl+Home/End em xterm
            if key_code == 530: current_editor.go_to_start_of_file()
            else: current_editor.go_to_end_of_file()

        # Ctrl+Left / Ctrl+Right (Mover por palavra) - Códigos comuns
        elif key_code in (540, 555, 545, 560): # Variam muito (kLFT5, kRIT5)
            if key_code in (540, 545): current_editor.move_word_left()
            else: current_editor.move_word_right()

        # Alt+Up / Alt+Down (Mover Linha)
        elif key_code in (566, 525): # Alt+Up, Alt+Down (xterm)
            if key_code == 566: current_editor.move_line_up()
            else: current_editor.move_line_down()

        # Ctrl+A (Select All)
        elif key_code == config.get_key("select_all"):
            current_editor.select_all()
            status_msg = "Selecionado tudo"

        # Ctrl+D (Duplicate Line)
        elif key_code == config.get_key("duplicate_line"):
            current_editor.duplicate_line()
            status_msg = "Linha duplicada"

        # Ctrl+K (Delete Line)
        elif key_code == config.get_key("delete_line"):
            current_editor.delete_current_line()
            status_msg = "Linha deletada"

        # Ctrl+/ (Toggle Comment) - ASCII 31 usually or handled differently
        # Vamos usar Ctrl+_ (ASCII 31) como proxy se Ctrl+/ não funcionar, ou mapear explicitamente
        elif key_code == config.get_key("toggle_comment") or key_code == 47: # 47 é '/' mas com Ctrl pode variar
            current_editor.toggle_comment()
            status_msg = "Comentário alternado"
        
        # Enter
        elif key_code in (10, 13, curses.KEY_ENTER):
            current_editor.insert_newline()
        
        # Backspace (ASCII 127 ou KEY_BACKSPACE)
        elif key_code in (curses.KEY_BACKSPACE, 127, 8):
            current_editor.delete_char()
        
        # Delete (KEY_DC)
        elif key_code == config.get_key("delete_forward"):
            current_editor.delete_forward()

        # Tab (Indent)
        elif key_code == 9:
            if not current_editor.expand_snippet(config.snippets):
                current_editor.indent_selection()

        # Shift+Tab (Dedent) - KEY_BTAB
        elif key_code == curses.KEY_BTAB:
            current_editor.dedent_selection()
        
        # Ctrl+S (Save) - ASCII 19
        elif key_code == config.get_key("save"):
            try:
                tab_manager.save_current_file()
                status_msg = "Arquivo salvo com sucesso!"
            except Exception as e:
                status_msg = f"Erro ao salvar: {str(e)}"

        # Ctrl+Q (Quit) - ASCII 17
        elif key_code == config.get_key("quit"):
            if tab_manager.check_all_modified():
                status_msg = "Arquivo modificado! Ctrl+S para salvar ou Ctrl+Q novamente para forçar saída."
                # Pequena lógica para confirmar saída forçada
                ui.draw(editors_to_draw, active_split, split_mode, status_msg, filepaths_to_draw, tab_info,
                        sidebar_items, sidebar_idx, sidebar_focus, sidebar_visible, sidebar_path)
                confirm = ui.get_input()
                if confirm == 17: # Ctrl+Q de novo
                    break
                elif confirm == 19: # Ctrl+S (int)
                    tab_manager.save_current_file()
                    break
            else:
                break
        
        # Caracteres imprimíveis
        elif (isinstance(key, str) and key.isprintable()) or (isinstance(key_code, int) and 32 <= key_code <= 126):
            char = key if isinstance(key, str) else chr(key_code)
            # Sobrescrita inteligente de fechamento
            line = current_editor.lines[current_editor.cy]
            if current_editor.cx < len(line) and line[current_editor.cx] == char and char in ")]}'\"":
                current_editor.cx += 1
            else:
                current_editor.insert_char(char, auto_close=True)
        
        # Ctrl+F (Find) - ASCII 6
        elif key_code == config.get_key("find"):
            query = ui.prompt("Find: ")
            if query:
                location = current_editor.find(query)
                if location:
                    current_editor.cy, current_editor.cx = location
                    status_msg = f"Encontrado em Ln {location[0]+1}, Col {location[1]+1}"
                else:
                    status_msg = f"'{query}' não encontrado"
            else:
                status_msg = "" # Limpa status se a busca for cancelada

        # Alt+F (Find Regex)
        elif key_code == config.get_key("find_regex"):
            query = ui.prompt("Regex Find: ")
            if query:
                location = current_editor.find_regex(query)
                if location:
                    current_editor.cy, current_editor.cx = location
                    status_msg = f"Regex encontrado em Ln {location[0]+1}, Col {location[1]+1}"
                else:
                    status_msg = f"Regex '{query}' não encontrado"
            else:
                status_msg = ""

        # Ctrl+G (Find Next) - ASCII 7
        elif key_code == config.get_key("find_next"):
            location = current_editor.find_next()
            if location:
                current_editor.cy, current_editor.cx = location
                status_msg = f"Encontrado em Ln {location[0] + 1}, Col {location[1] + 1}"
            else:
                status_msg = f"Nenhuma ocorrência encontrada"

        # Ctrl+R (Replace All) - ASCII 18
        elif key_code == config.get_key("replace"):
            find_str = ui.prompt("Substituir: ")
            if find_str:
                replace_str = ui.prompt(f"Substituir '{find_str}' por: ")
                if replace_str is not None: # Permite string vazia
                    count = current_editor.replace_all(find_str, replace_str)
                    status_msg = f"{count} ocorrências substituídas."
                else:
                    status_msg = "Substituição cancelada."
            else:
                status_msg = "Substituição cancelada."

        # Alt+R (Replace Regex)
        elif key_code == config.get_key("replace_regex"):
            find_str = ui.prompt("Regex Substituir: ")
            if find_str:
                replace_str = ui.prompt(f"Substituir Regex '{find_str}' por: ")
                if replace_str is not None:
                    count = current_editor.replace_all_regex(find_str, replace_str)
                    if count == -1:
                        status_msg = "Erro na expressão regular."
                    else:
                        status_msg = f"{count} ocorrências substituídas (Regex)."
                else:
                    status_msg = "Substituição cancelada."
            else:
                status_msg = "Substituição cancelada."

        # Ctrl+C (Copy) - ASCII 3
        elif key_code == config.get_key("copy"):
            current_editor.copy()
            status_msg = "Copiado para a área de transferência"

        # Ctrl+X (Cut) - ASCII 24
        elif key_code == config.get_key("cut"):
            current_editor.cut()
            status_msg = "Recortado para a área de transferência"

        # Ctrl+V (Paste) - ASCII 22
        elif key_code == config.get_key("paste"):
            current_editor.paste()
            status_msg = "Colado"

        # Ctrl+Z (Undo) - ASCII 26
        elif key_code == config.get_key("undo"):
            if current_editor.undo():
                status_msg = "Desfeito"
            else:
                status_msg = "Nada para desfazer"

        # Ctrl+Y (Redo) - ASCII 25
        elif key_code == config.get_key("redo"):
            if current_editor.redo():
                status_msg = "Refeito"
            else:
                status_msg = "Nada para refazer"

        # Ctrl+O (Open File) - ASCII 15
        elif key_code == config.get_key("open"):
            filename_to_open = ui.prompt("Abrir arquivo: ")
            if filename_to_open:
                try:
                    tab_manager.open_file(filename_to_open)
                    status_msg = f"Arquivo '{filename_to_open}' aberto."
                except Exception as e:
                    status_msg = f"Erro ao abrir arquivo: {str(e)}"
            else:
                status_msg = "Abertura de arquivo cancelada."

        # Ctrl+L (Go to Line) - ASCII 12
        elif key_code == config.get_key("goto_line"):
            line_str = ui.prompt("Ir para linha: ")
            if line_str:
                try:
                    line_num = int(line_str)
                    if current_editor.goto_line(line_num):
                        status_msg = f"Movido para linha {line_num}"
                    else:
                        status_msg = "Número de linha inválido"
                except ValueError:
                    status_msg = "Entrada inválida"

        # F12 (Go to Definition)
        elif key_code == config.get_key("definition"):
            word = current_editor.get_word_under_cursor()
            if word:
                loc = current_editor.find_definition(word)
                if loc:
                    current_editor.cy, current_editor.cx = loc
                    status_msg = f"Definição de '{word}' encontrada."
                else:
                    status_msg = f"Definição de '{word}' não encontrada."

        # Go to Symbol (Ctrl+T / Ctrl+Shift+O)
        elif key_code == config.get_key("goto_symbol"):
            symbols = current_editor.get_symbols()
            if symbols:
                idx = 0
                while True:
                    ui.draw(editors_to_draw, active_split, split_mode, "Go to Symbol...", filepaths_to_draw, tab_info,
                            sidebar_items, sidebar_idx, sidebar_focus, sidebar_visible, sidebar_path, system_status)
                    ui.draw_symbol_picker(symbols, idx)
                    
                    ch = ui.get_input()
                    if ch == curses.KEY_UP:
                        idx = (idx - 1) % len(symbols)
                    elif ch == curses.KEY_DOWN:
                        idx = (idx + 1) % len(symbols)
                    elif isinstance(ch, int) and ch in (10, 13): # Enter
                        line_num = symbols[idx][0]
                        current_editor.goto_line(line_num + 1)
                        status_msg = f"Saltou para símbolo na linha {line_num + 1}"
                        break
                    elif ch == 27: # Esc
                        break
            else:
                status_msg = "Nenhum símbolo encontrado."

        # Bookmarks
        elif key_code == config.get_key("toggle_bookmark"):
            current_editor.toggle_bookmark()
            status_msg = "Marcador alternado."
        elif key_code == config.get_key("next_bookmark"):
            current_editor.next_bookmark()
            status_msg = "Próximo marcador."
        elif key_code == config.get_key("prev_bookmark"):
            current_editor.prev_bookmark()
            status_msg = "Marcador anterior."

        # Jump to Matching Bracket (Ctrl+B default in new config)
        elif key_code == config.get_key("jump_bracket"):
            match = current_editor.get_matching_bracket()
            if match:
                current_editor.cy, current_editor.cx = match
                status_msg = "Saltou para parêntese correspondente."

        # Toggle Split (Ctrl+P)
        elif key_code == config.get_key("toggle_split"):
            split_mode = (split_mode + 1) % 3
            status_msg = f"Modo Split: {['Nenhum', 'Vertical', 'Horizontal'][split_mode]}"

        # Switch Focus (F6)
        elif key_code == config.get_key("switch_focus"):
            if split_mode != 0:
                active_split = 1 - active_split

        # Toggle Fold (F10)
        elif key_code == config.get_key("toggle_fold"):
            current_editor.toggle_fold()
            status_msg = "Dobra alternada."

        # Export HTML (F7)
        elif key_code == config.get_key("export_html"):
            default_name = os.path.basename(current_filepath) + ".html"
            out_path = ui.prompt(f"Exportar HTML para ({default_name}): ")
            if not out_path: out_path = default_name
            
            if html_exporter.export(current_editor.lines, out_path):
                status_msg = f"Exportado para {out_path}"
            else:
                status_msg = "Erro ao exportar HTML."

        # Open Config (Alt+J)
        elif key_code == config.get_key("open_config"):
            try:
                tab_manager.open_file(os.path.abspath(config.filepath))
                status_msg = "Configuração aberta."
            except Exception as e:
                status_msg = f"Erro ao abrir configuração: {e}"

        # Shift+C (Open Settings)
        elif key_code == config.get_key("open_settings"):
            config_win = ConfigWindow(ui, config)
            config_win.run()
            # After closing, a restart is needed to apply some changes (like colors)
            status_msg = "Settings closed. Restart to apply all changes."
            # Force a full redraw
            stdscr.clear()
            continue

        # Ctrl+K (Open Folder)
        elif key_code == config.get_key("open_folder"):
            folder_path = ui.prompt("Abrir Pasta: ")
            if folder_path:
                folder_path = os.path.expanduser(folder_path)
                if os.path.isdir(folder_path):
                    sidebar_path = os.path.abspath(folder_path)
                    project_root = sidebar_path
                    session_manager.save_sidebar_path(sidebar_path)
                    sidebar_items = file_handler.list_directory(sidebar_path, show_hidden)
                    sidebar_idx = 0
                    status_msg = f"Pasta de trabalho: {sidebar_path}"
                else:
                    status_msg = "Diretório inválido."
            continue

        # Ctrl+W (Close Tab) - ASCII 23
        elif key_code == config.get_key("close_tab"):
            editor_to_close = tab_manager.get_current_editor()
            if editor_to_close.is_modified:
                prompt_msg = f"Salvar '{tab_manager.get_current_filepath()}'? (s/n/c): "
                choice = (ui.prompt(prompt_msg) or "").lower()
                
                if choice == 's':
                    try:
                        tab_manager.save_current_file()
                    except Exception as e:
                        status_msg = f"Erro ao salvar: {e}"
                        continue # Não fecha a aba se o salvamento falhar
                elif choice == 'c':
                    status_msg = "Fechamento cancelado."
                    continue
                # Se for 'n' ou qualquer outra coisa, apenas prossegue para fechar

            if tab_manager.close_current_tab():
                status_msg = "Aba fechada."
                # Update indices after closing
                if split_tab_indices[active_split] >= len(tab_manager.open_tabs):
                    split_tab_indices[active_split] = max(0, len(tab_manager.open_tabs) - 1)
                
            continue # Recomeça o loop para redesenhar com a nova aba (ou sair)

        # PageUp (Switch Tab Left) - curses.KEY_PPAGE
        elif key_code == curses.KEY_PPAGE:
            split_tab_indices[active_split] = (split_tab_indices[active_split] - 1) % len(tab_manager.open_tabs)
            status_msg = f"Trocado para: {tab_manager.get_current_filepath()}"

        # PageDown (Switch Tab Right) - curses.KEY_NPAGE
        elif key_code == curses.KEY_NPAGE:
            split_tab_indices[active_split] = (split_tab_indices[active_split] + 1) % len(tab_manager.open_tabs)
            status_msg = f"Trocado para: {tab_manager.get_current_filepath()}"

if __name__ == "__main__":
    locale.setlocale(locale.LC_ALL, '')
    parser = argparse.ArgumentParser(description="Tasma Code Editor")
    parser.add_argument("filename", help="Nome do arquivo para editar", nargs='?', default="novo_arquivo.txt")
    args = parser.parse_args()

    try:
        curses.wrapper(main, args.filename)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Ocorreu um erro fatal: {e}")
