# /home/johnb/tasma-code-absulut/src/linter.py
import threading
import subprocess
import sys
import shutil   

class Linter:
    def __init__(self):
        self.thread = None
        self.lock = threading.Lock()

    def lint(self, editor, filepath):
        """Inicia o processo de linting em background."""
        if self.thread and self.thread.is_alive():
            return # Evita sobreposição de threads

        # Captura o conteúdo no thread principal para evitar condições de corrida
        content = "\n".join(editor.lines)
        
        self.thread = threading.Thread(target=self._run_lint, args=(editor, filepath, content))
        self.thread.daemon = True
        self.thread.start()

    def _run_lint(self, editor, filepath, content):
        errors = {}
        
        # 1. Verificação de Sintaxe (Rápida, Built-in)
        try:
            compile(content, filepath if filepath else "<string>", 'exec')
        except SyntaxError as e:
            # Apenas adiciona o erro se o número da linha for válido
            if e.lineno is not None:
                lineno = e.lineno - 1 # Converte para 0-based
                errors[lineno] = [f"SyntaxError: {e.msg}"]
        except Exception:
            pass

        # 2. Flake8 (Externo) - Opcional
        # Só roda se tiver flake8 instalado e for arquivo Python
        if (not filepath or filepath.endswith('.py')) and shutil.which("flake8"):
            try:
                # Passa conteúdo via stdin
                proc = subprocess.run(
                    [sys.executable, "-m", "flake8", "-", "--format=%(row)d:%(text)s"],
                    input=content.encode('utf-8'),
                    capture_output=True,
                    timeout=3
                )
                if proc.stdout:
                    for line in proc.stdout.decode('utf-8').splitlines():
                        parts = line.split(':', 1)
                        if len(parts) == 2:
                            try:
                                lineno = int(parts[0]) - 1
                                msg = parts[1].strip()
                                if lineno not in errors: errors[lineno] = []
                                errors[lineno].append(msg)
                            except ValueError: pass
            except Exception: pass

        # Atualiza o editor (operação atômica de atribuição de dict é segura em CPython)
        editor.linter_errors = errors