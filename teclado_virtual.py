#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Código aberto e de uso livre: pode ser usado, copiado, modificado e
# distribuído sem restrições.
# Gerado com a ajuda do Claude (Anthropic), a partir de pedido e
# revisões do usuário, em outubro de 2026.
"""
Teclado virtual para Ubuntu (sessão X11 / "Ubuntu on Xorg").

Como funciona
-------------
1. Clique em "Capturar janela alvo" e, dentro de 3 segundos, clique na janela
   do aplicativo que deve receber as teclas.
2. Ao clicar numa tecla (ou em "Enviar" no campo de texto), o script:
      a) dá o foco à janela alvo,
      b) envia a tecla/texto com o xdotool,
      c) devolve o foco ao teclado virtual.

Dependências:
    sudo apt install xdotool python3-tk

Execução:
    python3 teclado_virtual.py
"""

import os
import queue
import shutil
import subprocess
import threading
import time
import tkinter as tk

# =============================================================================
# CONFIGURAÇÕES (edite à vontade)
# =============================================================================
ATRASO_TROCA_FOCO = 0.05     # segundos de espera após mudar o foco
ATRASO_DIGITACAO_MS = 12     # intervalo entre caracteres ao enviar frases
SEMPRE_NO_TOPO = True        # mantém o teclado sobre as outras janelas
FONTE_TECLA = ("DejaVu Sans", 11)
FONTE_TEXTO = ("DejaVu Sans", 12)
COR_ATIVA = "#9fd3ff"        # cor de modificadores ativos
TEMPO_CAPTURA = 3            # segundos para clicar na janela alvo

# =============================================================================
# LAYOUT
# =============================================================================
def L(letras):
    """Gera (minúscula, maiúscula) para cada letra."""
    return [(c, c.upper()) for c in letras]


# Teclas comuns: tupla (normal, com Shift). Teclas especiais: nome (str).
LINHAS = [
    ["Esc"] + [f"F{i}" for i in range(1, 13)] + ["Del"],
    [("'", '"'), ("1", "!"), ("2", "@"), ("3", "#"), ("4", "$"), ("5", "%"),
     ("6", "¨"), ("7", "&"), ("8", "*"), ("9", "("), ("0", ")"), ("-", "_"),
     ("=", "+"), "Backspace"],
    ["Tab"] + L("qwertyuiop") + [("´", "`"), ("[", "{"), "Enter"],
    ["Caps"] + L("asdfghjkl") + [("ç", "Ç"), ("~", "^"), ("]", "}")],
    ["Shift", ("\\", "|")] + L("zxcvbnm") +
    [(",", "<"), (".", ">"), (";", ":"), ("/", "?"), "Shift"],
    ["Ctrl", "Alt", "Espaço", "←", "↑", "↓", "→", "Home", "End", "PgUp", "PgDn"],
]

# nome -> (rótulo, keysym do xdotool, largura)
ESPECIAIS = {
    "Esc": ("Esc", "Escape", 4),
    "Del": ("Del", "Delete", 4),
    "Backspace": ("⌫", "BackSpace", 8),
    "Tab": ("Tab", "Tab", 6),
    "Enter": ("Enter ⏎", "Return", 8),
    "Espaço": ("Espaço", "space", 28),
    "←": ("←", "Left", 4),
    "↑": ("↑", "Up", 4),
    "↓": ("↓", "Down", 4),
    "→": ("→", "Right", 4),
    "Home": ("Home", "Home", 5),
    "End": ("End", "End", 5),
    "PgUp": ("PgUp", "Prior", 5),
    "PgDn": ("PgDn", "Next", 5),
}
for _i in range(1, 13):
    ESPECIAIS[f"F{_i}"] = (f"F{_i}", f"F{_i}", 4)

# nome -> (rótulo, largura)
MODIFICADORES = {
    "Shift": ("⇧ Shift", 9),
    "Caps": ("⇪ Caps", 8),
    "Ctrl": ("Ctrl", 6),
    "Alt": ("Alt", 6),
}
# nome do modificador -> nome usado pelo xdotool
NOME_XDO = {"Shift": "shift", "Ctrl": "ctrl", "Alt": "alt"}


# =============================================================================
# FUNÇÕES DE ENVIO (xdotool) - é aqui que se adapta para outro sistema
# =============================================================================
ULTIMO_ERRO = ""


def xdo(*args, timeout=2):
    """Executa o xdotool e devolve a saída (texto) ou None em caso de erro.
    O motivo da falha fica em ULTIMO_ERRO."""
    global ULTIMO_ERRO
    try:
        r = subprocess.run(["xdotool", *args], capture_output=True,
                           text=True, timeout=timeout)
        if r.returncode == 0:
            ULTIMO_ERRO = ""
            return r.stdout.strip()
        ULTIMO_ERRO = (r.stderr or "código %d" % r.returncode).strip()
    except subprocess.TimeoutExpired:
        ULTIMO_ERRO = "tempo esgotado"
    except OSError as e:
        ULTIMO_ERRO = str(e)
    return None


def ativar_janela(wid):
    xdo("windowactivate", str(wid))   # sem --sync: no i3 ele demora ~2 s
    time.sleep(ATRASO_TROCA_FOCO)


def enviar_tecla(combinacao):
    """Ex.: 'Return', 'ctrl+c', 'F5'."""
    xdo("key", "--clearmodifiers", combinacao)


def enviar_texto(texto):
    xdo("type", "--clearmodifiers", "--delay", str(ATRASO_DIGITACAO_MS),
        "--", texto, timeout=30)


# =============================================================================
# INTERFACE
# =============================================================================
class TecladoVirtual(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Teclado virtual")
        self.resizable(False, False)
        if SEMPRE_NO_TOPO:
            self.attributes("-topmost", True)
        try:
            # tipo "dialog": gerenciadores como o i3 abrem a janela flutuante
            self.attributes("-type", "dialog")
        except tk.TclError:
            pass
        self.bind_all("<Control-q>", lambda e: self.destroy())
        self.bind_all("<Control-w>", lambda e: self.destroy())

        self.alvo = None                       # id da janela alvo
        self.mod = {"Shift": False, "Caps": False, "Ctrl": False, "Alt": False}
        self.bt_mod = {k: [] for k in self.mod}
        self.bt_char = []                      # (botão, normal, shift)
        self.fila = queue.Queue()              # envios em segundo plano
        self.meu_id = None
        threading.Thread(target=self._trabalhador, daemon=True).start()

        self._montar_topo()
        self._montar_teclas()
        self._montar_texto()

        self.status = tk.Label(self, anchor="w", fg="#555", text="")
        self.status.pack(fill="x", padx=6, pady=(0, 4))
        self._verificar_ambiente()

    # ------------------------------------------------------------ montagem
    def _montar_topo(self):
        topo = tk.Frame(self)
        topo.pack(fill="x", padx=6, pady=4)
        tk.Button(topo, text="Capturar janela alvo", takefocus=0,
                  command=self.capturar_alvo).pack(side="left")
        self.lbl_alvo = tk.Label(topo, text="(nenhuma janela alvo)", fg="#a00")
        self.lbl_alvo.pack(side="left", padx=8)
        tk.Button(topo, text="✕ Fechar", takefocus=0,
                  command=self.destroy).pack(side="right")

    def _montar_teclas(self):
        quadro = tk.Frame(self)
        quadro.pack(padx=6, pady=2)
        for linha in LINHAS:
            f = tk.Frame(quadro)
            f.pack(anchor="w")
            for item in linha:
                if isinstance(item, tuple):
                    self._tecla_char(f, *item)
                elif item in MODIFICADORES:
                    self._tecla_mod(f, item)
                else:
                    self._tecla_especial(f, item)

    def _tecla_char(self, pai, normal, shift):
        b = tk.Button(pai, text=normal, width=4, font=FONTE_TECLA, takefocus=0,
                      command=lambda: self.pressionar_char(normal, shift))
        b.pack(side="left", padx=1, pady=1)
        self.bt_char.append((b, normal, shift))

    def _tecla_especial(self, pai, nome):
        rotulo, keysym, larg = ESPECIAIS[nome]
        b = tk.Button(pai, text=rotulo, width=larg, font=FONTE_TECLA,
                      takefocus=0,
                      command=lambda: self.pressionar_especial(keysym))
        b.pack(side="left", padx=1, pady=1)

    def _tecla_mod(self, pai, nome):
        rotulo, larg = MODIFICADORES[nome]
        b = tk.Button(pai, text=rotulo, width=larg, font=FONTE_TECLA,
                      takefocus=0, command=lambda: self.alternar_mod(nome))
        b.pack(side="left", padx=1, pady=1)
        self.bt_mod[nome].append(b)

    def _montar_texto(self):
        f = tk.LabelFrame(self, text="Enviar frase ou expressão")
        f.pack(fill="x", padx=6, pady=4)
        self.entrada = tk.Entry(f, font=FONTE_TEXTO)
        self.entrada.pack(side="left", fill="x", expand=True, padx=4, pady=4)
        self.entrada.bind("<Return>", lambda e: self.enviar_campo())
        self.var_enter = tk.BooleanVar(value=False)
        tk.Checkbutton(f, text="+ Enter", variable=self.var_enter,
                       takefocus=0).pack(side="left")
        tk.Button(f, text="Enviar", takefocus=0,
                  command=self.enviar_campo).pack(side="left", padx=4)
        tk.Button(f, text="Limpar", takefocus=0,
                  command=lambda: self.entrada.delete(0, "end")
                  ).pack(side="left", padx=(0, 4))

    # ------------------------------------------------------------ ambiente
    def _verificar_ambiente(self):
        if not shutil.which("xdotool"):
            self.msg("xdotool não encontrado: sudo apt install xdotool", True)
        elif os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
            self.msg("Sessão Wayland: o xdotool não controla janelas nativas. "
                     "Entre em 'Ubuntu on Xorg'.", True)
        else:
            self.msg("Pronto. Capture a janela alvo para começar.")

    def msg(self, texto, erro=False):
        self.status.config(text=texto, fg="#a00" if erro else "#555")

    # ------------------------------------------------------------ alvo
    def capturar_alvo(self):
        self._contagem(TEMPO_CAPTURA)

    def _contagem(self, n):
        if n > 0:
            self.msg(f"Clique na janela alvo... {n}")
            self.after(1000, lambda: self._contagem(n - 1))
            return
        wid = xdo("getactivewindow") or xdo("getwindowfocus")
        if not wid:
            self.msg("xdotool falhou: " + (ULTIMO_ERRO or "sem resposta"), True)
            return
        nome = xdo("getwindowname", wid) or wid
        if nome == self.title() or wid == str(self.winfo_id()):
            self.msg("Capturou o próprio teclado: clique na janela alvo "
                     "durante a contagem.", True)
            return
        self.alvo = wid
        self.lbl_alvo.config(text=nome[:50], fg="#060")
        self.msg("Janela alvo definida.")

    # ------------------------------------------------------------ modificadores
    def alternar_mod(self, nome):
        self.mod[nome] = not self.mod[nome]
        self._atualizar_visual()

    def _soltar_modificadores(self):
        """Shift, Ctrl e Alt valem para uma tecla só; Caps permanece."""
        for k in ("Shift", "Ctrl", "Alt"):
            self.mod[k] = False
        self._atualizar_visual()

    def _atualizar_visual(self):
        for nome, botoes in self.bt_mod.items():
            for b in botoes:
                b.config(bg=COR_ATIVA if self.mod[nome] else
                         self.cget("bg"))
        for b, normal, shift in self.bt_char:
            b.config(text=self._char_atual(normal, shift))

    def _char_atual(self, normal, shift):
        if normal.isalpha():
            maiusculo = self.mod["Shift"] ^ self.mod["Caps"]
        else:
            maiusculo = self.mod["Shift"]
        return shift if maiusculo else normal

    # ------------------------------------------------------------ envio
    def _enviar(self, funcao, *args):
        """Troca o foco, envia, e devolve o foco ao teclado."""
        if not self.alvo:
            self.msg("Defina primeiro a janela alvo.", True)
            return False
        self.meu_id = self.winfo_id()
        self.fila.put((self.alvo, funcao, args))
        return True

    def _trabalhador(self):
        """Executa os envios fora da interface (os botões não 'travam').
        Se houver várias teclas na fila, só devolve o foco ao final."""
        no_alvo = None
        while True:
            alvo, funcao, args = self.fila.get()
            if no_alvo != alvo:
                ativar_janela(alvo)
                no_alvo = alvo
            funcao(*args)
            if self.fila.empty():
                ativar_janela(self.meu_id)
                no_alvo = None

    def pressionar_char(self, normal, shift):
        char = self._char_atual(normal, shift)
        mods = [NOME_XDO[k] for k in ("Ctrl", "Alt") if self.mod[k]]
        if mods and normal.isascii() and normal.isalnum():
            comb = "+".join(mods + [normal])
            self._enviar(enviar_tecla, comb)
        else:
            self._enviar(enviar_texto, char)
        self._soltar_modificadores()

    def pressionar_especial(self, keysym):
        mods = [NOME_XDO[k] for k in ("Shift", "Ctrl", "Alt") if self.mod[k]]
        self._enviar(enviar_tecla, "+".join(mods + [keysym]))
        self._soltar_modificadores()

    def enviar_campo(self):
        texto = self.entrada.get()
        com_enter = self.var_enter.get()
        if not texto:
            return

        def tarefa():
            enviar_texto(texto)
            if com_enter:
                enviar_tecla("Return")

        if self._enviar(tarefa):
            self.entrada.focus_set()
            self.msg("Texto enviado.")


if __name__ == "__main__":
    TecladoVirtual().mainloop()
