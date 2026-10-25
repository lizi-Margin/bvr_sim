"""Client preferences only; no FDM parameters, time step or AI gains."""
from pathlib import Path
import json, os

DEFAULTS={'quality':'high','font_scale':1.,'mouse_sensitivity':1.,'control_mode':'assisted',
          'show_hud':True,'master_volume':.75}
CHOICES={'quality':['low','medium','high'],'font_scale':[.85,1.,1.15],
         'mouse_sensitivity':[.5,.75,1.,1.25,1.5,2.],
         'control_mode':['assisted','raw_manual'],'show_hud':[True,False],
         'master_volume':[0.,.25,.5,.75,1.]}

class ClientSettings:
    def __init__(self,path=None):
        self.path=Path(path) if path is not None else None
        self.values=dict(DEFAULTS);self.error=''
        if self.path and self.path.exists():
            try:
                data=json.loads(self.path.read_text(encoding='utf8'))
                self.values=self.validate(data['preferences'])
            except (ValueError,KeyError,TypeError,OSError) as error:self.error=str(error)
    @staticmethod
    def default_path():return Path(os.environ.get('APPDATA',Path.home()/'.config'))/'bvr_sim/client-settings.json'
    @staticmethod
    def validate(values):
        if not isinstance(values,dict) or set(values)!=set(DEFAULTS):raise ValueError('Invalid client preference fields')
        for key,value in values.items():
            if type(value) is not type(DEFAULTS[key]) or value not in CHOICES[key]:raise ValueError('Invalid client preference: '+key)
        return dict(values)
    def save(self,values):
        candidate=self.validate(values)
        if self.path:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temp=self.path.with_suffix('.tmp')
            temp.write_text(json.dumps({'schema_version':1,'preferences':candidate},indent=2)+'\n',encoding='utf8')
            os.replace(temp,self.path)
        self.values=candidate
