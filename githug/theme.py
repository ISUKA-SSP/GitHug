"""Dark colors for ttk and classic Tk widgets, with no extra dependencies."""
import tkinter as tk
from tkinter import ttk

BG = '#202020'
PANEL = '#252525'
FIELD = '#191919'
TEXT = '#eeeeee'
MUTED = '#aaaaaa'
BORDER = '#383838'
ACCENT = '#245866'


def check_indicators(window, style):
    images = []
    for selected, disabled in ((False, False), (True, False), (False, True), (True, True)):
        image = tk.PhotoImage(master=window, width=22, height=22)
        image.put(BG, to=(0, 0, 22, 22))
        image.put('#68788a' if disabled else '#b6c6d8', to=(2, 2, 20, 20))
        image.put(('#46708d' if disabled else '#287db5') if selected else FIELD, to=(4, 4, 18, 18))
        if selected:
            for x,y in [(6,10),(7,11),(8,12),(9,13),(10,12),(11,11),(12,10),(13,9),(14,8),(15,7)]:
                image.put('#e4eaf0' if disabled else '#ffffff', to=(x, y, x+2, y+2))
        images.append(image)
    style.element_create('HugCheck.indicator', 'image', images[0],
                         ('disabled', 'selected', images[3]), ('disabled', images[2]), ('selected', images[1]))
    style.layout('TCheckbutton', [('Checkbutton.padding', {'sticky':'nswe', 'children':[
        ('HugCheck.indicator', {'side':'left', 'sticky':''}),
        ('Checkbutton.focus', {'side':'left', 'sticky':'nswe', 'children':[
            ('Checkbutton.label', {'sticky':'nswe'})]})]})])
    window._githug_check_images = images  # Keep Tcl image handles alive.


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
                    lightcolor=BORDER, darkcolor=BORDER, font=('Yu Gothic UI', 11))
    style.configure('TFrame', background=PANEL)
    style.configure('Appbar.TFrame', background=BG)
    style.configure('Card.TFrame', background=PANEL, borderwidth=0, relief='flat')
    style.configure('GraphHandle.TFrame',background=BORDER)
    style.configure('TLabel', background=PANEL, foreground=TEXT)
    style.configure('Brand.TLabel', background=BG, foreground='#f5f5f5', font=('Segoe UI', 23, 'bold'))
    style.configure('BrandSubtitle.TLabel', background=BG, foreground=MUTED, font=('Yu Gothic UI', 9))
    style.configure('Badge.TLabel', background=PANEL, foreground='#81d5d2', padding=(9,4), font=('Segoe UI',9))
    style.configure('AppbarMuted.TLabel', background=BG, foreground=MUTED)
    style.configure('Heading.TLabel', font=('Yu Gothic UI', 12, 'bold'), foreground='#ecf0f6')
    style.configure('Muted.TLabel', foreground=MUTED)
    style.configure('TButton', background='#333333', foreground=TEXT, padding=(12, 7), relief='flat', borderwidth=1)
    style.map('TButton', background=[('pressed', ACCENT), ('active', '#414141')],
              foreground=[('disabled', '#707986')])
    style.configure('Primary.TButton', background='#246a73', foreground='#f3fffe', padding=(14,7), relief='flat')
    style.map('Primary.TButton', background=[('pressed','#1c5864'),('active','#2c8390'),('disabled','#363636')], foreground=[('disabled',MUTED)])
    style.configure('Quiet.TButton', background=PANEL, foreground=MUTED, padding=(10,7), relief='flat')
    style.configure('Danger.TButton', background='#392630', foreground='#f7c1c7', padding=(12,7), relief='flat')
    style.map('Danger.TButton', background=[('active','#56323f')])
    style.configure('TCheckbutton', background=PANEL, foreground=TEXT, indicatorbackground=FIELD, padding=4)
    style.map('TCheckbutton', background=[('active', PANEL)], foreground=[('disabled', MUTED)])
    style.configure('TEntry', fieldbackground=FIELD, foreground=TEXT, insertcolor=TEXT, padding=5)
    style.map('TEntry', fieldbackground=[('readonly', PANEL)],
              selectbackground=[('!disabled', ACCENT)], selectforeground=[('!disabled', '#ffffff')])
    style.configure('TCombobox', fieldbackground=FIELD, background=PANEL, foreground=TEXT, arrowcolor=TEXT, padding=5)
    style.map('TCombobox', fieldbackground=[('readonly', FIELD)], foreground=[('readonly', TEXT)],
              selectbackground=[('readonly', ACCENT)], selectforeground=[('readonly', '#ffffff')])
    style.configure('Treeview', background=FIELD, fieldbackground=FIELD, foreground=TEXT,
                    rowheight=30, borderwidth=0)
    style.map('Treeview', background=[('selected', ACCENT)], foreground=[('selected', '#ffffff')])
    style.configure('Treeview.Heading', background='#303030', foreground='#cccccc', padding=(10, 8), relief='flat')
    style.map('Treeview.Heading', background=[('active', '#414141')])
    style.configure('TPanedwindow', background=BORDER, sashwidth=8)
    for direction in ('Vertical', 'Horizontal'):
        style.configure(direction + '.TScrollbar', background='#434f5e', troughcolor=BG,
                        arrowcolor=TEXT, bordercolor=BG)
        style.map(direction + '.TScrollbar', background=[('active', '#61758b')])
        style.configure(direction + '.TProgressbar', background='#5592c5', troughcolor=FIELD)
    style.configure('Icon.TButton',padding=(4,5),font=('Segoe UI Symbol',12))
    style.configure('View.TButton',background='#353535',foreground='#bdbdbd',padding=(8,9),font=('Yu Gothic UI',11),anchor='center')
    style.configure('SelectedView.TButton',background='#245866',foreground='#ffffff',padding=(8,9),font=('Yu Gothic UI',11,'bold'),anchor='center')
    style.map('View.TButton',background=[('active','#454545')])
    style.map('SelectedView.TButton',background=[('active','#2b6876'),('pressed','#245866')],foreground=[('!disabled','#ffffff')])
    style.configure('TNotebook',background=PANEL,borderwidth=0)
    style.configure('TNotebook.Tab',background='#383838',foreground='#eeeeee',padding=(14,8))
    style.map('TNotebook.Tab',background=[('selected','#245866'),('active','#484848')],
              foreground=[('selected','#ffffff'),('disabled','#999999'),('!disabled','#eeeeee')])
    check_indicators(window, style)
    from .platform_support import dark_titlebar
    def mapped(event):
        if event.widget is window or isinstance(event.widget, tk.Toplevel):
            dark_titlebar(event.widget)
    window.bind_all('<Map>', mapped, add='+')
    return style
