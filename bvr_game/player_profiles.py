"""Versioned, per-aircraft player assistance; independent of FDM and AI tuning."""
from __future__ import annotations
import argparse,copy,hashlib,json,math,os
from pathlib import Path
from .content import ROOT

DEFAULT=ROOT/'game/config/player_flight_profiles.json'
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')
def merge(base,overlay):
    out=copy.deepcopy(base)
    for key,value in overlay.items():
        if key=='inherits':continue
        out[key]=merge(out.get(key,{}),value) if isinstance(value,dict) else copy.deepcopy(value)
    return out

class PlayerProfileStore:
    def __init__(self,path=DEFAULT):self.path=Path(path);self.reload()
    @classmethod
    def from_document(cls,document,path=DEFAULT):
        self=cls.__new__(cls);self.path=Path(path);self.document=copy.deepcopy(document);self._validate();return self
    def reload(self):
        # Build/validate a candidate before replacing an existing good store.
        candidate=self.from_document(json.loads(self.path.read_text(encoding='utf-8-sig')),self.path)
        self.document=candidate.document;self.file_sha256=hashlib.sha256(self.path.read_bytes()).hexdigest();return self
    def _template(self,name,seen=()):
        if name in seen:raise ValueError('Cyclic player template inheritance: '+name)
        if name not in self.document['templates']:raise ValueError('Unknown player template: '+name)
        value=self.document['templates'][name];parent=value.get('inherits')
        return merge(self._template(parent,(*seen,name)) if parent else {},value)
    def resolve(self,aircraft_id):
        if aircraft_id not in self.document['aircraft']:raise ValueError('No explicit player profile assignment: '+aircraft_id)
        row=self.document['aircraft'][aircraft_id];name=row['template'];data=merge(self._template(name),row.get('overrides',{}))
        chain=[];template=name
        while template:chain.append(template);template=self.document['templates'][template].get('inherits')
        result={'aircraft_id':aircraft_id,'version':self.document['version'],'template':name,'inheritance':list(reversed(chain)),
                'tuning_status':row['tuning_status'],'assignment_basis':row['assignment_basis'],**data}
        result['effective_sha256']=hashlib.sha256(canonical(result)).hexdigest();return result
    def _validate(self):
        d=self.document
        if d.get('schema_version')!=1 or not isinstance(d.get('version'),str) or not d['version']:raise ValueError('Invalid player profile schema/version')
        required=set(d['units']['control'])
        if not required:raise ValueError('Missing player control units')
        for name in d['templates']:self._template(name)
        for id in d['aircraft']:
            p=self.resolve(id)
            if set(p['control'])!=required:raise ValueError(f'{id}: unknown/missing control fields')
            for section in ['control','input','camera']:
                if set(p[section])!=set(d['units'][section]):raise ValueError(f'{id}: unknown/missing {section} fields')
                for key,value in p[section].items():
                    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError(f'{id}: nonfinite/nonnumeric {section}.{key}')
            c=p['control'];i=p['input'];cam=p['camera']
            if not(0<c['max_bank']<1.5 and c['min_alpha']<0<c['max_alpha']<.8 and -5<c['min_g']<c['max_g']<=15
                   and 0<c['min_speed']<c['reference_speed'] and 0<c['schedule_min']<=c['schedule_max']
                   and 0<c['release_seconds']<5 and 0<c['surface_rate']<100 and 0<c['target_response']<5
                   and 0<=c['trim_limit']<=1 and 0<c['reference_density']<=2 and 0<c['energy_horizon']<=60 and 1<c['recovery_speed_ratio']<=2
                   and -.5<=c['recovery_pitch']<0 and 0<=i['deadzone']<.5 and i['sensitivity']>0
                   and i['curve']>=1 and .5<i['edge_fraction']<1 and i['edge_pan_rate']>=0
                   and 0<i['max_edge_pan']<1.5 and 0<i['edge_recenter_seconds']<5
                   and 0<i['max_target_elevation']<math.pi/2 and 0<i['direction_response']<5
                   and i['aim_distance_m']>=100 and cam['distance_spans']>0 and cam['lookahead_m']>100
                   and cam['lift_spans']>=0 and cam['smoothing_hz']>0
                   and .3<=cam['normal_fov']<=1.6 and .3<=cam['zoom_fov']<=cam['normal_fov']):
                raise ValueError(f'{id}: invalid player profile envelope/input/camera bounds')
            nonpositive=[k for k,v in c.items() if v<=0 and k not in {'min_alpha','min_g','trim_gain','trim_limit','yaw_damping','sideslip_gain','recovery_pitch'}]
            if nonpositive:raise ValueError(f'{id}: nonpositive control fields {nonpositive}')
    def native_profile(self,native,aircraft_id):
        return self.native_resolved(native,self.resolve(aircraft_id))
    def native_resolved(self,native,p):
        payload={k:v for k,v in p.items() if k!='effective_sha256'}
        if hashlib.sha256(canonical(payload)).hexdigest()!=p['effective_sha256']:raise ValueError('Recorded player profile hash mismatch')
        # Validate all effective input/camera/control fields, not just native
        # gains. The recorded inheritance metadata remains part of its hash.
        self.from_document({'schema_version':1,'version':p['version'],'units':self.document['units'],
            'templates':{'recorded':{k:p[k] for k in ['control','input','camera']}},
            'aircraft':{p['aircraft_id']:{'template':'recorded','tuning_status':p['tuning_status'],'assignment_basis':p['assignment_basis']}}},self.path)
        out=native.PlayerFlightProfile()
        out.id=p['aircraft_id'];out.version=p['version'];out.source_hash=p['effective_sha256']
        for key,value in p['control'].items():setattr(out,key,float(value))
        out.validate();return out
    def apply(self,session,native,aircraft_id):
        session.configure_player_flight(self.native_profile(native,aircraft_id));return self.resolve(aircraft_id)
    def save_override(self,aircraft_id,key,value):
        section,name=key.split('.',1)
        if section not in {'control','input','camera'} or name not in self.document['units'][section]:raise ValueError('Unknown player parameter: '+key)
        updated=copy.deepcopy(self.document)
        updated['aircraft'][aircraft_id].setdefault('overrides',{}).setdefault(section,{})[name]=float(value)
        candidate=self.from_document(updated,self.path)
        temp=self.path.with_name(self.path.name+'.tmp-'+str(os.getpid()))
        try:temp.write_text(json.dumps(candidate.document,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temp.replace(self.path)
        finally:
            if temp.exists():temp.unlink()
        self.reload();return self.resolve(aircraft_id)
    def export(self):return {'schema_version':1,'version':self.document['version'],'source_file':str(self.path),'file_sha256':getattr(self,'file_sha256',hashlib.sha256(canonical(self.document)).hexdigest()),'units':self.document['units'],'aircraft':[self.resolve(k) for k in self.document['aircraft']]}
    def describe(self,aircraft_id):
        return {'profile':self.resolve(aircraft_id),'units':self.document['units'],
            'source_file':str(self.path),'file_sha256':self.file_sha256}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['show','validate','list','set']);p.add_argument('aircraft',nargs='?');p.add_argument('--file',type=Path,default=DEFAULT);p.add_argument('--key');p.add_argument('--value',type=float);args=p.parse_args();store=PlayerProfileStore(args.file)
    if args.action=='show':result=store.describe(args.aircraft)
    elif args.action=='set':result=store.save_override(args.aircraft,args.key,args.value)
    elif args.action=='list':result=[{'aircraft_id':k,'template':v['template'],'tuning_status':v['tuning_status']} for k,v in store.document['aircraft'].items()]
    else:
        from .aircraft import aircraft_catalog
        ids={x['id'] for x in aircraft_catalog(include_library=True)['aircraft']}
        missing=ids-set(store.document['aircraft']);extra=set(store.document['aircraft'])-ids
        if missing or extra:raise ValueError(f'Catalog/profile mismatch: missing={missing},extra={extra}')
        result={'status':'passed','count':len(ids),'file_sha256':store.file_sha256}
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
