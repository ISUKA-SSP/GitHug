"""Normal launch plus a no-network frozen executable smoke test."""
import argparse
import json
import os
from pathlib import Path
import platform
import sys
import traceback
import tempfile
import subprocess
from . import __version__
from .platform_support import enable_dpi_awareness, git_executable


def launch(app_class, argv=None):
    parser=argparse.ArgumentParser(prog='GitTotte')
    parser.add_argument('--version',action='store_true')
    parser.add_argument('--smoke-test',metavar='REPORT')
    args=parser.parse_args(argv)
    if args.version:
        if sys.stdout:print(__version__)
        return 0
    enable_dpi_awareness()
    import tkinter as tk
    from tkinter import ttk
    from tkinter import messagebox
    root=None
    try:
        root=tk.Tk()
        callback_errors=[]
        if args.smoke_test:
            root.report_callback_exception=lambda kind,value,tb:callback_errors.append(str(value))
        root._githug_smoke=bool(args.smoke_test)
        if args.smoke_test:
            smoke_config=tempfile.TemporaryDirectory(prefix='GitTotte-smoke-settings-')
            root._githug_smoke_dir=smoke_config.name
        app=app_class(root)
        if args.smoke_test:
            from .core import git
            report={'version':__version__,'platform':platform.platform(),'frozen':bool(getattr(sys,'frozen',False)),
                    'git_executable':git_executable(),'git_version':git('--version').strip(),
                    'tk':str(root.tk.call('info','patchlevel')),'gui_initialized':True,
                    'mascot_size':[app.mascot_image.width(),app.mascot_image.height()]}
            from .core import Project
            from .notes import Notes
            with tempfile.TemporaryDirectory(prefix='GitTotte-smoke-') as temporary:
                directory=Path(temporary)
                git('init','-b','main',directory/'repo')
                git('config','user.name','GitTotte smoke',cwd=directory/'repo')
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
                app.history_query.set('合流')
                report['history_search_filters']=len(app.history.get_children())==1
                app.history_header.clear()
                report['history_search_clears']=len(app.history.get_children())==4
                app.folder_browser.set_folder(str(directory/'copy'))
                app.toggle_explanation()
                display_settings=app.settings_dialog()
                root.update_idletasks()
                report['display_settings_opened']=bool(display_settings.winfo_exists())
                def descendants(widget):
                    return [child for c in widget.winfo_children() for child in [c]+descendants(c)]
                checks=[w for w in descendants(display_settings) if isinstance(w,ttk.Checkbutton)]
                for w in checks:w.invoke()
                next(w for w in descendants(display_settings) if isinstance(w,ttk.Button) and w.cget('text')=='適用').invoke()
                saved=json.loads(app.config_path.read_text(encoding='utf-8'))
                report['guidance_preferences_saved']=not saved['hover_help'] and not saved['selection_guide'] and not app.tooltips.enabled
                report['mascot_setting_saved']=not saved['mascot_animation'] and app.mascot_view.timer is None
                display_settings=app.settings_dialog()
                checks=[w for w in descendants(display_settings) if isinstance(w,ttk.Checkbutton)]
                for w in checks:w.invoke()
                next(w for w in descendants(display_settings) if isinstance(w,ttk.Button) and w.cget('text')=='適用').invoke()
                report['guidance_preferences_restored']=app.tooltips.enabled
                settings=app.explanation.settings_dialog()
                root.update_idletasks()
                report['settings_dialog_opened']=settings.winfo_exists()
                settings.destroy()
                app.inspect_file(str(directory/'copy'/'file.txt'))
                from .reading import write_explanation
                write_explanation(app.explanation.output,'### 確認用の見出し\n* **重要**な説明と `file.txt`')
                app.explanation.tabs.select(0)
                app.explanation.tabs.select(1)
                app.explanation.prepare_input()
                app.history.graph_view.manual_width=180
                app.history.graph_view.set_page(app.history_model,[r['sha'] for r in records],True)
                root.after(1400,root.quit)
                root.mainloop()
                root.update_idletasks()
                root.update()
                app.tooltips.owner=app.history_header.entry
                app.tooltips.duration=40
                app.tooltips.show(app.history_header.entry,'検索欄の説明')
                report['hover_help_visible']=bool(app.tooltips.tip)
                root.after(100,root.quit);root.mainloop()
                report['hover_help_expires']=app.tooltips.tip is None
                app.tooltips.duration=4500
                app.tooltips.owner=app.history_header.entry
                app.tooltips.show(app.history_header.entry,'検索欄の説明')
                app.tooltips.set_enabled(False)
                report['hover_help_disabled']=app.tooltips.tip is None
                app.tooltips.set_enabled(True)
                report['graph_items']=len(app.history.graph_view.canvas.find_all())
                report['history_rows']=len(app.history.get_children())
                report['folder_tree_loaded']=len(app.folder_browser.paths)>1
                report['explanation_prepared']=bool(app.explanation.payload)
                report['explanation_panel_visible']=app.explanation_visible
                report['graph_width']=app.history.graph_view.canvas.winfo_width()
                if os.name=='nt':
                    # Capture only the temporary test window for visual review; never a user's session.
                    capture=Path(args.smoke_test).with_suffix('.png').resolve()
                    script=('Add-Type -AssemblyName System.Drawing; '
                            '$b=New-Object System.Drawing.Bitmap([int]$env:GITHUG_CAPTURE_W,[int]$env:GITHUG_CAPTURE_H); '
                            '$g=[System.Drawing.Graphics]::FromImage($b); '
                            '$g.CopyFromScreen([int]$env:GITHUG_CAPTURE_X,[int]$env:GITHUG_CAPTURE_Y,0,0,$b.Size); '
                            '$b.Save($env:GITHUG_CAPTURE_PATH,[System.Drawing.Imaging.ImageFormat]::Png); $g.Dispose(); $b.Dispose()')
                    subprocess.run(['powershell','-NoProfile','-Command',script],check=True,timeout=30,
                                   creationflags=subprocess.CREATE_NO_WINDOW,
                                   env={**os.environ,'GITHUG_CAPTURE_PATH':str(capture),
                                        'GITHUG_CAPTURE_X':str(root.winfo_rootx()),'GITHUG_CAPTURE_Y':str(root.winfo_rooty()),
                                        'GITHUG_CAPTURE_W':str(root.winfo_width()),'GITHUG_CAPTURE_H':str(root.winfo_height())})
                report['section_geometry']=app.sections.winfo_geometry()
                report['section_divider']=app.sections.sashpos(0)
                report['search_header_geometry']=[{'header':h.winfo_geometry(),'entry':h.entry.winfo_geometry(),'button':h.clear_button.winfo_geometry(),'header_x':h.winfo_rootx(),'button_right':h.clear_button.winfo_rootx()+h.clear_button.winfo_width(),'mapped':h.winfo_ismapped()} for h in (app.history_header,app.folder_header)]
                report['search_headers_fit']=all(h.entry.winfo_width()>=30 and h.clear_button.winfo_rootx()+h.clear_button.winfo_width()<=h.winfo_rootx()+h.winfo_width() for h in (app.history_header,app.folder_header))
                if not all(report[k] for k in ('history_search_filters','history_search_clears','search_headers_fit')):
                    raise RuntimeError('検索欄の確認に失敗しました: '+str(report))
                report['sidebar_width']=app.projects.master.winfo_width()
                report['panel_width']=app.explanation.frame.winfo_width()
                buttons=app.explanation.header_buttons
                report['header_buttons_visible']=all(b.winfo_width()>15 and b.winfo_x()>=0 and b.winfo_x()+b.winfo_width()<=b.master.winfo_width() for b in buttons)
                view_buttons=app.explanation.tabs.buttons
                report['view_buttons_equal']=abs(view_buttons[0].winfo_width()-view_buttons[1].winfo_width())<=2
                report['selection_guide_ready']=bool(app.action_guide.get())
                report['key_not_in_config']=not any('key' in k.casefold() for k in app.config)
                if not all(report[k] for k in ('display_settings_opened','guidance_preferences_saved','guidance_preferences_restored','hover_help_visible','hover_help_expires','hover_help_disabled','selection_guide_ready','key_not_in_config')):
                    raise RuntimeError('操作ガイドの確認に失敗しました: '+str(report))
                from .mascot_smoke import verify_mascot
                report.update(verify_mascot(app))
                if not report['mascot_setting_saved']:raise RuntimeError('キャラクターの設定を保存できませんでした。')
                report['callback_errors']=callback_errors
                if not report['header_buttons_visible'] or not report['view_buttons_equal'] or callback_errors or report['sidebar_width']<180 or report['panel_width']<250 or not report['folder_tree_loaded'] or not report['explanation_prepared']:
                    raise RuntimeError('追加パネルの確認に失敗しました: '+str(report))
                if os.name=='nt':
                    from .console_smoke import verify_console
                    report.update(verify_console(app,directory,Path(args.smoke_test).with_name(Path(args.smoke_test).stem+'-terminal.png')))
                    if callback_errors:raise RuntimeError('PowerShellのGUI操作に失敗しました: '+str(callback_errors))
                    from .folder_removal import recycle_registered, identity, hide_missing
                    from .updating import atomic_json
                    probe=directory/'GitTotte-recycle-smoke';probe.mkdir()
                    (probe/'日本語.txt').write_text('recoverable',encoding='utf-8')
                    atomic_json(app.project.base/'records'/'recycle-smoke.json',{'folder':str(probe),'sha':ids[0],'kind':'snapshot','created':'2026-11-04T12:00:00'})
                    destination=recycle_registered(app.project,probe,identity(probe))
                    report['folder_recycle_preserved_data']=bool(destination and not probe.exists() and (Path(destination)/'日本語.txt').read_text(encoding='utf-8')=='recoverable')
                    hide_missing(app.project,app.current,probe);app.load_folders()
                    report['missing_folder_removed']=not app.project.snapshots()
                    if not report['folder_recycle_preserved_data'] or not report['missing_folder_removed']:raise RuntimeError('フォルダーのごみ箱移動と一覧整理の確認に失敗しました。')

            report['history_size']=app.history.winfo_geometry()
            Path(args.smoke_test).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            root.destroy()
            smoke_config.cleanup()
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
            try:messagebox.showerror('GitTotteを起動できませんでした','起動記録を保存しました。\n'+str(path),parent=root)
            except Exception:pass
        if root:
            try:root.destroy()
            except Exception:pass
        return 1
