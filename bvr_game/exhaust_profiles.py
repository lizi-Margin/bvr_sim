"""Source-backed exhaust display metadata; never changes a flight model."""
from pathlib import Path
import argparse,json,math,xml.etree.ElementTree as ET
from .content import ROOT,sha,write_json

DEFAULT=ROOT/'game/config/aircraft_exhaust_profiles.json'
RESOURCES=ROOT/'bvr_sim/resources'


def inspect_fdm(path,resource_root=RESOURCES):
    path=Path(path);sources={};unresolved=[]
    def load(file):
        file=file.resolve();sources[str(file.relative_to(ROOT)) if file.is_relative_to(ROOT) else str(file)]=sha(file)
        return ET.parse(file).getroot()
    def resolve(name,parent):
        name=name if name.endswith('.xml') else name+'.xml'
        candidates=[parent/name,parent/'Engines'/name,parent/'Systems'/name,Path(resource_root)/'jsbsim/engine'/name]
        return next((p for p in candidates if p.is_file()),None)
    root=load(path);engines=[]
    if root.tag=='airplane':
        for index,jet in enumerate(root.findall('jet')):
            thrust=float(jet.get('thrust','0'));reheat=float(jet.get('afterburner','0'))
            if not math.isfinite(thrust+reheat):raise ValueError('Nonfinite source jet thrust')
            outputs=[o for o in jet.findall('control-output') if o.get('control')=='REHEAT' and o.get('prop')]
            supported=reheat>thrust>0
            output=next((o for o in outputs if float(o.get('min','0'))==0 and float(o.get('max','1'))==1),None)
            mode='property' if supported and output is not None else 'unavailable' if supported else 'disabled'
            engines.append({'engine_index':index,'type':'yasim-jet','afterburner_declared':supported,'mode':mode,
                'property':output.get('prop') if mode=='property' else '',
                'reason':'Declared normalized REHEAT output' if mode=='property' else 'Declared afterburner without normalized snapshot output' if supported else 'No source afterburner thrust declared',
                'source_thrust':thrust,'source_afterburner_thrust':reheat})
        if not engines:unresolved.append('No jet elements; no jet flame inferred for propellers or other sources')
    else:
        propulsion=root.find('propulsion');parent=path.parent
        if propulsion is not None and propulsion.get('file'):
            file=resolve(propulsion.get('file'),parent)
            if file:propulsion=load(file);parent=file.parent
            else:unresolved.append('Unresolved propulsion file: '+propulsion.get('file'));propulsion=None
        for index,engine in enumerate(propulsion.findall('engine') if propulsion is not None else []):
            file=resolve(engine.get('file',''),parent);definition=load(file) if file else None
            augmented=float(definition.findtext('augmented','0')) if definition is not None else None
            engines.append({'engine_index':index,'type':definition.tag if definition is not None else 'unresolved-jsbsim-engine',
                'afterburner_declared':augmented>0 if augmented is not None else None,
                'mode':'disabled' if augmented==0 else 'unavailable','property':'',
                'reason':'Source engine has no augmentation' if augmented==0 else 'JSBSim augmentation state is not currently exported in the existing visual snapshot' if augmented is not None else 'Engine definition could not be resolved',
                'source_engine_file':engine.get('file','')})
        if not engines:unresolved.append('No resolved propulsion engines; no flame inferred')
    return {'engines':engines,'sources':sources,'unresolved':unresolved}


def build_document():
    # This policy covers the imported appearances. The ordinary F22/F16's
    # existing separate throttle effect remains explicitly outside this policy.
    catalog_path=RESOURCES/'imported_aircraft_catalog.json';catalog=json.loads(catalog_path.read_text(encoding='utf8'))
    rows={}
    for aircraft in catalog['aircraft']:
        path=RESOURCES/aircraft['fdm']['file']
        if sha(path)!=aircraft['fdm']['sha256']:raise ValueError('Source FDM hash changed: '+aircraft['id'])
        rows[aircraft['appearance']['asset_id']]={'source_aircraft':aircraft['id'],**inspect_fdm(path)}
    return {'schema_version':1,'generator_sha256':sha(Path(__file__)),'catalog_sha256':sha(catalog_path),
        'scope':'Imported appearances only. Explicit source capability and existing normalized REHEAT snapshot property required. Missing data disables a visual effect; it does not classify a real engine as dry. No thrust, physics, controller, sound or source geometry changes. Ordinary F22/F16 retain their separately documented legacy effect.',
        'intensity_units':'Existing source REHEAT output clamped to0..1; display opacity/emission are engineering approximations, not exhaust temperature or measured radiance.',
        'aircraft':rows}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['build','validate','show'])
    p.add_argument('asset',nargs='?');p.add_argument('--file',type=Path,default=DEFAULT);a=p.parse_args()
    if a.action=='build':
        document=build_document();write_json(a.file,document)
        modes={k:sum(e['mode']==k for r in document['aircraft'].values() for e in r['engines']) for k in ['property','disabled','unavailable']}
        print(json.dumps({'file':str(a.file),'sha256':sha(a.file),'appearances':len(document['aircraft']),'engines_by_mode':modes}))
    elif a.action=='validate':
        assert json.loads(a.file.read_text(encoding='utf8'))==build_document(),'Source/profile drift; regenerate and review'
        print(json.dumps({'status':'passed','file_sha256':sha(a.file)}))
    else:print(json.dumps(json.loads(a.file.read_text(encoding='utf8'))['aircraft'][a.asset],indent=2))


if __name__=='__main__':main()
