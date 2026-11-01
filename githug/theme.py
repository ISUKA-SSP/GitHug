"""Dark colors for ttk and classic Tk widgets, with no extra dependencies."""
from tkinter import ttk

BG = '#15181d'
PANEL = '#1d2229'
FIELD = '#11151a'
TEXT = '#d7dce4'
MUTED = '#a5afbd'
BORDER = '#38414e'
ACCENT = '#315e86'


def apply_dark_theme(window):
    style = ttk.Style(window)
    style.theme_use('clam')
    window.configure(background=BG)
    for option, value in {
        '*Toplevel.background': BG, '*Dialog.background': BG,
        '*Listbox.background': FIELD, '*Listbox.foreground': TEXT,
        '*Listbox.selectBackground': ACCENT, '*Listbox.selectForeground': '#ffffff',
        '*Listbox.highlightBackground': BORDER, '*Listbox.highlightColor': ACCENT,
        '*Listbox.borderWidth': 0,
        '*Text.background': FIELD, '*Text.foreground': TEXT,
        '*Text.insertBackground': TEXT, '*Text.selectBackground': ACCENT,
        '*Text.selectForeground': '#ffffff', '*Text.highlightBackground': BORDER,
        '*Text.highlightColor': ACCENT, '*Text.relief': 'flat',
        '*Menu.background': PANEL, '*Menu.foreground': TEXT,
        '*Menu.activeBackground': ACCENT, '*Menu.activeForeground': '#ffffff',
        '*Label.background': BG, '*Label.foreground': TEXT,
        '*Entry.background': FIELD, '*Entry.foreground': TEXT,
        '*Entry.insertBackground': TEXT,
        '*Button.background': PANEL, '*Button.foreground': TEXT,
        '*Button.activeBackground': ACCENT, '*Button.activeForeground': '#ffffff',
    }.items():
        window.option_add(option, value)
    style.configure('.', background=BG, foreground=TEXT, bordercolor=BORDER,
                    lightcolor=BORDER, darkcolor=BORDER, font=('Yu Gothic UI', 10))
    style.configure('TFrame', background=BG)
    style.configure('TLabel', background=BG, foreground=TEXT)
    style.configure('Heading.TLabel', font=('Yu Gothic UI', 12, 'bold'), foreground='#ecf0f6')
    style.configure('Muted.TLabel', foreground=MUTED)
    style.configure('TButton', background=PANEL, foreground=TEXT, padding=(10, 6))
    style.map('TButton', background=[('pressed', ACCENT), ('active', '#2b3745')],
              foreground=[('disabled', '#707986')])
    style.configure('TEntry', fieldbackground=FIELD, foreground=TEXT, insertcolor=TEXT, padding=5)
    style.map('TEntry', fieldbackground=[('readonly', PANEL)],
              selectbackground=[('!disabled', ACCENT)], selectforeground=[('!disabled', '#ffffff')])
    style.configure('Treeview', background=FIELD, fieldbackground=FIELD, foreground=TEXT,
                    rowheight=27, borderwidth=0)
    style.map('Treeview', background=[('selected', ACCENT)], foreground=[('selected', '#ffffff')])
    style.configure('Treeview.Heading', background=PANEL, foreground=TEXT, padding=(8, 6), relief='flat')
    style.map('Treeview.Heading', background=[('active', '#2b3745')])
    style.configure('TPanedwindow', background=BORDER, sashwidth=8)
    for direction in ('Vertical', 'Horizontal'):
        style.configure(direction + '.TScrollbar', background='#434f5e', troughcolor=BG,
                        arrowcolor=TEXT, bordercolor=BG)
        style.map(direction + '.TScrollbar', background=[('active', '#61758b')])
        style.configure(direction + '.TProgressbar', background='#5592c5', troughcolor=FIELD)
    return style
