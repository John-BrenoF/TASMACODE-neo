# /home/johnb/tasma-code-absulut/src/html_exporter.py
import html
import keyword

class HtmlExporter:
    def __init__(self):
        # Compila a Regex para tokenização (prioridade importa: string/comentário primeiro)
        # Strings lidam com escapes básicos
        self.token_regex = re.compile(
            r'(?P<string>"[^"\\]*(?:\\.[^"\\]*)*"|\'[^\'\\]*(?:\\.[^\'\\]*)*\')|'
            r'(?P<comment>#.*)|'
            r'(?P<decorator>@\w+)|'
            r'(?P<keyword>\b(?:' + '|'.join(keyword.kwlist) + r')\b)|'
            r'(?P<number>\b\d+(\.\d+)?\b)|'
            r'(?P<class>\b[A-Z]\w*\b)|'
            r'(?P<operator>[+\-*/%=<>!&|^~]+)',
            re.DOTALL
        )
        
        # Estilos CSS básicos para o HTML gerado
        self.css = """
        body { background-color: #282a36; color: #f8f8f2; font-family: 'Consolas', 'Monaco', monospace; white-space: pre; margin: 0; padding: 10px; }
        .line { display: block; min-height: 1.2em; }
        .linenum { color: #6272a4; border-right: 1px solid #44475a; margin-right: 10px; padding-right: 10px; user-select: none; display: inline-block; width: 40px; text-align: right; }
        
        .keyword { color: #ff79c6; font-weight: bold; }
        .string { color: #f1fa8c; }
        .comment { color: #6272a4; font-style: italic; }
        .number { color: #bd93f9; }
        .decorator { color: #50fa7b; }
        .class { color: #8be9fd; font-style: italic; }
        .operator { color: #ff79c6; }
        """

    def export(self, lines, output_path):
        """Gera um arquivo HTML com o conteúdo fornecido."""
        html_content = ["<!DOCTYPE html>", "<html>", "<head>", "<meta charset='utf-8'>", "<style>", self.css, "</style>", "</head>", "<body>"]
        
        for i, line in enumerate(lines):
            formatted_line = self._format_line(line)
            html_content.append(f'<div class="line"><span class="linenum">{i+1}</span>{formatted_line}</div>')
            
        html_content.append("</body></html>")
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(html_content))
            return True
        except IOError:
            return False

    def _format_line(self, line):
        """Aplica syntax highlighting simples e retorna HTML."""
        if not line: return ""        
        result = []
        last_pos = 0
        
        for match in self.token_regex.finditer(line):
            # Adiciona texto não correspondido (espaços, pontuação simples)
            if match.start() > last_pos:
                result.append(html.escape(line[last_pos:match.start()])) 
            
            # Identifica o tipo de token e aplica a classe CSS
            token_type = match.lastgroup
            token_value = match.group(token_type)
            result.append(f'<span class="{token_type}">{html.escape(token_value)}</span>')
            last_pos = match.end()
        
        result.append(html.escape(line[last_pos:]))
            
        return "".join(result)
