"""Normal launch plus a no-network frozen executable smoke test."""
import argparse
import json
import os
from pathlib import Path
import platform
import sys
import traceback
import tempfile
from . import __version__
from .platform_support import enable_dpi_awareness, git_executable


def launch(app_class, argv=None):
    parser=argparse.ArgumentParser(prog='GitHug')
    parser.add_argument('--version',action='store_true')
    parser.add_argument('--smoke-test',metavar='REPORT')
    args=parser.parse_args(argv)
    if args.version:
        if sys.stdout:print(__version__)
        return 0
    enable_dpi_awareness()
    import tkinter as tk
    from tkinter import messagebox
    root=None
    try:
        root=tk.Tk()
        app=app_class(root)
        if args.smoke_test:
            from .core import git
            report={'version':__version__,'platform':platform.platform(),'frozen':bool(getattr(sys,'frozen',False)),
                    'git_executable':git_executable(),'git_version':git('--version').strip(),
                    'tk':str(root.tk.call('info','patchlevel')),'gui_initialized':True}
            from .core import Project
            from .notes import Notes
            with tempfile.TemporaryDirectory(prefix='GitHug-smoke-') as temporary:
                directory=Path(temporary)
                git('init','-b','main',directory/'repo')
                git('config','user.name','GitHug smoke',cwd=directory/'repo')
                git('config','user.email','smoke@example.invalid',cwd=directory/'repo')
                (directory/'repo'/'file.txt').write_text('smoke test',encoding='utf-8')
                git('add','.',cwd=directory/'repo')
                git('-c','commit.gpgsign=false','commit','-m','smoke',cwd=directory/'repo')
                git('clone',directory/'repo',directory/'copy')
                report['git_roundtrip']=(directory/'copy'/'file.txt').read_text()=='smoke test'
                app.project=Project(directory/'workspace','https://github.com/example/smoke')
                app.current={'url':app.project.url,'work':[]}
                app.notes=Notes(app.project.base)
                ids=[format(i,'040x') for i in range(1,5)]
                records=[{'sha':ids[0],'parents':ids[1]+' '+ids[2],'refs':'main','message':'合流の表示確認','date':'2026-11-03T10:00:00+09:00'},
                         {'sha':ids[1],'parents':ids[3],'refs':'','message':'普段使う版の変更','date':'2026-11-02T10:00:00+09:00'},
                         {'sha':ids[2],'parents':ids[3],'refs':'work/example','message':'別の枝の変更','date':'2026-11-02T09:00:00+09:00'},
                         {'sha':ids[3],'parents':'','refs':'','message':'最初の版','date':'2026-11-01T10:00:00+09:00'}]
                app.show_history(records)
                root.after(350,root.quit)
                root.mainloop()
                root.update_idletasks()
                report['graph_items']=len(app.history.graph_view.canvas.find_all())
                report['history_rows']=len(app.history.get_children())
            report['history_size']=app.history.winfo_geometry()
            Path(args.smoke_test).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            root.destroy()
            return 0
        root.mainloop()
        return 0
    except Exception:
        directory=Path(os.environ.get('APPDATA',Path.home()/'.config'))/'GitHug'
        directory.mkdir(parents=True,exist_ok=True)
        path=directory/'startup_error.log'
        path.write_text(traceback.format_exc(),encoding='utf-8')
        if args.smoke_test:
            Path(args.smoke_test).write_text(json.dumps({'version':__version__,'gui_initialized':False,'error':traceback.format_exc()},ensure_ascii=False,indent=2),encoding='utf-8')
        else:
            try:messagebox.showerror('GitHugを起動できませんでした','起動記録を保存しました。\n'+str(path),parent=root)
            except Exception:pass
        if root:
            try:root.destroy()
            except Exception:pass
        return 1
