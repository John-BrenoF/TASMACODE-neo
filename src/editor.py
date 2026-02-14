# /home/johnb/tasma-code-absulut/src/editor.py
import copy
import re
import subprocess
import shutil

class Editor:
    """
    Responsabilidade: Gerenciar o buffer de texto e a posição do cursor.
    Lógica pura de edição (inserir, deletar, mover).
    """
    def __init__(self, lines=None):
        self.lines = lines if lines else [""]
        self.cx = 0  # Cursor X (coluna)
        self.cy = 0  # Cursor Y (linha)
        self.is_modified = False
        self.search_query = ""
        self.search_mode = "text" # 'text' or 'regex'
        self.clipboard = ""
        self.bookmarks = set()
        self.linter_errors = {} # {line_index: [error_msg, ...]}
        self.folds = set() # Set of line indices that are folded
        self.scroll_offset_x = 0
        self.scroll_offset_y = 0

        self.selection_anchor_x = None
        self.selection_anchor_y = None

        self.undo_stack = []
        self.redo_stack = []
        self._save_state() # Save initial state
        self.dirty_lines = set()
        self.needs_full_redraw = True

    def move_cursor(self, dx, dy):
        """Move o cursor garantindo que ele fique dentro dos limites do texto."""
        # Move vertically in visual space
        visual_indices = self.get_visual_indices()
        try:
            current_visual_idx = visual_indices.index(self.cy)
        except ValueError:
            current_visual_idx = 0
            # Snap to nearest visible
            for idx, val in enumerate(visual_indices):
                if val > self.cy: break
                current_visual_idx = idx

        target_visual_idx = max(0, min(len(visual_indices) - 1, current_visual_idx + dy))
        self.cy = visual_indices[target_visual_idx]

        # Move horizontally
        self.cx += dx

        # Limites horizontais (ajusta X baseado no comprimento da linha atual)
        current_line_len = len(self.lines[self.cy])
        if self.cx < 0:
            self.cx = 0
        elif self.cx > current_line_len:
            self.cx = current_line_len

    def goto_line(self, line_number):
        """Move o cursor para a linha especificada (1-based)."""
        target_y = line_number - 1
        old_y = self.cy
        if 0 <= target_y < len(self.lines):
            self.cy = target_y
            self.cx = 0
            if old_y != self.cy:
                self.mark_dirty(old_y)
                self.mark_dirty(self.cy)
            return True
        return False

    def mark_dirty(self, y):
        """Marca uma linha específica como suja para redesenho."""
        self.dirty_lines.add(y)

    def mark_all_dirty(self):
        """Marca todo o editor para redesenho."""
        self.needs_full_redraw = True

    def clean_dirty(self):
        """Limpa o estado de sujo após o redesenho."""
        self.dirty_lines.clear()
        self.needs_full_redraw = False

    def _save_state(self):
        """Saves the current editor state to the undo stack."""
        # Only save if the current state is different from the last saved state
        if not self.undo_stack or (self.lines, self.cx, self.cy, self.bookmarks, self.folds) != self.undo_stack[-1]:
            self.undo_stack.append((copy.deepcopy(self.lines), self.cx, self.cy, copy.deepcopy(self.bookmarks), copy.deepcopy(self.folds)))
            self.redo_stack.clear() # Any new action clears the redo stack
            self.is_modified = True # Any new action means modified

            # Limit undo stack size to prevent excessive memory usage
            MAX_UNDO_STATES = 100
            if len(self.undo_stack) > MAX_UNDO_STATES:
                self.undo_stack.pop(0) # Remove the oldest state

    def _restore_state(self, state_tuple):
        """Restores the editor to a given state."""
        self.lines, self.cx, self.cy, self.bookmarks, self.folds = copy.deepcopy(state_tuple[0]), state_tuple[1], state_tuple[2], copy.deepcopy(state_tuple[3]), copy.deepcopy(state_tuple[4])
        # Determine if modified by comparing with the very first state in undo_stack
        if self.undo_stack and self.lines == self.undo_stack[0][0]:
            self.is_modified = False
        else:
            self.is_modified = True
        self.mark_all_dirty()

    def insert_char(self, char, auto_close=False):
        """Insere um caractere na posição atual."""
        if self.has_selection():
            self.delete_selected_text()
        self._save_state() # Save state before modification
        line = self.lines[self.cy]
        
        pairs = {'(': ')', '[': ']', '{': '}', '"': '"', "'": "'"}
        if auto_close and char in pairs:
            self.lines[self.cy] = line[:self.cx] + char + pairs[char] + line[self.cx:]
        else:
            self.lines[self.cy] = line[:self.cx] + char + line[self.cx:]
        self.cx += 1
        self.mark_dirty(self.cy)

    def insert_newline(self):
        """Quebra a linha atual em duas com auto-indentação."""
        if self.has_selection():
            self.delete_selected_text()
        self._save_state() # Save state before modification
        line = self.lines[self.cy]
        
        # Auto-indentation logic
        indent = ""
        for char in line:
            if char == " ":
                indent += " "
            else:
                break
        
        if line.strip().endswith(":"):
            indent += "    "

        left_part = line[:self.cx]
        right_part = line[self.cx:]
        
        self.lines[self.cy] = left_part
        self.lines.insert(self.cy + 1, indent + right_part)
        self.cy += 1 # Move cursor to new line
        self.cx = len(indent) # Move cursor to end of indentation
        self.mark_all_dirty() # Inserir linha desloca tudo abaixo

    def delete_char(self):
        """Simula o Backspace."""
        if self.has_selection():
            self.delete_selected_text()
            return

        if self.cx > 0:
            # Deletar caractere na linha atual
            line = self.lines[self.cy]
            self._save_state() # Save state before modification
            self.lines[self.cy] = line[:self.cx - 1] + line[self.cx:]
            self.cx -= 1
            self.mark_dirty(self.cy)
        elif self.cy > 0:
            # Juntar com a linha de cima
            current_line = self.lines.pop(self.cy)
            self.cy -= 1
            self.cx = len(self.lines[self.cy])
            self._save_state() # Save state before modification
            self.lines[self.cy] += current_line
            self.mark_all_dirty() # Remover linha desloca tudo

    def delete_forward(self):
        """Simula a tecla Delete (apaga à frente)."""
        if self.has_selection():
            self.delete_selected_text()
            return

        line = self.lines[self.cy]
        if self.cx < len(line):
            self._save_state()
            self.lines[self.cy] = line[:self.cx] + line[self.cx + 1:]
            self.mark_dirty(self.cy)
        elif self.cy < len(self.lines) - 1:
            self._save_state()
            next_line = self.lines.pop(self.cy + 1)
            self.lines[self.cy] += next_line
            self.mark_all_dirty()

    def find(self, query):
        """
        Encontra a próxima ocorrência de uma string de busca.
        Busca para frente a partir do caractere após o cursor e dá a volta no arquivo.
        Retorna uma tupla (y, x) ou None.
        """
        if not query:
            return None
        
        self.search_query = query
        self.search_mode = "text"

        # Itera por todas as linhas, começando pela atual, em ordem
        for i in range(len(self.lines)):
            # Calcula o índice real da linha, fazendo o wrap-around
            y = (self.cy + i) % len(self.lines)
            line = self.lines[y]
            
            # Se for a primeira linha da busca, começa após o cursor.
            # Caso contrário, começa do início da linha.
            start_x = self.cx + 1 if i == 0 else 0
            
            match_x = line.find(query, start_x)
            
            if match_x != -1:
                return (y, match_x)
                
        # Se chegamos aqui, nada foi encontrado após o cursor.
        # Agora, verificamos a parte da primeira linha que foi pulada.
        line = self.lines[self.cy]
        match_x = line.find(query, 0, self.cx + 1)
        if match_x != -1:
            return (self.cy, match_x)

        return None

    def find_regex(self, query):
        """Encontra a próxima ocorrência de um padrão regex."""
        if not query: return None
        try:
            regex = re.compile(query)
        except re.error:
            return None
        
        self.search_query = query
        self.search_mode = "regex"
        
        for i in range(len(self.lines)):
            y = (self.cy + i) % len(self.lines)
            line = self.lines[y]
            start_x = self.cx + 1 if i == 0 else 0
            
            match = regex.search(line, start_x)
            if match:
                return (y, match.start())
        
        # Wrap around
        line = self.lines[self.cy]
        match = regex.search(line, 0, self.cx + 1)
        if match:
            return (self.cy, match.start())
        return None

    def replace_all(self, find_str, replace_str):
        """Substitui todas as ocorrências de find_str por replace_str."""
        if not find_str: return 0
        
        self._save_state()
        count = 0
        for i, line in enumerate(self.lines):
            if find_str in line:
                new_line = line.replace(find_str, replace_str)
                if new_line != line:
                    self.lines[i] = new_line
                    count += line.count(find_str)
        self.mark_all_dirty()
        return count

    def replace_all_regex(self, pattern, replace_pattern):
        """Substitui todas as ocorrências de regex pattern por replace_pattern."""
        if not pattern: return 0
        try:
            regex = re.compile(pattern)
        except re.error: return -1
        
        self._save_state()
        count = 0
        for i, line in enumerate(self.lines):
            new_line, n = regex.subn(replace_pattern, line)
            if n > 0:
                self.lines[i] = new_line
                count += n
        self.mark_all_dirty()
        return count

    def _copy_to_system_clipboard(self, text):
        """Tenta copiar para o clipboard do sistema (xclip/xsel)."""
        try:
            if shutil.which("xclip"):
                p = subprocess.Popen(["xclip", "-selection", "clipboard", "-i"], stdin=subprocess.PIPE)
                p.communicate(input=text.encode('utf-8'))
            elif shutil.which("xsel"):
                p = subprocess.Popen(["xsel", "-b", "-i"], stdin=subprocess.PIPE)
                p.communicate(input=text.encode('utf-8'))
        except Exception:
            pass

    def _get_from_system_clipboard(self):
        """Tenta ler do clipboard do sistema."""
        try:
            if shutil.which("xclip"):
                return subprocess.check_output(["xclip", "-selection", "clipboard", "-o"]).decode('utf-8')
            elif shutil.which("xsel"):
                return subprocess.check_output(["xsel", "-b", "-o"]).decode('utf-8')
        except Exception:
            return ""
        return ""

    def copy(self):
        """Copia a linha atual para a área de transferência."""
        if self.has_selection():
            self.clipboard = self.get_selected_text()
            self.clear_selection()
        elif self.lines:
            self.clipboard = self.lines[self.cy]
        self._copy_to_system_clipboard(self.clipboard)

    def cut(self):
        """Corta o texto selecionado ou a linha atual para a área de transferência."""
        if not self.lines:
            return

        self._save_state()

        if self.has_selection():
            self.clipboard = self.get_selected_text()
            self.delete_selected_text()
        else:
            # No selection, cut the whole line
            self.clipboard = self.lines.pop(self.cy)
            if not self.lines:
                self.lines.append("")
            
            if self.cy >= len(self.lines):
                self.cy = len(self.lines) - 1
            
            self.cx = 0
        self.is_modified = True
        self._copy_to_system_clipboard(self.clipboard)

    def paste(self):
        """Insere o conteúdo da área de transferência na posição do cursor."""
        if self.has_selection():
            self.delete_selected_text()

        # Tenta obter do sistema primeiro
        sys_clip = self._get_from_system_clipboard()
        if sys_clip:
            self.clipboard = sys_clip

        if self.clipboard:
            self._save_state() # Save state before modification
            pasted_lines = self.clipboard.split('\n')

            if len(pasted_lines) == 1:
                # Single line paste
                line = self.lines[self.cy]
                self.lines[self.cy] = line[:self.cx] + pasted_lines[0] + line[self.cx:]
                self.cx += len(pasted_lines[0])
            else:
                # Multi-line paste
                line = self.lines[self.cy]
                after_cursor = line[self.cx:]
                
                # First line of paste
                self.lines[self.cy] = line[:self.cx] + pasted_lines[0]
                
                # Insert middle lines
                for i in range(1, len(pasted_lines) - 1):
                    self.lines.insert(self.cy + i, pasted_lines[i])
                
                # Last line of paste
                last_pasted_line = pasted_lines[-1]
                self.lines.insert(self.cy + len(pasted_lines) - 1, last_pasted_line + after_cursor)
                
                # Update cursor position
                self.cy += len(pasted_lines) - 1
                self.cx = len(last_pasted_line)
            self.mark_all_dirty()

    def select_all(self):
        """Seleciona todo o texto do buffer."""
        self.selection_anchor_y = 0
        self.selection_anchor_x = 0
        self.cy = len(self.lines) - 1
        self.cx = len(self.lines[self.cy])
        self.mark_all_dirty() # Seleção muda visual de tudo

    def duplicate_line(self):
        """Duplica a linha atual."""
        self._save_state()
        self.lines.insert(self.cy + 1, self.lines[self.cy])
        self.cy += 1
        self.mark_all_dirty()

    def delete_current_line(self):
        """Deleta a linha atual."""
        self._save_state()
        if len(self.lines) > 1:
            self.lines.pop(self.cy)
            if self.cy >= len(self.lines):
                self.cy = len(self.lines) - 1
            self.cx = min(self.cx, len(self.lines[self.cy]))
        else:
            self.lines[0] = ""
            self.cx = 0
        self.mark_all_dirty()

    def move_line_up(self):
        """Move a linha atual para cima."""
        if self.cy > 0:
            self._save_state()
            self.lines[self.cy], self.lines[self.cy - 1] = self.lines[self.cy - 1], self.lines[self.cy]
            self.cy -= 1
            self.mark_all_dirty()

    def move_line_down(self):
        """Move a linha atual para baixo."""
        if self.cy < len(self.lines) - 1:
            self._save_state()
            self.lines[self.cy], self.lines[self.cy + 1] = self.lines[self.cy + 1], self.lines[self.cy]
            self.cy += 1
            self.mark_all_dirty()

    def indent_selection(self):
        """Indenta a linha atual ou a seleção."""
        self._save_state()
        start_y, end_y = self.cy, self.cy
        if self.has_selection():
            coords = self.get_normalized_selection()
            start_y, end_y = coords[0][0], coords[1][0]
            # Se a seleção termina no início de uma linha, não indenta essa linha
            if coords[1][1] == 0 and start_y != end_y:
                end_y -= 1

        for i in range(start_y, end_y + 1):
            self.lines[i] = "    " + self.lines[i]
        
        self.cx += 4
        if self.has_selection():
            self.selection_anchor_x += 4
        self.mark_all_dirty()

    def dedent_selection(self):
        """Remove indentação da linha atual ou seleção."""
        self._save_state()
        start_y, end_y = self.cy, self.cy
        if self.has_selection():
            coords = self.get_normalized_selection()
            start_y, end_y = coords[0][0], coords[1][0]
            if coords[1][1] == 0 and start_y != end_y:
                end_y -= 1

        for i in range(start_y, end_y + 1):
            if self.lines[i].startswith("    "):
                self.lines[i] = self.lines[i][4:]
            elif self.lines[i].startswith(" ") and len(self.lines[i]) < 4:
                 self.lines[i] = self.lines[i].lstrip()
        
        self.cx = max(0, self.cx - 4)
        self.mark_all_dirty()

    def toggle_comment(self):
        """Adiciona ou remove comentário (#) nas linhas selecionadas."""
        self._save_state()
        start_y, end_y = self.cy, self.cy
        if self.has_selection():
            coords = self.get_normalized_selection()
            start_y, end_y = coords[0][0], coords[1][0]
            if coords[1][1] == 0 and start_y != end_y:
                end_y -= 1

        # Verifica se todas as linhas já estão comentadas para decidir a ação
        all_commented = True
        for i in range(start_y, end_y + 1):
            if not self.lines[i].lstrip().startswith("#"):
                all_commented = False
                break
        
        for i in range(start_y, end_y + 1):
            line = self.lines[i]
            if all_commented:
                self.lines[i] = line.replace("# ", "", 1).replace("#", "", 1)
            else:
                self.lines[i] = "# " + line
        self.mark_all_dirty()

    def start_selection(self):
        """Marca o início da seleção na posição atual do cursor."""
        self.selection_anchor_x = self.cx
        self.selection_anchor_y = self.cy
        self.mark_dirty(self.cy)

    def clear_selection(self):
        """Limpa a seleção."""
        self.selection_anchor_x = None
        self.selection_anchor_y = None
        self.mark_all_dirty() # Limpar seleção afeta visualmente várias linhas

    def has_selection(self):
        """Verifica se há texto selecionado."""
        return self.selection_anchor_x is not None

    def get_normalized_selection(self):
        """Retorna as coordenadas da seleção (start_y, start_x, end_y, end_x)."""
        if not self.has_selection():
            return None
        
        p1_y, p1_x = self.selection_anchor_y, self.selection_anchor_x
        p2_y, p2_x = self.cy, self.cx

        return tuple(sorted(((p1_y, p1_x), (p2_y, p2_x))))

    def get_selected_text(self):
        """Retorna o texto atualmente selecionado."""
        coords = self.get_normalized_selection()
        if not coords:
            return ""
        
        (start_y, start_x), (end_y, end_x) = coords
        
        if start_y == end_y:
            return self.lines[start_y][start_x:end_x]
        
        text = [self.lines[start_y][start_x:]]
        text.extend(self.lines[start_y + 1 : end_y])
        text.append(self.lines[end_y][:end_x])
        
        return "\n".join(text)

    def delete_selected_text(self):
        """Deleta o texto atualmente selecionado."""
        coords = self.get_normalized_selection()
        if not coords:
            return
        
        self._save_state()
        (start_y, start_x), (end_y, end_x) = coords

        first_line_part = self.lines[start_y][:start_x]
        last_line_part = self.lines[end_y][end_x:]

        del self.lines[start_y:end_y]
        self.lines.insert(start_y, first_line_part + last_line_part)

        self.cy, self.cx = start_y, start_x
        self.clear_selection()
        self.mark_all_dirty()

    def undo(self):
        """Undoes the last action."""
        if len(self.undo_stack) > 1: # Need at least two states to undo (current + previous)
            current_state = self.undo_stack.pop() # Remove current state
            self.redo_stack.append(current_state) # Add current state to redo stack
            self._restore_state(self.undo_stack[-1]) # Restore to the previous state
            self.mark_all_dirty()
            return True
        return False

    def redo(self):
        """Redoes the last undone action."""
        if self.redo_stack:
            state_to_redo = self.redo_stack.pop()
            self.undo_stack.append(state_to_redo) # Push the redone state back to undo stack
            self._restore_state(state_to_redo) # Restore to the redone state
            self.mark_all_dirty()
            return True
        return False

    def find_next(self):
        """
        Encontra a próxima ocorrência da última string de busca.
        Retorna uma tupla (y, x) ou None.
        """
        if not self.search_query:
            return None

        if self.search_mode == "regex":
            try:
                regex = re.compile(self.search_query)
            except re.error: return None
            
            for i in range(len(self.lines)):
                y = (self.cy + i) % len(self.lines)
                line = self.lines[y]
                start_x = self.cx + 1 if i == 0 else 0
                match = regex.search(line, start_x)
                if match: return (y, match.start())
            
            line = self.lines[self.cy]
            match = regex.search(line, 0, self.cx + 1)
            if match: return (self.cy, match.start())
            
        else:
            # Itera por todas as linhas, começando pela atual, em ordem
            for i in range(len(self.lines)):
                # Calcula o índice real da linha, fazendo o wrap-around
                y = (self.cy + i) % len(self.lines)
                line = self.lines[y]

                # Se for a primeira linha da busca, começa após o cursor.
                # Caso contrário, começa do início da linha.
                start_x = self.cx + 1 if i == 0 else 0

                match_x = line.find(self.search_query, start_x)

                if match_x != -1:
                    return (y, match_x)

            # Se chegamos aqui, nada foi encontrado após o cursor.
            # Agora, verificamos a parte da primeira linha que foi pulada.
            line = self.lines[self.cy]
            match_x = line.find(self.search_query, 0, self.cx + 1)
            if match_x != -1:
                return (self.cy, match_x)

        return None

    def go_to_start_of_line(self):
        """Smart Home: Alterna entre coluna 0 e primeiro char não-espaço."""
        line = self.lines[self.cy]
        first_non_space = 0
        for i, c in enumerate(line):
            if not c.isspace():
                first_non_space = i
                break
        
        if self.cx == first_non_space:
            self.cx = 0
        else:
            self.cx = first_non_space

    def go_to_end_of_line(self):
        self.cx = len(self.lines[self.cy])

    def go_to_start_of_file(self):
        self.cy = 0
        self.cx = 0

    def go_to_end_of_file(self):
        self.cy = len(self.lines) - 1
        self.cx = len(self.lines[self.cy])

    def move_word_right(self):
        line = self.lines[self.cy]
        if self.cx >= len(line):
            if self.cy < len(self.lines) - 1:
                self.cy += 1
                self.cx = 0
            return
        
        # Skip current word or spaces
        i = self.cx
        # If on space, skip spaces
        if i < len(line) and line[i].isspace():
            while i < len(line) and line[i].isspace(): i += 1
        # If on char, skip chars
        elif i < len(line) and not line[i].isspace():
            while i < len(line) and not line[i].isspace(): i += 1
            # Then skip subsequent spaces
            while i < len(line) and line[i].isspace(): i += 1
        self.cx = i

    def move_word_left(self):
        if self.cx == 0:
            if self.cy > 0:
                self.cy -= 1
                self.cx = len(self.lines[self.cy])
            return

        line = self.lines[self.cy]
        i = self.cx - 1
        # Skip spaces backwards
        while i >= 0 and line[i].isspace(): i -= 1
        # Skip chars backwards
        while i >= 0 and not line[i].isspace(): i -= 1
        self.cx = i + 1

    def get_word_under_cursor(self):
        """Retorna a palavra sob o cursor."""
        line = self.lines[self.cy]
        if not line or self.cx >= len(line):
            return ""
        
        if not (line[self.cx].isalnum() or line[self.cx] == '_'):
            return ""

        start = self.cx
        while start > 0 and (line[start - 1].isalnum() or line[start - 1] == '_'):
            start -= 1
        
        end = self.cx
        while end < len(line) and (line[end].isalnum() or line[end] == '_'):
            end += 1
            
        return line[start:end]

    def find_definition(self, word):
        """Procura por 'def word' ou 'class word' no arquivo."""
        if not word: return None
        
        patterns = [f"def {word}", f"class {word}"]
        for i, line in enumerate(self.lines):
            for pat in patterns:
                # Verifica se começa com o padrão (ignorando indentação)
                if line.lstrip().startswith(pat):
                    return (i, line.find(word))
        return None

    def get_matching_bracket(self):
        """Retorna (y, x) do parêntese correspondente ou None."""
        line = self.lines[self.cy]
        if self.cx >= len(line): return None
        
        char = line[self.cx]
        pairs = {'(': ')', '[': ']', '{': '}'}
        reverse_pairs = {')': '(', ']': '[', '}': '{'}
        
        if char in pairs:
            target = pairs[char]
            direction = 1
        elif char in reverse_pairs:
            target = reverse_pairs[char]
            direction = -1
        else:
            return None

        balance = 0
        curr_y, curr_x = self.cy, self.cx
        
        while 0 <= curr_y < len(self.lines):
            line_content = self.lines[curr_y]
            
            # Se for a linha inicial, começa do cursor + direção
            start_x = curr_x + direction if curr_y == self.cy else (0 if direction == 1 else len(line_content) - 1)
            
            # Range apropriado para a direção
            iter_range = range(start_x, len(line_content)) if direction == 1 else range(start_x, -1, -1)
            
            for x in iter_range:
                c = line_content[x]
                if c == char:
                    balance += 1
                elif c == target:
                    if balance == 0:
                        return (curr_y, x)
                    balance -= 1
            
            curr_y += direction
        return None

    def get_completions(self):
        """Retorna sugestões baseadas no prefixo da palavra atual."""
        line = self.lines[self.cy]
        if not line or self.cx == 0: return [], ""
        
        # Encontrar início da palavra atual
        start = self.cx
        while start > 0 and (line[start-1].isalnum() or line[start-1] == '_'):
            start -= 1
        
        prefix = line[start:self.cx]
        if not prefix or len(prefix) < 2: return [], ""
        
        # Coletar palavras de todo o buffer
        words = set()
        for l in self.lines:
            for w in re.findall(r'\w+', l):
                if w.startswith(prefix) and w != prefix:
                    words.add(w)
        
        return sorted(list(words)), prefix

    def toggle_bookmark(self):
        """Alterna um marcador na linha atual."""
        self._save_state()
        if self.cy in self.bookmarks:
            self.bookmarks.remove(self.cy)
        else:
            self.bookmarks.add(self.cy)
        self.mark_dirty(self.cy)

    def next_bookmark(self):
        """Pula para o próximo marcador."""
        if not self.bookmarks: return
        sorted_marks = sorted(list(self.bookmarks))
        for mark in sorted_marks:
            if mark > self.cy:
                self.cy = mark
                self.mark_all_dirty() # Pulo longo
                self.cx = 0
                return
        self.cy = sorted_marks[0] # Wrap around
        self.mark_all_dirty()
        self.cx = 0

    def _get_indent_level(self, line_idx):
        if line_idx >= len(self.lines): return 0
        line = self.lines[line_idx]
        return len(line) - len(line.lstrip())

    def _get_fold_end(self, start_idx):
        if start_idx >= len(self.lines): return start_idx
        start_indent = self._get_indent_level(start_idx)
        for i in range(start_idx + 1, len(self.lines)):
            if self.lines[i].strip() == "": continue
            if self._get_indent_level(i) <= start_indent:
                return i - 1
        return len(self.lines) - 1

    def get_visual_indices(self):
        """Retorna lista de índices de linhas visíveis (não dobradas)."""
        indices = []
        i = 0
        while i < len(self.lines):
            indices.append(i)
            if i in self.folds:
                end = self._get_fold_end(i)
                i = end + 1
            else:
                i += 1
        return indices

    def toggle_fold(self):
        """Alterna dobra de código na linha atual."""
        self._save_state()
        if self.cy in self.folds:
            self.folds.remove(self.cy)
        else:
            my_indent = self._get_indent_level(self.cy)
            can_fold = False
            for i in range(self.cy + 1, len(self.lines)):
                if self.lines[i].strip() != "" and self._get_indent_level(i) > my_indent:
                    can_fold = True
                    break
                if self.lines[i].strip() != "" and self._get_indent_level(i) <= my_indent:
                    break
            if can_fold:
                self.folds.add(self.cy)
        self.mark_all_dirty() # Dobra afeta layout vertical

    def prev_bookmark(self):
        """Pula para o marcador anterior."""
        if not self.bookmarks: return
        sorted_marks = sorted(list(self.bookmarks), reverse=True)
        for mark in sorted_marks:
            if mark < self.cy:
                self.cy = mark
                self.mark_all_dirty()
                self.cx = 0
                return
        self.cy = sorted_marks[0] # Wrap around
        self.mark_all_dirty()
        self.cx = 0

    def get_symbols(self):
        """Retorna uma lista de (linha, conteúdo) para definições de funções e classes."""
        symbols = []
        for i, line in enumerate(self.lines):
            stripped = line.strip()
            if stripped.startswith("def ") or stripped.startswith("class "):
                symbols.append((i, line))
        return symbols

    def get_word_before_cursor(self):
        """Retorna a palavra imediatamente antes do cursor."""
        line = self.lines[self.cy]
        if self.cx == 0: return ""
        
        start = self.cx
        while start > 0 and (line[start-1].isalnum() or line[start-1] == '_'):
            start -= 1
        
        return line[start:self.cx]

    def expand_snippet(self, snippets):
        """Expande a palavra antes do cursor se for um snippet."""
        if self.has_selection():
            return False
            
        word = self.get_word_before_cursor()
        if not word or word not in snippets:
            return False
            
        self._save_state()
        
        # Remove a palavra chave
        line = self.lines[self.cy]
        start_word_x = self.cx - len(word)
        
        snippet_text = snippets[word]
        snippet_lines = snippet_text.split('\n')
        
        # Preserva o conteúdo da linha antes e depois da palavra
        prefix = line[:start_word_x]
        suffix = line[self.cx:]
        
        # A primeira linha do snippet é anexada ao prefixo
        self.lines[self.cy] = prefix + snippet_lines[0]
        
        # Se houver mais linhas, insere elas com a indentação correta
        if len(snippet_lines) > 1:
            base_indent = ""
            for char in prefix:
                if char.isspace(): base_indent += char
                else: break
            
            for i in range(1, len(snippet_lines)):
                self.lines.insert(self.cy + i, base_indent + snippet_lines[i])
            
            self.lines[self.cy + len(snippet_lines) - 1] += suffix
            self.cy += len(snippet_lines) - 1
            self.cx = len(base_indent) + len(snippet_lines[-1])
        else:
            self.lines[self.cy] += suffix
            self.cx = len(prefix) + len(snippet_lines[0])
            
        self.is_modified = True
        self.mark_all_dirty()
        return True
