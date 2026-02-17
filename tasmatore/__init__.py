import curses
import os
import sys
import threading
import time
import webbrowser
import re

# Adiciona diretório atual ao path
current_dir = os.path.dirname(os.path.abspath(__file__))

from .store_ui import StoreUI
from .installer import PluginInstaller

class TasmaStorePlugin:
    def __init__(self):
        self.context = None
        self.active = False
        self.ui = None
        self.installer = None
        self.plugins = []
        self.selected_idx = 0
        self.focus = 'input' # 'input' or 'list'
        self.confirm_delete_plugin = None

    def register(self, context):
        """Registra o plugin e o atalho F2."""
        self.context = context
        
        # Define o diretório de plugins (um nível acima da pasta tasmatore)
        plugins_dir = os.path.join(os.path.dirname(current_dir), "plugins")
        if not os.path.exists(plugins_dir):
            try: os.makedirs(plugins_dir)
            except: pass
        self.installer = PluginInstaller(plugins_dir)
        
        # Registra o comando global F2
        # curses.KEY_F2 é geralmente 266
        if 'global_commands' in context:
            context['global_commands'][curses.KEY_F2] = self.run

    def run(self):
        """Loop principal da janela da loja (Bloqueante)."""
        self.active = True
        stdscr = self.context['ui'].stdscr
        self.ui = StoreUI(stdscr)
        self.refresh_plugins_list()
        self.selected_idx = 0
        
        curses.curs_set(0)

        while self.active:
            self.ui.draw(self.plugins, self.selected_idx, self.focus, self.confirm_delete_plugin)
            
            if self.ui.is_loading:
                self.ui.animation_frame += 1
                stdscr.timeout(100) # Animação não-bloqueante
            else:
                stdscr.timeout(-1) # Bloqueante
            
            try:
                key = stdscr.get_wch()
            except curses.error:
                key = None

            if key == -1 or key is None:
                continue

            self.handle_input(key)

        # Restaura timeout padrão (bloqueante ou definido pelo editor)
        stdscr.timeout(-1)

    def refresh_plugins_list(self):
        names = self.installer.list_installed_plugins()
        self.plugins = []
        for name in names:
            desc = self.installer.get_plugin_description(name)
            repo = self.installer.get_plugin_repository_link(name)
            self.plugins.append({'name': name, 'desc': desc, 'repo': repo})

    def handle_input(self, key):
        if self.ui.is_loading:
            return # Bloqueia input durante instalação

        # Normaliza key code
        key_code = key if isinstance(key, int) else ord(key)

        # Modo de Confirmação de Deleção
        if self.confirm_delete_plugin:
            if key_code in (ord('y'), ord('Y')):
                success, msg = self.installer.delete_plugin(self.confirm_delete_plugin)
                self.ui.status_msg = msg
                self.refresh_plugins_list()
                self.selected_idx = min(self.selected_idx, max(0, len(self.plugins) - 1))
                self.confirm_delete_plugin = None
            elif key_code in (ord('n'), ord('N'), 27):
                self.confirm_delete_plugin = None
                self.ui.status_msg = "Deleção cancelada."
            return

        if key_code == 27: # Esc
            self.active = False
        
        elif key_code == 9: # Tab
            self.focus = 'list' if self.focus == 'input' else 'input'

        elif key_code == curses.KEY_UP:
            if self.focus == 'list':
                self.selected_idx = max(0, self.selected_idx - 1)
        
        elif key_code == curses.KEY_DOWN:
            if self.focus == 'list':
                self.selected_idx = min(len(self.plugins) - 1, self.selected_idx + 1)

        elif key_code in (ord('g'), ord('G')) and self.focus == 'list':
            if self.plugins:
                plugin_data = self.plugins[self.selected_idx]
                repo_link = plugin_data.get('repo')
                if repo_link:
                    self.ui.status_msg = f"Abrindo: {repo_link}"
                    # Abre em thread para não travar a UI
                    threading.Thread(target=lambda: webbrowser.open(repo_link)).start()
                else:
                    self.ui.status_msg = "Link do repositório não disponível."

        elif key_code in (ord('u'), ord('U')) and self.focus == 'list':
            if self.plugins:
                plugin_name = self.plugins[self.selected_idx]['name']
                self.ui.status_msg = f"Atualizando {plugin_name}..."
                
                def target():
                    success, msg = self.installer.update_plugin(plugin_name)
                    self.ui.status_msg = msg
                
                threading.Thread(target=target).start()

        elif key_code in (curses.KEY_DC, 330): # Delete Key
            if self.focus == 'list' and self.plugins:
                self.confirm_delete_plugin = self.plugins[self.selected_idx]['name']

        elif key_code in (10, 13): # Enter
            if self.focus == 'input' and self.ui.input_buffer:
                self.start_install(self.ui.input_buffer.strip())
            elif self.focus == 'list':
                pass # Futuro: Abrir detalhes do plugin?
        
        elif key_code in (curses.KEY_BACKSPACE, 127, 8):
            if self.focus == 'input':
                self.ui.input_buffer = self.ui.input_buffer[:-1]
            
        elif isinstance(key, str) and key.isprintable():
            if self.focus == 'input':
                self.ui.input_buffer += key
        
        # Suporte a Ctrl+V (Paste) se o terminal enviar bytes padrão (ASCII 22)
        elif key_code == 22:
            try:
                # Tenta pegar do clipboard (depende do editor ter exposto isso ou usar subprocess)
                # Como fallback simples, não implementado aqui sem acesso direto ao clipboard do OS
                pass 
            except: pass

    def start_install(self, url):
        self.ui.is_loading = True
        self.ui.progress_percent = 0
        self.ui.raw_progress_buffer = ""
        self.ui.status_msg = "Clonando repositório... aguarde."
        
        def on_progress(char):
            # Acumula caracteres e tenta extrair porcentagem
            self.ui.raw_progress_buffer += char
            if char in ('\r', '\n'):
                line = self.ui.raw_progress_buffer.strip()
                self.ui.raw_progress_buffer = ""
                if line:
                    self.ui.status_msg = line
                    # Regex para capturar porcentagem do git (ex: 15%)
                    match = re.search(r'(\d+)%', line)
                    if match:
                        try: self.ui.progress_percent = int(match.group(1))
                        except: pass

        def target():
            success, msg = self.installer.install_from_github(url, on_progress=on_progress)
            self.ui.status_msg = msg
            self.ui.is_loading = False
            if success:
                self.ui.input_buffer = "" # Limpa após sucesso
                self.refresh_plugins_list() # Atualiza lista
        
        threading.Thread(target=target).start()

# Instância e função de registro padrão
plugin = TasmaStorePlugin()

def register(context):
    plugin.register(context)