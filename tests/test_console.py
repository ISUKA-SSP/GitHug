import os
from pathlib import Path
import queue
import sys
import tempfile
import time
import unittest
import pyte
from githug.console_session import PromptFilter, ConsoleSession
from githug.console_screen import ConsoleScreen

class ScreenTests(unittest.TestCase):
    def test_prompt_marker_split_at_every_boundary(self):
        marker='__GH_abcdef__'
        for i in range(1,len(marker)):
            f=PromptFilter(marker)
            a,ready1=f.feed('before'+marker[:i]);b,ready2=f.feed(marker[i:]+'after')
            self.assertEqual(a+b,'beforeafter');self.assertFalse(ready1);self.assertTrue(ready2)
        f=PromptFilter(marker);a,_=f.feed('text__GH_ab');b,_=f.feed('',final=True)
        self.assertEqual(a+b,'text__GH_ab')

    def test_vt_cursor_progress_unicode_and_response(self):
        replies=[];s=ConsoleScreen(80,8,replies.append);stream=pyte.Stream(s)
        stream.feed('download 1%\rdownload 100%\x1b[K\r\n日本語\r\n\x1b[31mERROR\x1b[0m')
        self.assertIn('download 100%',s.text());self.assertIn('日本語',s.text());self.assertNotIn('\x1b',s.text())
        stream.feed('\x1b[6n');self.assertTrue(replies[-1].endswith('R'))
        for _ in range(1800):stream.feed('\r\nline')
        self.assertLessEqual(len(s.history.top),1500)

@unittest.skipUnless(os.name=='nt','Windows ConPTY integration')
class WindowsConsoleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='GitHug-console-test-')
        self.folder=Path(self.temp.name)/"日本語 [folder] ' quote";self.folder.mkdir()
        self.addCleanup(self.temp.cleanup)
        self.session=ConsoleSession(self.folder,rows=25,columns=140)
        self.addCleanup(self.cleanup_session)
        self.filter=PromptFilter(self.session.marker)
        self.screen=ConsoleScreen(140,25,self.session.write);self.stream=pyte.Stream(self.screen)
        self.output=''
        self.wait(lambda:self.session.ready,20)

    def cleanup_session(self):
        self.session.stop();self.assertTrue(self.session.finished.wait(8),'console did not stop')

    def pump(self):
        for _ in range(64):
            try:kind,value=self.session.events.get_nowait()
            except queue.Empty:break
            if kind=='error':self.fail(value)
            if kind=='output':
                value,ready=self.filter.feed(value);self.stream.feed(value);self.output+=value
                if ready:self.session.ready=True

    def wait(self,predicate,timeout=15):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            self.pump()
            if predicate():return
            if self.session.finished.is_set():self.fail('console exited: '+str(self.session.error)+'\n'+self.output[-3000:])
            time.sleep(.02)
        self.fail('timeout\n'+self.output[-3000:])

    def test_multiline_readhost_python_and_session_variables(self):
        self.session.execute("$label='日本語'; Write-Output ('LOCATION:'+(Get-Location).Path)\n$answer=Read-Host 'QUESTION_MARKER'\nWrite-Output ('ANSWER:'+$label+':'+$answer)")
        self.wait(lambda:'QUESTION_MARKER' in self.output)
        self.assertFalse(self.session.ready)
        self.session.write('はい\r');self.wait(lambda:self.session.ready and 'ANSWER:日本語:はい' in self.output)
        self.assertIn(str(self.folder),self.screen.text())
        self.session.execute("Write-Output ('RETAINED:'+$label)")
        self.wait(lambda:self.session.ready and 'RETAINED:日本語' in self.output)
        python=str(Path(sys.executable)).replace("'","''")
        self.session.execute("& '"+python+"' -u -c 'v=input(\"PYQUESTION:\");print(\"PYANSWER:\"+v)'")
        self.wait(lambda:'PYQUESTION:' in self.output)
        self.session.write('回答\r');self.wait(lambda:self.session.ready and 'PYANSWER:回答' in self.output)
        self.assertFalse(list(Path(self.session._temporary.name).iterdir()),'command text should be removed before execution')

    def test_interrupt_and_terminate_descendant_process(self):
        self.session.execute("Write-Output 'SLEEP_STARTED'; Start-Sleep -Seconds 60")
        self.wait(lambda:'SLEEP_STARTED' in self.output)
        self.session.interrupt();self.wait(lambda:self.session.ready)
        pid_file=Path(self.temp.name)/'child.pid';quoted=str(pid_file).replace("'","''")
        self.session.execute("$p=Start-Process powershell.exe -ArgumentList '-NoProfile','-Command','Start-Sleep -Seconds 60' -NoNewWindow -PassThru\n$p.Id | Set-Content -LiteralPath '"+quoted+"'\nStart-Sleep -Seconds 60")
        self.wait(lambda:pid_file.exists() and bool(pid_file.read_text().strip()))
        pid=int(pid_file.read_text().strip());self.session.stop()
        self.assertTrue(self.session.finished.wait(8))
        import ctypes
        from ctypes import wintypes
        api=ctypes.WinDLL('kernel32',use_last_error=True)
        api.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];api.OpenProcess.restype=wintypes.HANDLE
        api.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        api.CloseHandle.argtypes=[wintypes.HANDLE]
        handle=api.OpenProcess(0x1000,False,pid)
        if handle:
            try:
                code=wintypes.DWORD();self.assertTrue(api.GetExitCodeProcess(handle,ctypes.byref(code)))
                self.assertNotEqual(code.value,259,'child process survived console shutdown')
            finally:api.CloseHandle(handle)
