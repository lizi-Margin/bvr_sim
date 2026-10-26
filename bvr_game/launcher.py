"""Responsive loading UI supervising one game worker, including native startup.

python -m bvr_game.launcher play --map-version VERSION --aircraft F16
The UI stays in a separate process, so Cancel works during JSON/native calls.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import json,os,queue,signal,subprocess,sys,threading,time
from .startup import PREFIX

ROOT=Path(__file__).resolve().parents[1]

class GameWorker:
    def __init__(self,args,log_root=None):
        self.directory=Path(log_root or ROOT/'game/logs/startup')/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+str(os.getpid()))
        self.directory.mkdir(parents=True,exist_ok=False)
        self.messages=queue.Queue();self.process=None;self.reader=None
        self.started=time.monotonic();self.loading_started=self.started;self.cancelled=False;self.ready=False
        self.status={'status':'starting','launcher_pid':os.getpid(),'arguments':list(args),'python':sys.executable}
        self._save()
        env=os.environ.copy();env['BVR_GAME_STARTUP_PROGRESS']='1';env['BVR_GAME_STARTUP_WORKER']='1';env['PYTHONUTF8']='1';env['PYTHONUNBUFFERED']='1'
        if getattr(sys,'frozen',False):
            command=[sys.executable,'--bvr-game-worker',*args]
        else:
            command=[sys.executable,'-u','-X','utf8','-m','bvr_game',*args]
        options={'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP | (getattr(subprocess,'CREATE_NO_WINDOW',0) if getattr(sys,'frozen',False) else 0)} if os.name=='nt' else {'start_new_session':True}
        self.process=subprocess.Popen(command,cwd=ROOT,env=env,
            stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8',errors='replace',**options)
        self.status['worker_pid']=self.process.pid;self._save()
        self.reader=threading.Thread(target=self._read,daemon=True);self.reader.start()

    def _save(self):
        self.status['elapsed_seconds']=round(time.monotonic()-self.started,3)
        pending=self.directory/'status.pending.json'
        pending.write_text(json.dumps(self.status,ensure_ascii=False,indent=2),encoding='utf8')
        target=self.directory/'status.json'
        for attempt in range(5):
            try:
                pending.replace(target)
                break
            except PermissionError:
                if attempt==4:raise
                time.sleep(.02*(attempt+1))

    def _read(self):
        with (self.directory/'worker.log').open('w',encoding='utf8') as log, (self.directory/'events.jsonl').open('w',encoding='utf8') as events:
            for line in self.process.stdout:
                log.write(line);log.flush()
                if line.startswith(PREFIX):
                    try:message=json.loads(line[len(PREFIX):])
                    except json.JSONDecodeError:continue
                    events.write(json.dumps({'received_seconds':round(time.monotonic()-self.started,3),**message},ensure_ascii=False)+'\n');events.flush()
                    self.messages.put(message)
        self.process.stdout.close()

    def update(self):
        changed=False
        while True:
            try:message=self.messages.get_nowait()
            except queue.Empty:break
            changed=True
            self.status['stage']=message['stage'];self.status['message']=message['message']
            if message['stage']=='ready':
                self.ready=True;self.status['status']='ready'
                self.status['ready_seconds']=round(time.monotonic()-self.started,3)
                self.status.setdefault('first_ready_seconds',self.status['ready_seconds'])
            elif message['stage']=='loading_map':
                self.ready=False;self.status['status']='loading_map'
                self.loading_started=time.monotonic()
        code=self.process.poll()
        if code is not None:
            self.status['return_code']=code
            self.status['status']='cancelled' if self.cancelled else ('exited' if code==0 else 'failed')
            changed=True
        if changed:self._save()
        return code

    def cancel(self):
        """Stop only our exact child; do not depend on it handling Ctrl-C."""
        self.cancelled=True
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=1.)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=2.)
        self.status['status']='cancelled';self._save()


def main(args=None):
    # Create the UI before importing any native module or reading any map.
    import tkinter as tk
    from tkinter import ttk
    root=tk.Tk();root.title('BVR SIM | 正在启动');root.geometry('580x245');root.resizable(False,False)
    # Native device/scene setup can briefly show a non-pumping game window.
    # Keep the independent Cancel UI above it until the first frame completes.
    root.attributes('-topmost',True)
    root.configure(background='#172028')
    title=tk.Label(root,text='正在启动 Flight Operations',font=('Microsoft YaHei UI',16),background='#172028',foreground='#ffffff')
    title.pack(pady=(22,12))
    message=tk.StringVar(value='正在启动游戏进程…')
    tk.Label(root,textvariable=message,font=('Microsoft YaHei UI',11),background='#172028',foreground='#dfe4e5',wraplength=540).pack()
    bar=ttk.Progressbar(root,mode='indeterminate',length=520);bar.pack(pady=16);bar.start(12)
    detail=tk.StringVar(value='大型地图需要加载一段时间。关闭此窗口或点击取消可立即停止。')
    tk.Label(root,textvariable=detail,font=('Microsoft YaHei UI',9),background='#172028',foreground='#a4afb4',wraplength=540).pack()
    worker=None;exit_code=0;interrupt=False;failed=False
    def cancel():
        nonlocal exit_code
        if worker is not None and worker.process.poll() is None:worker.cancel()
        exit_code=130 if not failed else 1
        root.destroy()
    button=ttk.Button(root,text='取消启动',command=cancel);button.pack(pady=12)
    root.protocol('WM_DELETE_WINDOW',cancel)
    root.bind('<Escape>',lambda event:cancel())
    def sigint(signum,frame):
        nonlocal interrupt
        interrupt=True
    signal.signal(signal.SIGINT,sigint)
    if hasattr(signal,'SIGBREAK'):signal.signal(signal.SIGBREAK,sigint)
    def show_failure(error):
        nonlocal failed,exit_code
        failed=True;exit_code=1;root.deiconify();root.title('BVR SIM | 启动失败')
        title.configure(text='游戏启动失败');bar.stop()
        message.set(str(error));button.configure(text='关闭')
        if worker:detail.set('详细日志：'+str(worker.directory/'worker.log'))
    def poll():
        if interrupt:cancel();return
        if worker is not None:
            code=worker.update()
            message.set(worker.status.get('message','正在加载游戏模块…'))
            if code is not None:
                if code==0:root.destroy();return
                if not failed:show_failure('游戏进程退出（代码 '+str(code)+'），请查看下方日志。')
                root.after(100,poll);return
            if worker.ready:root.withdraw()
            else:
                if root.state()=='withdrawn':root.deiconify()
                if worker.status['status']=='loading_map':button.configure(text='取消加载并退出')
                root.title(f'BVR SIM | 正在加载 · {time.monotonic()-worker.loading_started:.0f}秒')
        root.after(100,poll)
    def start():
        nonlocal worker
        try:worker=GameWorker(sys.argv[1:] if args is None else args)
        except Exception as error:show_failure(error);return
        if not getattr(sys,'frozen',False):
            encoding=sys.stdout.encoding or 'utf-8'
            log_location=str(worker.directory).encode(encoding,errors='backslashreplace').decode(encoding)
            print('Startup log: '+log_location,flush=True)
        poll()
    root.after(50,start)
    try:root.mainloop()
    finally:
        if worker and worker.process.poll() is None:worker.cancel()
        if worker and worker.reader:worker.reader.join(timeout=1.)
    return exit_code

if __name__=='__main__':raise SystemExit(main())
