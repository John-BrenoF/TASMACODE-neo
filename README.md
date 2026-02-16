<img width="500" height="500" alt="buo-removebg-preview" src="https://github.com/user-attachments/assets/bf8e1f3b-77b1-4e1e-8d37-ad0e471145cc" />

# Tasma Code Editor


O Tasma Code Editor é um editor de texto robusto baseado em terminal (TUI), desenvolvido em Python utilizando a biblioteca `curses`. Ele combina a leveza de editores de console com funcionalidades modernas de IDEs.

## Como Funciona

O sistema opera através de um loop principal (`main.py`) que orquestra a interação entre os componentes:

1.  **Gerenciamento de Estado**: O `TabManager` controla os buffers de arquivos abertos, enquanto a classe `Editor` lida com a manipulação de texto, cursor e histórico de desfazer/refazer.
2.  **Interface (UI)**: A classe `UI` é responsável por desenhar o estado atual no terminal, gerenciando janelas, cores (syntax highlighting), a barra lateral de arquivos e a disposição em abas ou divisão de tela (split view).
3.  **Event Loop**: O editor captura entradas de teclado e mouse em tempo real, despachando comandos para o componente ativo (seja o editor de texto, a árvore de arquivos ou um plugin).

## Sistema de Plugins Independentes

O Tasma possui uma arquitetura modular que permite estender suas funcionalidades sem alterar o código-fonte principal. O sistema de plugins é projetado para ser **independente e desacoplado**.

### Arquitetura

*   **Descoberta Automática**: O `PluginManager` escaneia o diretório `plugins/` na inicialização. Qualquer pasta ou arquivo Python válido é tratado como um plugin potencial.
*   **Injeção de Contexto**: O contrato principal é a função `register(context)`. O editor injeta um dicionário `context` contendo referências vivas para os subsistemas vitais:
    *   `ui`: Permite desenhar na tela, criar popups ou registrar painéis laterais (como visto no plugin de Chat IA).
    *   `tab_manager`: Permite abrir, fechar ou manipular arquivos programaticamente.
    *   `global_commands`: Permite que plugins registrem novos atalhos de teclado globais.
    *   `config`: Acesso às configurações do usuário.

### Flexibilidade

Graças a esse design, plugins podem variar desde simples utilitários (como colorizadores de barra de status) até sistemas complexos que rodam em threads separadas (como o `Tasmalive` server) ou modificam o comportamento de renderização do editor (como a tela de boas-vindas `welcome-tasma`).

## Funcionalidades Principais

*   **Edição**: Syntax highlighting, autocomplete, macros e múltiplos cursores.
*   **Navegação**: Fuzzy finder, árvore de arquivos e abas.
*   **Visualização**: Suporte a Split Vertical e Horizontal.
*   **Ferramentas**: Linter integrado e terminal embutido (via plugins).

# testes 
---

## testes no ubuntu- gnometerminal 

https://github.com/user-attachments/assets/edf08a34-43d9-4dcf-a4c2-5aa24bc3e20c

##  testes no KDE-plamas - Konsole 

https://github.com/user-attachments/assets/8038a951-90a4-478d-9ab8-a7ef99f0c124

---
