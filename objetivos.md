# TasmaCode Editor

Este arquivo define os **únicos três objetivos prioritários** no momento.  
Tudo o mais (autocomplete, fuzzy finder, linter, terminal embutido, múltiplos cursores etc.) fica em segundo plano até esses três estarem 100% entregues e testados.  
Foco = terminar o que é essencial para alguém usar o editor sem raiva.

Data de criação: fevereiro/2026  

## Objetivo 1: Tornar 100% compatível com GNOME Terminal

**Por quê isso é prioridade absoluta?**  
GNOME Terminal é o terminal padrão em muitas distros Linux (Ubuntu, Fedora, Pop!_OS, Mint etc.). Se não rodar bem nele, 70%+ dos usuários Linux potenciais vão desistir em 30 segundos.  
Problemas comuns em curses + GNOME Terminal:  
- Suporte a cores (256 vs truecolor)  
- Flickering / redraw lento  
- Comportamento de teclas (mouse, resize, Ctrl+setas)  
- Blinking / atributos especiais (A_BLINK nem sempre funciona)  
- UTF-8 e acentos quebrados se TERM não for configurado direito

**Critérios de sucesso (Definition of Done):**  
- O editor abre sem crash ou tela preta/lixo no GNOME Terminal (versão >= 3.36, comum em 2024+)  
- Cores funcionam corretamente (pelo menos 256 cores, ideal truecolor se possível)  
- Redesenho suave (sem flickering excessivo ao digitar/mover cursor)  
- Teclas normais (setas, Home/End, Ctrl+C sem matar o app, Ctrl+S etc.) respondem certo  
- Testado em GNOME Terminal + pelo menos mais um (ex: Kitty ou Alacritty) para comparar

**Passos técnicos concretos (em ordem):**  
1. Usar `curses.wrapper(main)` corretamente para setup/cleanup automático.  
2. Detectar capacidades: `curses.has_colors()`, `curses.COLORS`, `curses.can_change_color()`.  
3. Forçar 256 cores se disponível:  
   ```python
   if curses.COLORS >= 256:
       # usar paleta 256
   else:
       # fallback 8 cores
