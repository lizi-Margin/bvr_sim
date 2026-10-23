"""Client journal around the core's real ACMI/log streams; no simulated states invented."""
from datetime import datetime,timezone
from pathlib import Path
import json,os,time,uuid

def utc():return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def atomic_json(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8');tmp.replace(path)

class SortieJournal:
    def __init__(self,session,root):
        self.session=session;self.root=Path(root).resolve();self.current=None;self.last=None;self.stream=None;self.actions=0;self.last_flush=0.
    def paths(self):
        return {'root':str(self.root),'current':str(self.current['directory']) if self.current else None,'recent':str(self.last) if self.last else None}
    def start(self,config,context):
        if self.current:raise RuntimeError('Finish the previous sortie before starting another')
        id=datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-'+uuid.uuid4().hex[:12]
        directory=self.root/id
        try:
            directory.mkdir(parents=True,exist_ok=False)
            data={'sortie_id':id,'directory':str(directory),'started_at':utc(),'ended_at':None,'status':'running','config':config,'context':context,'acmi':str(directory/'battle.acmi'),'core_log':str(directory/'core.log'),'input_tape':str(directory/'input-tape.json'),'incremental_input_tape':str(directory/'input-tape.jsonl'),'result':'running','exception':None}
            self.current=data;self.actions=0
            atomic_json(directory/'sortie.json',data)
            self.stream=(directory/'input-tape.jsonl').open('w',encoding='utf8')
            self.session.begin_recording(data['core_log'],data['acmi'],data['started_at'])
            self.last_flush=time.monotonic()
        except Exception as error:
            self.finish('logging_error',error=str(error))
            raise RuntimeError(f'Cannot start sortie logs in {directory}: {error}') from error
        return self.paths()
    def record(self,kind,value,tick):
        if not self.current:return
        try:
            self.stream.write(json.dumps({'tick':tick,'kind':kind,'value':value},ensure_ascii=False,separators=(',',':'))+'\n');self.actions+=1
            if time.monotonic()-self.last_flush>=1:
                self.stream.flush();self.last_flush=time.monotonic()
        except Exception as error:raise RuntimeError(f'Input journal write failed: {self.current["incremental_input_tape"]}: {error}') from error
    def finish(self,reason,frame=None,error=None):
        if not self.current:return
        data=self.current;directory=Path(data['directory']);failure=None
        try:self.session.end_recording()
        except Exception as e:failure=str(e)
        if self.stream:
            try:self.stream.flush();self.stream.close()
            except Exception as e:failure=(failure or '')+' '+str(e)
        self.stream=None
        data.update(ended_at=utc(),status=reason,exception=error or failure)
        if frame:
            data.update(result=frame['result'],last_tick=frame['tick'],sim_time=frame['sim_time'],last_events=frame['events'][-20:])
        try:
            rows=[]
            if (directory/'input-tape.jsonl').exists():
                rows=[json.loads(line) for line in (directory/'input-tape.jsonl').read_text(encoding='utf8').splitlines() if line]
            atomic_json(directory/'input-tape.json',{'schema_version':1,'sortie_id':data['sortie_id'],'config':data['config'],'context':data['context'],'actions':rows,'final_frame':frame})
            atomic_json(directory/'sortie.json',data)
        except Exception as e:failure=(failure or '')+f' {directory}: {e}'
        self.last=directory;self.current=None
        if failure:raise RuntimeError('Cannot finalize sortie logs: '+failure)

def open_logs_directory(paths):
    directory=Path(paths['current'] or paths['recent'] or paths['root'])
    directory.mkdir(parents=True,exist_ok=True)
    # ShellExecute via Python's path API; never concatenate shell commands.
    os.startfile(str(directory),'explore')
    return str(directory)
