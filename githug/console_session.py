"""A single owned ConPTY session. No Tk calls in worker threads."""
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time
import uuid
from .terminal import powershell_arguments

class PromptFilter:
    """Remove only our own unpredictable prompt marker, across read boundaries."""
    def __init__(self,marker):self.marker=marker;self.pending=''
    def feed(self,text,final=False):
        text=self.pending+text;self.pending=''
        ready=self.marker in text;text=text.replace(self.marker,'')
        if not final:
            for size in range(min(len(text),len(self.marker)-1),0,-1):
                if text.endswith(self.marker[:size]):
                    self.pending=text[-size:];text=text[:-size];break
        return text,ready


def startup_script(marker,command_dir):
    literal=str(command_dir).replace("'","''")
    # Files are read as text, then immediately removed; no execution-policy changes.
    return ("$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)\n"
            "Remove-Module PSReadLine -ErrorAction SilentlyContinue\n"
            "function global:prompt { [Console]::Write([Environment]::NewLine + '"+marker+"'); 'PS ' + (Get-Location).Path + '> ' }\n"
            "function global:Get-GitHugCommand([string]$id) {\n"
            " if ($id -notmatch '^[a-f0-9]{32}$') { throw 'Invalid command id' }\n"
            " $p = [IO.Path]::Combine('"+literal+"', $id + '.txt')\n"
            " $s = [IO.File]::ReadAllText($p, [Text.Encoding]::UTF8)\n"
            " [IO.File]::Delete($p)\n"
            " [scriptblock]::Create($s)\n}\n")

class ConsoleSession:
    def __init__(self,folder,rows=12,columns=100):
        self.folder=str(Path(folder).resolve(strict=True))
        if not Path(self.folder).is_dir():raise ValueError('作業場所にはフォルダーを選んでください。')
        self.marker='__GH_'+uuid.uuid4().hex+'__'
        self.events=queue.Queue(maxsize=128);self.inputs=queue.Queue(maxsize=64)
        self.stopping=threading.Event();self.finished=threading.Event()
        self.ready=False;self.job=None;self.pid=None;self.rows=rows;self.columns=columns
        self.error=None;self._temporary=None;self._command_lock=threading.Lock()
        self.worker=threading.Thread(target=self._run,daemon=True)
        self.worker.start()

    @property
    def active(self):return not self.finished.is_set()

    def _emit(self,kind,value=None):
        while not self.stopping.is_set():
            try:self.events.put((kind,value),timeout=.05);return
            except queue.Full:continue

    def _run(self):
        pty=None;job=None
        try:
            if os.name!='nt':raise RuntimeError('埋め込みPowerShellはWindowsで利用できます。')
            try:
                from winpty import PTY
                from winpty.enums import Backend
            except ImportError:raise RuntimeError('ターミナル用の部品がありません。python -m pip install -r requirements.txt を実行してください。') from None
            from .process_job import ProcessJob
            self._temporary=tempfile.TemporaryDirectory(prefix='GitHug-commands-')
            script=startup_script(self.marker,self._temporary.name)
            args,directory=powershell_arguments(self.folder,script)
            args.insert(1,'-NoProfile');args.insert(1,'-NoLogo')
            pty=PTY(self.columns,self.rows,backend=Backend.ConPTY)
            pty.spawn(args[0],cwd=str(directory),cmdline=' '+subprocess.list2cmdline(args[1:]))
            self.pid=pty.pid
            job=ProcessJob(self.pid);self.job=job
            self._emit('started',self.pid)
            dead_since=None
            while not self.stopping.is_set():
                for _ in range(16):
                    try:kind,value=self.inputs.get_nowait()
                    except queue.Empty:break
                    if kind=='write':pty.write(value)
                    else:pty.set_size(value[1],value[0])
                output=pty.read(blocking=False)
                if output:
                    for start in range(0,len(output),8192):self._emit('output',output[start:start+8192])
                alive=pty.isalive()
                if not alive:
                    if dead_since is None:dead_since=time.monotonic()
                    if not output and time.monotonic()-dead_since>.25:break
                if not output:self.stopping.wait(.01)
        except Exception as exc:
            if not self.stopping.is_set():self.error=str(exc);self._emit('error',self.error)
        finally:
            self.ready=False
            # Keep ownership until all descendants have been terminated, including background jobs.
            if job:
                try:job.terminate()
                except OSError:pass
                job.close()
            self.job=None
            if pty is not None:
                try:del pty
                except Exception:pass
            with self._command_lock:
                if self._temporary:
                    try:self._temporary.cleanup()
                    except OSError:pass
                    self._temporary=None
            self.finished.set()
            # End status must be visible even when output backpressure was released by stop().
            try:self.events.put_nowait(('ended',self.error))
            except queue.Full:pass

    def write(self,text):
        if not self.active or self.stopping.is_set():raise RuntimeError('PowerShellは終了しています。もう一度開いてください。')
        if len(text)>16000:raise ValueError('一度に送る入力は16000文字までです。')
        try:self.inputs.put_nowait(('write',text))
        except queue.Full:raise RuntimeError('入力の送信中です。少し待ってください。') from None

    def execute(self,script):
        if not self.ready:raise RuntimeError('前の処理が続いています。質問への回答は「途中の入力」から送ってください。')
        if not script.strip():return
        if len(script)>200000:raise ValueError('コマンドが長すぎます。処理を分けて実行してください。')
        with self._command_lock:
            if self._temporary is None:raise RuntimeError('PowerShellを準備中です。')
            path=Path(self._temporary.name)/(uuid.uuid4().hex+'.txt')
            path.write_text(script,encoding='utf-8')
            try:self.write('. (Get-GitHugCommand '+path.stem+')\r')
            except Exception:path.unlink(missing_ok=True);raise
            self.ready=False

    def interrupt(self):
        self.ready=False;self.write('\x03')

    def resize(self,rows,columns):
        rows=max(3,min(120,rows));columns=max(40,min(300,columns))
        if (rows,columns)==(self.rows,self.columns):return
        self.rows,self.columns=rows,columns
        if self.active:
            try:self.inputs.put_nowait(('resize',(rows,columns)))
            except queue.Full:pass

    def stop(self):
        self.ready=False;self.stopping.set()
        # Terminating the job unblocks a child stuck in console read/write.
        job=self.job
        if job:
            try:job.terminate()
            except OSError:pass
