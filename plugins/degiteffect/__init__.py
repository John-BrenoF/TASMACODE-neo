import sys
import os
import curses
import time

# Adiciona diretório atual ao path para importar módulos locais
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from effect_manager import EffectManager

class DigitEffectPlugin:
    def __init__(self):
        self.manager = EffectManager()
        self.ui = None
        self.original_insert_char = None
        self.original_draw_editor_pane = None

    def register(self, context):
        self.ui = context.get('ui')
        
        # Tenta localizar a classe Editor para fazer o hook (Monkey Patch)
        # O editor geralmente está carregado em sys.modules['editor'] ou 'src.editor'
        EditorClass = None
        if 'editor' in sys.modules:
            EditorClass = sys.modules['editor'].Editor
        elif 'src.editor' in sys.modules:
            EditorClass = sys.modules['src.editor'].Editor
        
        if EditorClass:
            # Hook no método insert_char para detectar digitação
            self.original_insert_char = EditorClass.insert_char
            
            def wrapper(editor_instance, char, auto_close=False):
                return self.hooked_insert_char(editor_instance, char, auto_close)
            EditorClass.insert_char = wrapper

        if self.ui:
            # Hook no método de desenho do painel do editor para renderizar o efeito
            self.original_draw_editor_pane = self.ui._draw_editor_pane
            self.ui._draw_editor_pane = self.hooked_draw_editor_pane

    def hooked_insert_char(self, editor_instance, char, auto_close=False):
        """Intercepta a digitação para registrar o efeito."""
        # Executa o método original primeiro
        if self.original_insert_char:
            self.original_insert_char(editor_instance, char, auto_close)
        
        # Registra o efeito na posição onde o caractere foi inserido.
        # Nota: insert_char avança o cursor (cx), então o char está em cx - 1
        self.manager.add_effect(editor_instance, editor_instance.cy, editor_instance.cx - 1, char)
        
        # Força atualização rápida da UI para animação fluida
        if self.ui:
            self.ui.stdscr.timeout(50)

    def hooked_draw_editor_pane(self, editor, rect, filepath, is_active):
        """Intercepta o desenho para sobrepor os efeitos visuais."""
        # Desenha o editor normalmente primeiro
        if self.original_draw_editor_pane:
            self.original_draw_editor_pane(editor, rect, filepath, is_active)
        
        # Obtém efeitos ativos
        effects = self.manager.get_active_effects(editor)
        if not effects:
            return

        y, x, h, w = rect
        visual_indices = editor.get_visual_indices()
        
        # Calcula geometria para renderizar os efeitos na posição correta da tela
        line_count = len(editor.lines)
        line_num_width = len(str(line_count))
        gutter_width = line_num_width + 3
        total_left_margin = x + gutter_width
        
        now = time.time()
        
        for effect in effects:
            eff_y = effect['y']
            eff_x = effect['x']
            char = effect['char']
            
            # Verifica se a linha do efeito está visível
            if eff_y not in visual_indices:
                continue
                
            vis_idx = visual_indices.index(eff_y)
            screen_row = vis_idx - editor.scroll_offset_y
            
            # Verifica se está dentro da área visível verticalmente
            if 0 <= screen_row < h:
                screen_y = y + screen_row
                screen_x = eff_x - editor.scroll_offset_x + total_left_margin
                
                # Verifica limites horizontais
                if total_left_margin <= screen_x < x + w:
                    # Calcula intensidade do brilho baseado no tempo
                    elapsed = now - effect['start_time']
                    progress = elapsed / self.manager.duration
                    
                    # Define estilo do brilho (Flash -> Bold -> Fade)
                    attr = curses.A_NORMAL
                    if progress < 0.2:
                        attr = curses.A_REVERSE | curses.A_BOLD # Flash inicial forte
                    elif progress < 0.5:
                        attr = curses.A_BOLD | curses.color_pair(1) # Brilho colorido
                    else:
                        attr = curses.A_BOLD # Fade out
                    
                    try:
                        self.ui.stdscr.addstr(screen_y, screen_x, char, attr)
                    except curses.error: pass
        
        # Mantém o loop de eventos rápido enquanto houver animações
        self.ui.stdscr.timeout(50)

plugin = DigitEffectPlugin()
def register(context):
    plugin.register(context)