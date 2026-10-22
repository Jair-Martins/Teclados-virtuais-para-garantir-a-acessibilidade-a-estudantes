#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Código aberto e de uso livre: pode ser usado, copiado, modificado e
# distribuído sem restrições.
# Gerado com a ajuda do Claude (Anthropic), a partir de pedido e
# revisões do usuário, em outubro de 2026.
"""
Teclado virtual de SÍMBOLOS MATEMÁTICOS para Ubuntu (sessão X11).

Mesma mecânica do teclado de letras:
  1. Clique em "Capturar janela alvo" e, em 3 segundos, clique na janela
     que deve receber os símbolos.
  2. Ao clicar num símbolo, o foco vai à janela alvo, o símbolo é enviado
     com o xdotool e o foco volta ao teclado.

Novidades:
  * Abas por assunto (Básico, Gregas, Cálculo, Conjuntos e lógica, ...).
  * "Modo LaTeX": em vez do símbolo Unicode (∑), envia o comando (\\sum).
    Comandos com chaves, como \\frac{}{}, já deixam o cursor dentro.
  * Shift (uma vez) troca minúsculas por maiúsculas (gregas e letras).

Dependências:
    sudo apt install xdotool python3-tk

Execução:
    python3 teclado_matematico.py
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
ATRASO_DIGITACAO_MS = 15     # intervalo entre caracteres (aumente se falhar)
SEMPRE_NO_TOPO = True
FONTE_SIMBOLO = ("DejaVu Sans", 14)
FONTE_BOTAO = ("DejaVu Sans", 10)
FONTE_TEXTO = ("DejaVu Sans", 12)
COR_ATIVA = "#9fd3ff"
TEMPO_CAPTURA = 3
SIMBOLOS_POR_LINHA = 10      # usado nas abas geradas automaticamente
PRE_AQUECER = True           # corrige o 1º símbolo errado após capturar
ATRASO_APOS_AQUECER = 0.15   # segundos de espera depois do pré-aquecimento


# =============================================================================
# SÍMBOLOS
# =============================================================================
# Cada símbolo pode ser escrito de 4 formas:
#   "x"                          -> só o caractere
#   ("∑", r"\sum")               -> (caractere, comando LaTeX)
#   ("rótulo", "∑", r"\sum")     -> rótulo diferente do que é enviado;
#                                   se o caractere for "" envia sempre LaTeX
#   ("α", "Α", r"\alpha", None)  -> (minúscula, maiúscula, tex min., tex mai.)
#                                   a maiúscula aparece com o Shift
# Para editar o teclado, basta alterar as listas abaixo.

def chunk(lista, n=SIMBOLOS_POR_LINHA):
    return [lista[i:i + n] for i in range(0, len(lista), n)]


def L(letras):
    return [(c, c.upper(), None, None) for c in letras]


def G(lo, up, nome, nome_up=None):
    return (lo, up, "\\" + nome, ("\\" + nome_up) if nome_up else None)


GREGAS = [
    G("α", "Α", "alpha"), G("β", "Β", "beta"), G("γ", "Γ", "gamma", "Gamma"),
    G("δ", "Δ", "delta", "Delta"), G("ε", "Ε", "varepsilon"),
    G("ζ", "Ζ", "zeta"), G("η", "Η", "eta"), G("θ", "Θ", "theta", "Theta"),
    G("ι", "Ι", "iota"), G("κ", "Κ", "kappa"),
    G("λ", "Λ", "lambda", "Lambda"), G("μ", "Μ", "mu"), G("ν", "Ν", "nu"),
    G("ξ", "Ξ", "xi", "Xi"), G("π", "Π", "pi", "Pi"), G("ρ", "Ρ", "rho"),
    G("σ", "Σ", "sigma", "Sigma"), G("τ", "Τ", "tau"),
    G("υ", "Υ", "upsilon", "Upsilon"), G("φ", "Φ", "varphi", "Phi"),
    G("χ", "Χ", "chi"), G("ψ", "Ψ", "psi", "Psi"),
    G("ω", "Ω", "omega", "Omega"),
]
GREGAS_VARIANTES = [
    ("ϵ", r"\epsilon"), ("ϕ", r"\phi"), ("ϑ", r"\vartheta"),
    ("ϱ", r"\varrho"), ("ς", r"\varsigma"), ("ϖ", r"\varpi"),
]

SUPER = [(c, "^{%s}" % t) for c, t in
         zip("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ", "0123456789+-=()ni")]
SUB = [(c, "_{%s}" % t) for c, t in
       zip("₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₙₘₖₗₚₛₜₕᵢⱼᵣᵤᵥ",
           "0123456789+-=()aeoxnmklpsthijruv")]

FRACOES = [
    ("½", r"\frac{1}{2}"), ("⅓", r"\frac{1}{3}"), ("⅔", r"\frac{2}{3}"),
    ("¼", r"\frac{1}{4}"), ("¾", r"\frac{3}{4}"), ("⅕", r"\frac{1}{5}"),
    ("⅖", r"\frac{2}{5}"), ("⅗", r"\frac{3}{5}"), ("⅘", r"\frac{4}{5}"),
    ("⅙", r"\frac{1}{6}"), ("⅚", r"\frac{5}{6}"), ("⅛", r"\frac{1}{8}"),
    ("⅜", r"\frac{3}{8}"), ("⅝", r"\frac{5}{8}"), ("⅞", r"\frac{7}{8}"),
]

# Acentos combinantes: no modo Unicode vão DEPOIS da letra (x + ⃗);
# no modo LaTeX envia \vec{} e deixa o cursor dentro das chaves.
ACENTOS = [
    ("◌\u20d7", "\u20d7", r"\vec{}"), ("◌\u0302", "\u0302", r"\hat{}"),
    ("◌\u0304", "\u0304", r"\bar{}"), ("◌\u0305", "\u0305", r"\overline{}"),
    ("◌\u0307", "\u0307", r"\dot{}"), ("◌\u0308", "\u0308", r"\ddot{}"),
    ("◌\u0303", "\u0303", r"\tilde{}"), ("◌\u0306", "\u0306", r"\breve{}"),
    ("◌\u030c", "\u030c", r"\check{}"), ("◌\u0301", "\u0301", r"\acute{}"),
]

# Estruturas: sempre enviam LaTeX (não existe equivalente em Unicode simples).
ESTRUTURAS = [
    ("a/b", "", r"\frac{}{}"), ("√", "", r"\sqrt{}"),
    ("ⁿ√", "", r"\sqrt[]{}"), ("xⁿ", "", r"^{}"), ("xₙ", "", r"_{}"),
    ("∑ᵇₐ", "", r"\sum_{}^{}"), ("∫ᵇₐ", "", r"\int_{}^{}"),
    ("lim", "", r"\lim_{}"), ("texto", "", r"\text{}"),
    ("$ $", "", r"$$"), ("negrito", "", r"\mathbf{}"),
    ("caligr.", "", r"\mathcal{}"), ("vetor", "", r"\vec{}"),
    ("matriz", "", r"\begin{pmatrix}  &  \\  &  \end{pmatrix}"),
    ("sistema", "", r"\begin{cases}  \\  \end{cases}"),
]

CATEGORIAS = {
    "Básico": [
        list("1234567890"),
        ["+", ("−", "-"), ("×", r"\times"), ("÷", r"\div"), ("·", r"\cdot"),
         "=", ("≠", r"\neq"), ("±", r"\pm"), ("∓", r"\mp")],
        ["(", ")", "[", "]", ("{", r"\{"), ("}", r"\}"),
         ("⟨", r"\langle"), ("⟩", r"\rangle"), "|", ("‖", r"\|")],
        ["<", ">", ("≤", r"\leq"), ("≥", r"\geq"), ("≈", r"\approx"),
         ("≡", r"\equiv"), ("∝", r"\propto"), ("∼", r"\sim"),
         ("≪", r"\ll"), ("≫", r"\gg")],
        [".", ",", ":", ";", "!", "%", "/", "^", "_",
         ("√", "√", r"\sqrt{}"), ("∞", r"\infty")],
    ],
    "Gregas": chunk(GREGAS, 12) + [GREGAS_VARIANTES],
    "Cálculo": [
        [("∫", r"\int"), ("∬", r"\iint"), ("∭", r"\iiint"),
         ("∮", r"\oint"), "∯", ("∑", r"\sum"), ("∏", r"\prod"),
         ("∐", r"\coprod"), ("∂", r"\partial"), ("∇", r"\nabla")],
        [("√", "√", r"\sqrt{}"), ("∛", "∛", r"\sqrt[3]{}"),
         ("∜", "∜", r"\sqrt[4]{}"), ("′", "'"), ("″", "''"),
         ("∞", r"\infty"), ("ℓ", r"\ell"), ("ℏ", r"\hbar")],
        [("lim", "lim", r"\lim_{}"), ("sen", "sen", r"\sin"),
         ("cos", "cos", r"\cos"), ("tg", "tg", r"\tan"),
         ("arcsen", "arcsen", r"\arcsin"), ("ln", "ln", r"\ln"),
         ("log", "log", r"\log"), ("exp", "exp", r"\exp")],
        ["dx", "dy", "dz", "dt", ("d/dx", "d/dx", r"\frac{d}{dx}"),
         ("∂/∂x", "∂/∂x", r"\frac{\partial}{\partial x}"),
         ("∇·", "∇·", r"\nabla\cdot"), ("∇×", "∇×", r"\nabla\times"),
         ("∇²", "∇²", r"\nabla^{2}")],
    ],
    "Conjuntos e lógica": [
        [("∈", r"\in"), ("∉", r"\notin"), ("∋", r"\ni"), ("⊂", r"\subset"),
         ("⊃", r"\supset"), ("⊆", r"\subseteq"), ("⊇", r"\supseteq"),
         ("⊄", r"\not\subset"), ("∪", r"\cup"), ("∩", r"\cap")],
        [("∅", r"\emptyset"), ("∖", r"\setminus"), ("ℕ", r"\mathbb{N}"),
         ("ℤ", r"\mathbb{Z}"), ("ℚ", r"\mathbb{Q}"), ("ℝ", r"\mathbb{R}"),
         ("ℂ", r"\mathbb{C}"), ("ℙ", r"\mathbb{P}"), ("ℵ", r"\aleph")],
        [("∀", r"\forall"), ("∃", r"\exists"), ("∄", r"\nexists"),
         ("¬", r"\neg"), ("∧", r"\land"), ("∨", r"\lor"),
         ("⊕", r"\oplus"), ("⊗", r"\otimes"), ("⊢", r"\vdash"),
         ("⊨", r"\models")],
        [("∴", r"\therefore"), ("∵", r"\because"), ("∣", r"\mid"),
         ("∤", r"\nmid"), ("⊤", r"\top"), ("⊥", r"\bot"),
         ("□", r"\square"), ("∎", r"\blacksquare")],
    ],
    "Setas": [
        [("→", r"\to"), ("←", r"\leftarrow"), ("↑", r"\uparrow"),
         ("↓", r"\downarrow"), ("↔", r"\leftrightarrow"),
         ("↦", r"\mapsto"), ("↪", r"\hookrightarrow"),
         ("⇌", r"\rightleftharpoons")],
        [("⇒", r"\Rightarrow"), ("⇐", r"\Leftarrow"),
         ("⇔", r"\Leftrightarrow"), ("⇑", r"\Uparrow"),
         ("⇓", r"\Downarrow"), ("⟹", r"\implies"),
         ("⟸", r"\impliedby"), ("⟺", r"\iff")],
        [("↗", r"\nearrow"), ("↘", r"\searrow"), ("↙", r"\swarrow"),
         ("↖", r"\nwarrow"), ("⟶", r"\longrightarrow"),
         ("⟵", r"\longleftarrow"), ("⟼", r"\longmapsto"),
         ("↝", r"\leadsto")],
    ],
    "Índices": chunk(SUPER, 9) + chunk(SUB, 11),
    "Frações": chunk(FRACOES, 8),
    "Geometria": [
        [("°", r"^{\circ}"), ("′", "'"), ("″", "''"), ("∠", r"\angle"),
         ("∡", r"\measuredangle"), ("⊥", r"\perp"), ("∥", r"\parallel"),
         ("∦", r"\nparallel"), ("≅", r"\cong"), ("≃", r"\simeq")],
        [("△", r"\triangle"), ("□", r"\square"), ("◯", r"\bigcirc"),
         ("⌒", r"\frown"), ("⊙", r"\odot"), ("π", r"\pi")],
    ],
    "Acentos": chunk(ACENTOS, 10),
    "LaTeX": chunk(ESTRUTURAS, 5),
    "Letras": [L("qwertyuiop"), L("asdfghjkl"), L("zxcvbnm")],
}

# Barra permanente (sempre visível). Nome -> (rótulo, keysym, largura)
TECLAS_FIXAS = [
    ("Shift", None, 9),
    ("Espaço", "space", 14),
    ("Backspace", "BackSpace", 6),
    ("Enter", "Return", 6),
    ("←", "Left", 3), ("↑", "Up", 3), ("↓", "Down", 3), ("→", "Right", 3),
    ("Home", "Home", 5), ("End", "End", 5), ("Del", "Delete", 5),
]
ROTULOS_FIXOS = {"Backspace": "⌫", "Enter": "Enter ⏎", "Shift": "⇧ Shift"}


def normalizar(item):
    """Converte qualquer forma de item em um dicionário uniforme."""
    d = dict(rn=None, rs=None, un=None, us=None, tn=None, ts=None)
    if isinstance(item, str):
        d.update(rn=item, un=item)
    elif len(item) == 2:
        d.update(rn=item[0], un=item[0], tn=item[1])
    elif len(item) == 3:
        d.update(rn=item[0], un=item[1], tn=item[2])
    else:
        d.update(rn=item[0], rs=item[1], un=item[0], us=item[1],
                 tn=item[2], ts=item[3])
    return d


# =============================================================================
# ENVIO (xdotool) - é aqui que se adapta para outro sistema
# =============================================================================
ULTIMO_ERRO = ""


def xdo(*args, timeout=2):
    """Executa o xdotool; devolve a saída ou None (motivo em ULTIMO_ERRO)."""
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
    xdo("key", "--clearmodifiers", combinacao)


def enviar_texto(texto):
    xdo("type", "--clearmodifiers", "--delay", str(ATRASO_DIGITACAO_MS),
        "--", texto, timeout=30)


def enviar_simbolo(texto):
    """Envia o texto e, se houver {} [] ou $$, deixa o cursor lá dentro."""
    enviar_texto(texto)
    marcas = [texto.find(m) for m in ("{}", "[]", "$$") if m in texto]
    if marcas:
        voltar = len(texto) - min(marcas) - 1
        if voltar > 0:
            xdo("key", "--clearmodifiers", *(["Left"] * voltar))


def aquecer():
    """Evita o 1º símbolo errado após capturar a janela alvo.

    Para digitar símbolos Unicode o xdotool remapeia uma tecla por alguns
    instantes; o aplicativo alvo só atualiza seu mapa de teclas na primeira
    vez e, até lá, interpreta a tecla como outro caractere (um número).
    Aqui disparamos Ctrl+∞, que os programas ignoram, para "gastar" essa
    primeira falha sem escrever nada no alvo."""
    xdo("key", "--clearmodifiers", "ctrl+U221E")
    time.sleep(ATRASO_APOS_AQUECER)


# =============================================================================
# INTERFACE
# =============================================================================
class TecladoMatematico(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Teclado matemático")
        self.resizable(False, False)
        if SEMPRE_NO_TOPO:
            self.attributes("-topmost", True)
        try:
            self.attributes("-type", "dialog")   # i3: abre flutuante
        except tk.TclError:
            pass
        self.bind_all("<Control-q>", lambda e: self.destroy())
        self.bind_all("<Control-w>", lambda e: self.destroy())

        self.alvo = None
        self.shift = False
        self.categoria = None
        self.bt_cat = {}
        self.bt_shift = []          # botões "Shift"
        self.bt_simbolo = []        # (botão, dict) da aba atual
        self.fila = queue.Queue()
        self.meu_id = None
        self.preparados = set()     # janelas alvo já pré-aquecidas
        threading.Thread(target=self._trabalhador, daemon=True).start()

        self._montar_topo()
        self._montar_abas()
        self.quadro = tk.Frame(self)
        self.quadro.pack(padx=6, pady=4, anchor="w")
        self._montar_fixas()
        self._montar_texto()
        self.status = tk.Label(self, anchor="w", fg="#555")
        self.status.pack(fill="x", padx=6, pady=(0, 4))

        self.mostrar_categoria("Básico")
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
        self.var_latex = tk.BooleanVar(value=False)
        tk.Checkbutton(topo, text="Modo LaTeX", variable=self.var_latex,
                       takefocus=0).pack(side="right", padx=8)

    def _montar_abas(self):
        f = tk.Frame(self)
        f.pack(fill="x", padx=6)
        for i, nome in enumerate(CATEGORIAS):
            b = tk.Button(f, text=nome, takefocus=0, font=FONTE_BOTAO,
                          command=lambda n=nome: self.mostrar_categoria(n))
            b.grid(row=i // 5, column=i % 5, sticky="ew", padx=1, pady=1)
            self.bt_cat[nome] = b
        for c in range(5):
            f.columnconfigure(c, weight=1)

    def _montar_fixas(self):
        f = tk.Frame(self)
        f.pack(padx=6, pady=2, anchor="w")
        for nome, keysym, larg in TECLAS_FIXAS:
            rot = ROTULOS_FIXOS.get(nome, nome)
            if nome == "Shift":
                b = tk.Button(f, text=rot, width=larg, font=FONTE_BOTAO,
                              takefocus=0, command=self.alternar_shift)
                self.bt_shift.append(b)
            else:
                b = tk.Button(f, text=rot, width=larg, font=FONTE_BOTAO,
                              takefocus=0,
                              command=lambda k=keysym: self._enviar(
                                  enviar_tecla, k))
            b.pack(side="left", padx=1, pady=1)

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

    # ------------------------------------------------------------ abas
    def mostrar_categoria(self, nome):
        self.categoria = nome
        for n, b in self.bt_cat.items():
            b.config(bg=COR_ATIVA if n == nome else self.cget("bg"))
        for w in self.quadro.winfo_children():
            w.destroy()
        self.bt_simbolo = []
        for linha in CATEGORIAS[nome]:
            f = tk.Frame(self.quadro)
            f.pack(anchor="w")
            for item in linha:
                d = normalizar(item)
                larg = max(4, len(d["rn"]) + 1)
                b = tk.Button(f, text=d["rn"], width=larg, takefocus=0,
                              font=FONTE_SIMBOLO,
                              command=lambda d=d: self.pressionar(d))
                b.pack(side="left", padx=1, pady=1)
                self.bt_simbolo.append((b, d))
        self._atualizar_visual()

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
        self.preparados.discard(wid)    # pré-aquece de novo a cada captura
        self.lbl_alvo.config(text=nome[:50], fg="#060")
        self.msg("Janela alvo definida.")

    # ------------------------------------------------------------ Shift
    def alternar_shift(self):
        self.shift = not self.shift
        self._atualizar_visual()

    def _atualizar_visual(self):
        cor = COR_ATIVA if self.shift else self.cget("bg")
        for b in self.bt_shift:
            b.config(bg=cor)
        for b, d in self.bt_simbolo:
            if d["rs"]:
                b.config(text=d["rs"] if self.shift else d["rn"])

    # ------------------------------------------------------------ envio
    def _enviar(self, funcao, *args):
        """Coloca o envio na fila (a interface não trava)."""
        if not self.alvo:
            self.msg("Defina primeiro a janela alvo.", True)
            return False
        self.meu_id = self.winfo_id()
        self.fila.put((self.alvo, funcao, args))
        return True

    def _trabalhador(self):
        """Executa os envios fora da interface. Se houver várias teclas na
        fila, o foco só volta ao teclado quando a fila esvazia."""
        no_alvo = None
        while True:
            alvo, funcao, args = self.fila.get()
            if no_alvo != alvo:
                ativar_janela(alvo)
                no_alvo = alvo
                if PRE_AQUECER and alvo not in self.preparados:
                    aquecer()
                    self.preparados.add(alvo)
            funcao(*args)
            if self.fila.empty():
                ativar_janela(self.meu_id)
                no_alvo = None

    def pressionar(self, d):
        maiusc = self.shift and d["us"] is not None
        uni = d["us"] if maiusc else d["un"]
        tex = d["ts"] if maiusc else d["tn"]
        if tex and (self.var_latex.get() or not uni):
            texto = tex
        else:
            texto = uni
        if self._enviar(enviar_simbolo, texto) and self.shift:
            self.shift = False
            self._atualizar_visual()

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
    TecladoMatematico().mainloop()
