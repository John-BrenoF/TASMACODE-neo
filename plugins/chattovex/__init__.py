# /home/johnb/tasma-code-absulut/plugins/chattovex/__init__.py
import curses
import threading
import sys
import os
import re
import json
import subprocess
import difflib

# Adiciona o diretório atual ao path para permitir importações locais
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from api_client import GroqClient
from chat_ui import ChatUI

class AIChatPlugin:
    def __init__(self):
        self.is_visible = False
        self.name = "Chattovex"
        self.config_file = os.path.join(current_dir, "config.json")
        self.config = self.load_config()
        self.api_key = self.config.get("api_key", "")
        self.client = GroqClient(self.api_key)
        self.ui_component = ChatUI()
        self.context = None
        self.is_processing = False
        self.temperature = 0.7
        self.send_context = True
        self.custom_system_prompt = None
        self.history_file = os.path.join(current_dir, "chat_history.json")
        
        # Configura callback e carrega histórico
        self.ui_component.on_message_added = self.save_chat_history_internal
        self.load_chat_history()
        self.personas_file = os.path.join(current_dir, "personas.json")
        self.personas = self.load_personas()
        
        # Estado do Menu Ctrl+M
        self.menu_active = False
        self.menu_index = 0
        self.menu_options = [
            ("Enviar Mensagem", "send"),
            ("Aplicar Código", "/apply"),
            ("Ver Diferenças", "/diff"),
            ("Copiar Resposta", "/copy"),
            ("Limpar Chat", "/reset"),
            ("Personas", "/persona"),
            ("Config API Key", "/apikey"),
            ("Modelo IA", "/model"),
            ("Alternar Contexto", "/context"),
            ("Salvar Chat", "/save"),
            ("Exportar Código", "/export"),
            ("Listar Arquivos", "/files"),
            ("Ler Arquivo", "/read"),
            ("Executar Shell", "/exec"),
            ("Cancelar", "cancel")
        ]

    def register(self, context):
        """Registra o plugin na UI e guarda referência ao contexto (editor, etc)."""
        self.context = context
        self.ui = context.get('ui')
        if self.ui:
            self.ui.right_sidebar_plugin = self

    def load_config(self):
        config = {"api_key": ""}
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config.update(json.load(f))
            except: pass
        return config

    def save_config(self):
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=4)
        except: pass

    def load_personas(self):
        defaults = {
            "default": "Você é um assistente de codificação integrado ao editor Tasma.",
            "expert": "Você é um especialista em Python e arquitetura de software. Seja técnico, preciso e prefira código limpo.",
            "teacher": "Explique detalhadamente os conceitos utilizados no código, agindo como um professor."
        }
        if os.path.exists(self.personas_file):
            try:
                with open(self.personas_file, 'r') as f:
                    saved = json.load(f)
                    defaults.update(saved)
            except: pass
        return defaults

    def save_personas(self):
        try:
            with open(self.personas_file, 'w') as f:
                json.dump(self.personas, f)
        except: pass

    def load_chat_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r') as f:
                    data = json.load(f)
                    self.ui_component.history = [(item['role'], item['content']) for item in data]
                    self.ui_component.scroll_offset = 0
            except: pass

    def save_chat_history_internal(self):
        data = [{"role": r, "content": c} for r, c in self.ui_component.history]
        try:
            with open(self.history_file, 'w') as f:
                json.dump(data, f)
        except: pass

    def draw(self, stdscr, x, y, h, w):
        """Delega o desenho para o componente de UI."""
        self.ui_component.draw(stdscr, x, y, h, w, self.is_visible, self.is_processing)
        if self.menu_active:
            self.ui_component.draw_menu(stdscr, x, y, h, w, self.menu_options, self.menu_index)

    def handle_input(self, key):
        """Processa entrada quando a sidebar está focada."""
        if self.menu_active:
            self.handle_menu_input(key)
            return

        if key == 12: # Ctrl+L - Abre Menu
            self.menu_active = True
            self.menu_index = 0
            return

        if key in (10, 13): # Enter (13), Ctrl+J (10)
            message = self.ui_component.input_buffer.strip()
            if message:
                # Se houver texto, envia a mensagem
                self.ui_component.input_buffer = ""
                self.ui_component.add_message("user", message)
                self.process_command(message)
        elif key == 263 or key == 127 or key == 8: # Backspace
            self.ui_component.input_buffer = self.ui_component.input_buffer[:-1]
        elif isinstance(key, int) and 32 <= key <= 126:
            self.ui_component.input_buffer += chr(key)
        elif key == curses.KEY_PPAGE: # PageUp
            self.ui_component.scroll_up()
        elif key == curses.KEY_NPAGE: # PageDown
            self.ui_component.scroll_down()
        elif isinstance(key, str) and len(key) == 1:
             self.ui_component.input_buffer += key

    def handle_menu_input(self, key):
        if key == curses.KEY_UP:
            self.menu_index = (self.menu_index - 1) % len(self.menu_options)
        elif key == curses.KEY_DOWN:
            self.menu_index = (self.menu_index + 1) % len(self.menu_options)
        elif key in (10, 13): # Enter para selecionar
            action = self.menu_options[self.menu_index][1]
            self.execute_menu_action(action)
            self.menu_active = False
        elif key == 27: # Esc para sair
            self.menu_active = False

    def execute_menu_action(self, action):
        if action == "send":
            message = self.ui_component.input_buffer.strip()
            if message:
                self.ui_component.input_buffer = ""
                self.ui_component.add_message("user", message)
                self.process_command(message)
        elif action == "cancel":
            pass
        elif action.startswith("/"):
            # Comandos que precisam de argumentos apenas preenchem o input
            if action in ["/files", "/read", "/exec", "/apikey", "/persona", "/save", "/export", "/model", "/temp", "/system"]:
                self.ui_component.input_buffer = action + " "
            else:
                # Comandos diretos executam imediatamente
                self.process_command(action)

    def process_command(self, user_input):
        """Envia contexto do editor e input do usuário para a IA."""
        # Comandos locais
        if user_input.startswith('/'):
            cmd = user_input.split()[0].lower()
            if cmd in ('/clear', '/reset'):
                self.ui_component.history = []
                self.ui_component.scroll_offset = 0
                self.ui_component.add_message("system", "Chat limpo.")
            elif cmd == '/apply':
                # /apply [index] [all]
                args = user_input.split()
                mode = 'auto'
                index = -1 # Último por padrão
                
                if len(args) > 1:
                    if args[1] == 'all': mode = 'all'
                    elif args[1].isdigit(): index = int(args[1]) - 1
                
                self.apply_code_block(index, mode)
            elif cmd == '/copy':
                self.copy_last_message()
            elif cmd == '/help':
                help_text = "Comandos:\n/apikey - Config Key\n/persona - Personas\n/apply - Aplicar\n/copy - Copiar\n/reset - Reiniciar\n/files - Listar"
                self.ui_component.add_message("system", help_text)
            elif cmd == '/files':
                self.list_files(user_input)
            elif cmd == '/read':
                self.read_file_content(user_input)
                return
            elif cmd == '/exec':
                self.exec_shell_cmd(user_input)
                return
            elif cmd == '/save':
                filename = user_input.split(' ', 1)[1] if ' ' in user_input else "chat_log.txt"
                self.save_history(filename)
            elif cmd == '/model':
                if ' ' in user_input:
                    self.client.model = user_input.split(' ', 1)[1].strip()
                    self.ui_component.add_message("system", f"Modelo alterado para: {self.client.model}")
                else:
                    self.ui_component.add_message("system", f"Modelo atual: {self.client.model}")
            elif cmd == '/temp':
                try:
                    val = float(user_input.split(' ', 1)[1])
                    self.temperature = max(0.0, min(2.0, val))
                    self.ui_component.add_message("system", f"Temperatura ajustada: {self.temperature}")
                except:
                    self.ui_component.add_message("system", "Uso: /temp 0.7")
            elif cmd == '/context':
                self.send_context = not self.send_context
                status = "LIGADO" if self.send_context else "DESLIGADO"
                self.ui_component.add_message("system", f"Envio de contexto: {status}")
            elif cmd == '/undo':
                if len(self.ui_component.history) >= 2:
                    # Remove User e AI (últimos 2)
                    self.ui_component.history.pop()
                    self.ui_component.history.pop()
                    self.ui_component.scroll_offset = 0
                    self.ui_component.add_message("system", "Última interação desfeita.")
                else:
                    self.ui_component.add_message("system", "Histórico insuficiente para desfazer.")
            elif cmd == '/tokens':
                # Estimativa grosseira: 1 token ~= 4 chars
                total_chars = sum(len(t) for r, t in self.ui_component.history)
                est_tokens = total_chars // 4
                self.ui_component.add_message("system", f"Tokens estimados no histórico: ~{est_tokens}")
            elif cmd == '/system':
                if ' ' in user_input:
                    self.custom_system_prompt = user_input.split(' ', 1)[1]
                    self.ui_component.add_message("system", "Prompt de sistema atualizado.")
                else:
                    self.custom_system_prompt = None
                    self.ui_component.add_message("system", "Prompt de sistema resetado.")
            elif cmd == '/export':
                filename = user_input.split(' ', 1)[1] if ' ' in user_input else "exported_code.txt"
                self.export_code_blocks(filename)
            elif cmd == '/stats':
                stats = (f"Modelo: {self.client.model}\n"
                         f"Temp: {self.temperature}\n"
                         f"Contexto: {'ON' if self.send_context else 'OFF'}")
                self.ui_component.add_message("system", stats)
            elif cmd == '/insert':
                # Força inserção no cursor (bypass smart replace)
                self.apply_code_block(mode='insert')
            elif cmd == '/apikey':
                if len(user_input.split()) > 1:
                    key = user_input.split(' ', 1)[1].strip()
                    self.api_key = key
                    self.config['api_key'] = key
                    self.client.api_key = key
                    self.save_config()
                    self.ui_component.add_message("system", "API Key salva com sucesso.")
                else:
                    self.ui_component.add_message("system", "Uso: /apikey <sua_chave>")
            elif cmd == '/persona':
                self.manage_persona(user_input)
            else:
                self.ui_component.add_message("system", f"Comando desconhecido: {cmd}")
            return

        if self.is_processing: return
        
        editor = self.get_active_editor()
        if not editor:
            self.ui_component.add_message("system", "Nenhum editor ativo.")
            return

        # Captura o código atual
        # Truncamento para evitar erro de Rate Limit (TPM)
        # Limita o contexto a cerca de 150 linhas ao redor do cursor
        limit_lines = 150
        total_lines = len(editor.lines)
        code_context = ""
        
        if self.send_context:
            if total_lines > limit_lines:
                start = max(0, editor.cy - (limit_lines // 2))
                end = min(total_lines, start + limit_lines)
                if end - start < limit_lines: start = max(0, end - limit_lines)
                code_context = f"# ... (Truncado: linhas {start+1}-{end} de {total_lines}) ...\n" + "\n".join(editor.lines[start:end]) + "\n# ..."
            else:
                code_context = "\n".join(editor.lines)
            
        cursor_info = f"Cursor na linha {editor.cy + 1}, coluna {editor.cx + 1}."
        
        system_prompt = (
            "Você é um assistente de codificação integrado ao editor Tasma.\n"
            "Você tem acesso ao código atual do usuário.\n"
            "Responda com blocos de código Markdown (```) para que possam ser aplicados.\n"
            "Se o usuário pedir uma alteração, forneça APENAS o código novo ou instruções claras.\n"
            "Se for uma pergunta geral, responda concisamente.\n"
        )
        
        if self.custom_system_prompt:
            system_prompt = self.custom_system_prompt

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": (f"Código Atual:\n```\n{code_context}\n```\n\n{cursor_info}\n\n" if self.send_context else "") + f"Pedido: {user_input}"}
        ]

        self.is_processing = True
        
        # Thread para não travar a UI
        threading.Thread(target=self._api_call, args=(messages,)).start()

    def _api_call(self, messages):
        response = self.client.send_message(messages, temperature=self.temperature)
        self.ui_component.add_message("assistant", response)
        self.is_processing = False
        # Força refresh da UI se possível (no loop principal isso acontece naturalmente)

    def manage_persona(self, user_input):
        args = user_input.split()
        if len(args) < 2:
            self.ui_component.add_message("system", "Uso: /persona [list|load|save|delete] [nome]")
            return
        
        action = args[1]
        
        if action == 'list':
            msg = "Personas disponíveis:\n" + "\n".join(f"- {k}" for k in self.personas.keys())
            self.ui_component.add_message("system", msg)
            
        elif action == 'load':
            if len(args) < 3:
                self.ui_component.add_message("system", "Nome da persona necessário.")
                return
            name = args[2]
            if name in self.personas:
                self.custom_system_prompt = self.personas[name]
                self.ui_component.add_message("system", f"Persona '{name}' carregada.")
            else:
                self.ui_component.add_message("system", "Persona não encontrada.")
                
        elif action == 'save':
            if len(args) < 3:
                self.ui_component.add_message("system", "Nome para salvar necessário.")
                return
            name = args[2]
            if self.custom_system_prompt:
                self.personas[name] = self.custom_system_prompt
                self.save_personas()
                self.ui_component.add_message("system", f"Persona '{name}' salva.")
            else:
                self.ui_component.add_message("system", "Nenhum prompt customizado ativo para salvar.")

        elif action == 'delete':
            if len(args) < 3: return
            name = args[2]
            if name in self.personas:
                del self.personas[name]
                self.save_personas()
                self.ui_component.add_message("system", f"Persona '{name}' removida.")

    def apply_code_block(self, index=-1, mode='auto', filename=None):
        """Aplica um bloco de código da IA no editor com lógica inteligente."""
        last_msg = None
        for role, text in reversed(self.ui_component.history):
            if role == 'assistant':
                last_msg = text
                break
        
        if not last_msg:
            self.ui_component.add_message("system", "Nenhuma resposta da IA encontrada.")
            return

        code_blocks = re.findall(r'```(?:\w+)?\n(.*?)```', last_msg, re.DOTALL)
        if not code_blocks:
            self.ui_component.add_message("system", "Nenhum bloco de código encontrado.")
            return

        # Seleciona o bloco correto
        try:
            code = code_blocks[index]
        except IndexError:
            self.ui_component.add_message("system", f"Bloco {index+1} não existe.")
            return

        editor = self.get_active_editor()
        if not editor: return

        # Modo: Novo Arquivo
        if mode == 'new' and filename:
            try:
                # Resolve caminho
                if not os.path.isabs(filename):
                     if self.context and 'tab_manager' in self.context:
                        curr = self.context['tab_manager'].get_current_filepath()
                        if curr:
                            filename = os.path.join(os.path.dirname(curr), filename)
                
                # Usa tab manager para abrir (cria buffer)
                if self.context and 'tab_manager' in self.context:
                    new_editor = self.context['tab_manager'].open_file(filename)
                    new_editor.lines = code.split('\n')
                    new_editor.is_modified = True
                    self.ui_component.add_message("system", f"Arquivo criado/atualizado: {filename}")
            except Exception as e:
                self.ui_component.add_message("system", f"Erro ao criar arquivo: {e}")
            return

        # Modo: Substituir tudo
        if mode == 'all':
            editor.select_all()
            editor.clipboard = code
            editor.paste()
            self.ui_component.add_message("system", "Arquivo substituído completamente.")
            return

        # Se houver seleção manual, substitui a seleção (comportamento padrão do paste)
        if editor.has_selection() or mode == 'insert':
            editor.clipboard = code
            editor.paste()
            self.ui_component.add_message("system", "Código inserido/colado.")
            return

        # Smart Replace: Tenta encontrar função/classe para substituir
        # Procura por 'def nome' ou 'class nome' no início do bloco
        match = re.search(r'^\s*(?:async\s+)?(?:def|class)\s+([a-zA-Z_]\w*)', code, re.MULTILINE)
        if match:
            name = match.group(1)
            loc = editor.find_definition(name)
            if loc:
                start_y = loc[0]
                # Usa a lógica de dobra para encontrar o fim do bloco existente
                end_y = editor._get_fold_end(start_y)
                
                # Lógica de Indentação Automática
                target_indent = editor._get_indent_level(start_y)
                lines = code.split('\n')
                # Detecta indentação base do bloco colado (assumindo 1ª linha como base)
                source_indent = len(lines[0]) - len(lines[0].lstrip()) if lines else 0
                
                adjusted_lines = []
                for line in lines:
                    if not line.strip():
                        adjusted_lines.append("")
                        continue
                    curr_indent = len(line) - len(line.lstrip())
                    # Mantém a indentação relativa
                    new_indent = target_indent + (curr_indent - source_indent)
                    adjusted_lines.append(" " * max(0, new_indent) + line.lstrip())

                # Prepara para substituição
                editor._save_state()
                del editor.lines[start_y:end_y+1] # Remove linhas antigas
                
                for i, line in enumerate(adjusted_lines):
                    editor.lines.insert(start_y + i, line)
                
                editor.is_modified = True
                editor.cy = start_y # Move cursor para o início da alteração
                self.ui_component.add_message("system", f"Definição de '{name}' atualizada.")
                return

        # Fallback: Insere no cursor se não encontrou definição para substituir
        editor.clipboard = code
        editor.paste()
        self.ui_component.add_message("system", "Código inserido no cursor (Smart Replace não aplicável).")

    def show_diff(self, index=-1):
        """Mostra o diff entre o código atual e a sugestão da IA."""
        last_msg = None
        for role, text in reversed(self.ui_component.history):
            if role == 'assistant':
                last_msg = text
                break
        
        if not last_msg: return
        code_blocks = re.findall(r'```(?:\w+)?\n(.*?)```', last_msg, re.DOTALL)
        if not code_blocks: return
        try: code = code_blocks[index]
        except: return

        editor = self.get_active_editor()
        if not editor: return

        # Tenta encontrar o alvo do Smart Replace
        match = re.search(r'^\s*(?:async\s+)?(?:def|class)\s+([a-zA-Z_]\w*)', code, re.MULTILINE)
        if match:
            name = match.group(1)
            loc = editor.find_definition(name)
            if loc:
                start_y = loc[0]
                end_y = editor._get_fold_end(start_y)
                target_lines = editor.lines[start_y:end_y+1]
                
                # Ajusta indentação da sugestão para comparação justa
                target_indent = editor._get_indent_level(start_y)
                lines = code.split('\n')
                source_indent = len(lines[0]) - len(lines[0].lstrip()) if lines else 0
                adjusted_lines = []
                for line in lines:
                    if not line.strip(): adjusted_lines.append("")
                    else:
                        curr = len(line) - len(line.lstrip())
                        new_indent = target_indent + (curr - source_indent)
                        adjusted_lines.append(" " * max(0, new_indent) + line.lstrip())

                diff = difflib.unified_diff(
                    target_lines, adjusted_lines, 
                    fromfile=f"Atual ({name})", tofile=f"Sugestão ({name})", lineterm=""
                )
                diff_text = "\n".join(diff)
                self.ui_component.add_message("system", f"Diff:\n```diff\n{diff_text}\n```")
                return
        
        self.ui_component.add_message("system", "Diff: Smart Replace não detectou alvo. O código seria inserido.")

    def copy_last_message(self):
        """Copia a última mensagem da IA para o clipboard do sistema."""
        for role, text in reversed(self.ui_component.history):
            if role == 'assistant':
                editor = self.get_active_editor()
                if editor:
                    editor._copy_to_system_clipboard(text)
                    self.ui_component.add_message("system", "Resposta copiada.")
                return
        self.ui_component.add_message("system", "Nada para copiar.")

    def list_files(self, user_input):
        """Lista arquivos do diretório atual ou do caminho especificado."""
        args = user_input.split(' ', 1)
        path = args[1] if len(args) > 1 else None
        
        if not path:
            # Tenta pegar do arquivo atual
            if self.context and 'tab_manager' in self.context:
                current_filepath = self.context['tab_manager'].get_current_filepath()
                if current_filepath:
                    path = os.path.dirname(current_filepath)
        
        if not path:
            path = "."
            
        if self.context and 'file_handler' in self.context:
            files = self.context['file_handler'].list_directory(path)
            if not files:
                self.ui_component.add_message("system", f"Nenhum arquivo encontrado em: {path}")
                return

            output = [f"Arquivos em: {path}"]
            for name, is_dir in files[:20]: # Limita a 20 itens
                prefix = "[DIR] " if is_dir else "      "
                output.append(f"{prefix}{name}")
            if len(files) > 20:
                output.append(f"... e mais {len(files) - 20} itens.")
            self.ui_component.add_message("system", "\n".join(output))

    def read_file_content(self, user_input):
        """Lê arquivo e envia para a IA."""
        args = user_input.split(' ', 1)
        if len(args) < 2:
            self.ui_component.add_message("system", "Uso: /read [arquivo]")
            return
        
        filename = args[1].strip()
        path = filename
        
        # Resolve caminho relativo
        if not os.path.isabs(path):
            if self.context and 'tab_manager' in self.context:
                current_filepath = self.context['tab_manager'].get_current_filepath()
                if current_filepath:
                    path = os.path.join(os.path.dirname(current_filepath), filename)
        
        if not os.path.exists(path):
            self.ui_component.add_message("system", f"Arquivo não encontrado: {path}")
            return

        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            
            self.ui_component.add_message("user", f"/read {filename}")
            self.ui_component.add_message("system", f"Lendo '{filename}' ({len(content)} chars)...")
            
            # Prepara contexto
            editor = self.get_active_editor()
            code_context = ""
            if self.send_context and editor:
                # Contexto do editor (truncado)
                limit_lines = 100
                if len(editor.lines) > limit_lines:
                    code_context = f"# Contexto Editor (Truncado):\n" + "\n".join(editor.lines[:limit_lines]) + "\n...\n\n"
                else:
                    code_context = f"# Contexto Editor:\n" + "\n".join(editor.lines) + "\n\n"

            prompt = f"Conteúdo do arquivo '{filename}':\n```\n{content}\n```\n\nAnalise este arquivo."
            final_content = f"{code_context}{prompt}"
            
            messages = [
                {"role": "system", "content": self.custom_system_prompt or "Você é um assistente de codificação."},
                {"role": "user", "content": final_content}
            ]
            
            self.is_processing = True
            threading.Thread(target=self._api_call, args=(messages,)).start()

        except Exception as e:
            self.ui_component.add_message("system", f"Erro: {e}")

    def exec_shell_cmd(self, user_input):
        """Executa comando shell."""
        cmd = user_input.split(' ', 1)[1] if ' ' in user_input else ""
        if not cmd: return
        
        self.ui_component.add_message("user", f"/exec {cmd}")
        self.ui_component.add_message("system", "Executando...")
        
        def run():
            try:
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
                out = (res.stdout + res.stderr).strip() or "[Sem saída]"
                self.ui_component.add_message("system", f"Saída:\n```\n{out[:2000]}\n```")
            except Exception as e:
                self.ui_component.add_message("system", f"Erro: {e}")
        threading.Thread(target=run).start()

    def save_history(self, filename):
        """Salva o histórico do chat em um arquivo."""
        try:
            # Salva na raiz do projeto para facilitar
            base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            full_path = os.path.join(base_path, filename)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(f"Log de Chat - {self.name}\n{'='*30}\n\n")
                for role, text in self.ui_component.history:
                    f.write(f"[{role.upper()}]:\n{text}\n{'-'*20}\n")
            self.ui_component.add_message("system", f"Salvo em: {filename}")
        except Exception as e:
            self.ui_component.add_message("system", f"Erro ao salvar: {e}")

    def export_code_blocks(self, filename):
        """Exporta apenas os blocos de código para um arquivo."""
        try:
            base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            full_path = os.path.join(base_path, filename)
            with open(full_path, 'w', encoding='utf-8') as f:
                for role, text in self.ui_component.history:
                    if role == 'assistant':
                        blocks = re.findall(r'```(?:\w+)?\n(.*?)```', text, re.DOTALL)
                        for block in blocks:
                            f.write(block + "\n\n")
            self.ui_component.add_message("system", f"Códigos exportados para: {filename}")
        except Exception as e:
            self.ui_component.add_message("system", f"Erro ao exportar: {e}")

    def get_active_editor(self):
        if self.context and 'tab_manager' in self.context:
            return self.context['tab_manager'].get_current_editor()
        return None

# Instância global
plugin = AIChatPlugin()

def register(context):
    plugin.register(context)
