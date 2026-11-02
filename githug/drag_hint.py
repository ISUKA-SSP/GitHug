"""Folder-shaped drag feedback, positioned away from the pointer hit target."""
import tkinter as tk


class DragHint:
    def __init__(self, root):
        self.root = root
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', True)
        frame = tk.Frame(self.window, background='#263443', highlightbackground='#65809a', highlightthickness=1)
        frame.pack(fill='both', expand=True)
        self.icon = tk.Canvas(frame, width=44, height=42, background='#263443', highlightthickness=0)
        self.icon.pack(side='left', padx=6, pady=8)
        self.label = tk.Label(frame, background='#263443', foreground='#eef4fa', justify='left',
                              anchor='w', font=('Yu Gothic UI', 10), wraplength=240)
        self.label.pack(side='left', fill='both', padx=(0, 12), pady=8)

    def show(self, x, y, title, subtitle='', allowed=True, action=''):
        icon = self.icon
        icon.delete('all')
        color = '#efc166' if allowed else '#9c9a91'
        icon.create_polygon(4, 10, 17, 10, 21, 15, 39, 15, 39, 34, 4, 34, fill=color, outline='#f7d98e')
        icon.create_polygon(4, 17, 41, 17, 37, 36, 4, 36, fill='#e2b458' if allowed else '#8e8b82', outline='#f7d98e')
        if allowed:
            if action:
                icon.create_oval(24, 24, 43, 43, fill='#347eb0', outline='#c3e6ff')
                icon.create_text(33, 33, text=action, fill='white', font=('Yu Gothic UI', 11, 'bold'))
        else:
            icon.create_oval(24, 24, 42, 42, fill='#263443', outline='#ff8d8d', width=2)
            icon.create_line(27, 39, 39, 27, fill='#ff8d8d', width=2)
        self.label.configure(text=title + ('\n' + subtitle[:55] if subtitle else ''))
        self.window.update_idletasks()
        width, height = self.window.winfo_reqwidth(), self.window.winfo_reqheight()
        # Flip to the other side near the edge, keeping the pointer outside the hint.
        px = x + 18 if x + width + 18 < self.root.winfo_screenwidth() else x - width - 18
        py = y + 22 if y + height + 22 < self.root.winfo_screenheight() else y - height - 22
        self.window.geometry(f'+{max(0,px)}+{max(0,py)}')
        self.window.deiconify()

    def hide(self):
        self.window.withdraw()
