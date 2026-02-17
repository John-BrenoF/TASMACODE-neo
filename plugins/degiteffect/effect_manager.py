import time

class EffectManager:
    """
    Responsável por armazenar e gerenciar o ciclo de vida dos efeitos visuais.
    Não depende de curses ou da UI.
    """
    def __init__(self):
        # Lista de dicionários: {'editor': ref, 'y': int, 'x': int, 'char': str, 'start_time': float}
        self.effects = []
        self.duration = 0.8 # Duração do efeito em segundos

    def add_effect(self, editor, y, x, char):
        """Registra um novo efeito na posição especificada."""
        self.effects.append({
            'editor': editor,
            'y': y,
            'x': x,
            'char': char,
            'start_time': time.time()
        })

    def get_active_effects(self, editor):
        """Retorna efeitos ativos para um editor específico e limpa os expirados."""
        now = time.time()
        # Remove efeitos expirados
        self.effects = [e for e in self.effects if now - e['start_time'] < self.duration]
        # Retorna apenas os que pertencem ao editor solicitado
        return [e for e in self.effects if e['editor'] == editor]