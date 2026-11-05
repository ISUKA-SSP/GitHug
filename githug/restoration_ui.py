"""Review exact new destination before restoring; never reuses an existing folder."""
from .restoration import execute_restore
from .operation_guide import begin as guide_begin, finish as guide_finish
from .terminology import messagebox


def start_restore(app,project,prepare,parent=None,after=None,notice=''):
    if app.busy:return
    parent=parent or app.window
    def prepared(plan):
        if not parent.winfo_exists():return
        source=('PCの記録：'+plan.metadata['commit'][:12]+'\n'+plan.metadata.get('message','')) if plan.kind=='local' else 'バックアップ：'+plan.source.name
        text=source+f'\n\nファイル：{plan.count:,} 件 ／ 内容のサイズ：{plan.size/(1024*1024):.1f} MB'
        text+='\n\n新しく作るフォルダー：\n'+str(plan.destination)+'\n\n元のフォルダー・バックアップ・PCの記録は変更しません。復元した内容を自動で実行することもありません。'
        if notice:text+='\n\n'+notice
        text+='\n\nこの場所へ復元しますか？'
        if not messagebox.askyesno('新しいフォルダーへ復元',text,parent=parent,default='no'):return
        ticket=guide_begin(app,'restore-'+plan.kind,project)
        def done(result):
            folder=result['folder']
            guide_finish(ticket,'記録した内容を、新しいフォルダーへ復元しました。\n'+folder+('\n'+result['warning'] if result['warning'] else ''))
            if app.project is project:
                app.folder_query.set('');app.load_folders()
                for item in app.folders.get_children():
                    if app.folders.item(item,'values')[1]==folder:
                        app.folders.selection_set(item);app.folders.focus(item);app.folders.see(item);break
                app.status.set('新しいフォルダーに復元しました：'+folder)
            text=folder+'\n\n'+('PCのフォルダー一覧に追加しました。「フォルダーを開く」から中身を確認できます。' if result['registered'] else '')
            if result['warning']:text+='\n\n'+result['warning']
            messagebox.showinfo('新しいフォルダーに復元しました',text,parent=parent if parent.winfo_exists() else app.window)
            if after and app.project is project:after(folder)
        app.run('新しいフォルダーへ復元しています…',lambda:execute_restore(project,plan,lambda note:setattr(app,'operation_note',note)),done)
    app.run('復元元と保存場所を確認しています…',prepare,prepared)
