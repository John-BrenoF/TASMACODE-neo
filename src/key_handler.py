# src/key_handler.py
class KeyHandler:
    def __init__(self, config):
        self.config = config
        self.actions = {} # name -> callback
        self.key_map = {} # key_code -> action_name

    def register_action(self, name, callback, fixed_keys=None):
        """Registers an action. Maps to config key AND a list of fixed key codes."""
        self.actions[name] = callback
        key_code = self.config.get_key(name)
        
        # Mapeia a tecla vinda da configuração (config.json)
        if key_code is not None and key_code != -1:
            self.key_map[key_code] = name
        # E também mapeia uma lista de teclas fixas de fallback, se fornecida
        if fixed_keys:
            if isinstance(fixed_keys, list):
                for fk in fixed_keys:
                    self.key_map[fk] = name
            elif isinstance(fixed_keys, int): # Keep backward compatibility
                 self.key_map[fixed_keys] = name

    def handle_key(self, key_code, context):
        """
        Dispatches the key to the appropriate callback.
        Returns True if the key was handled, False otherwise.
        """
        # 1. Check global commands (plugins)
        if 'global_commands' in context and key_code in context['global_commands']:
            context['global_commands'][key_code]()
            return True

        # 2. Check registered actions
        if key_code in self.key_map:
            name = self.key_map[key_code]
            if name in self.actions:
                self.actions[name]()
                return True
        
        return False
