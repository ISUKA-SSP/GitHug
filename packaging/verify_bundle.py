"""Run the packaged EXE with isolated settings and force the bundled Git path."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

folder=Path(sys.argv[1]).resolve()
report=Path(sys.argv[2]).resolve() if len(sys.argv)>2 else folder.parent/'windows-smoke.json'
report.parent.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='GitHug-verify-') as temporary:
    env={**os.environ,'APPDATA':temporary,'GITHUG_PREFER_BUNDLED_GIT':'1',
         'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':os.devnull}
    completed=subprocess.run([str(folder/'GitHug.exe'),'--smoke-test',str(report)],cwd=folder,env=env,timeout=90)
    if not report.exists():raise RuntimeError('EXEが起動確認レポートを作成しませんでした。')
    data=json.loads(report.read_text(encoding='utf-8'))
    print(json.dumps(data,ensure_ascii=True,indent=2))
    if completed.returncode or not data.get('gui_initialized'):raise RuntimeError('EXEの起動確認に失敗しました。')
    if not all(data.get(key) for key in ('frozen','graph_items','git_roundtrip','folder_tree_loaded','explanation_prepared','explanation_panel_visible')) or data.get('callback_errors'):
        raise RuntimeError('GUI・履歴グラフ・同梱Gitの確認に失敗しました。')
    if (folder/'tools'/'git').resolve() not in Path(data['git_executable']).resolve().parents:
        raise RuntimeError('同梱Gitではなく、PC側のGitで起動してしまいました。')
