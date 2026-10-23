"""Create/bake the river-valley airfield through the existing registered Baker."""
from pathlib import Path
import argparse,json,sys,hashlib,shutil,uuid
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import write_json

def recipe():
    r=json.loads((ROOT/'game/recipes/training_range_v3.json').read_text(encoding='utf-8'))
    r.update(name='river_valley_airfield',seed=3124,height_spacing_m=25,field_spacing_m=750,
        field_palette_linear=[[.88,.87,.71,1],[.76,.84,.67,1],[.91,.83,.67,1],[.67,.77,.61,1]])
    r['landscape']={'version':1,'feature_extent_km':[8,8],'feature_center':[-1000,-2200],
        'valley_base_rise_m':95,'valley_scale_m':1800,'ridge_amplitude_m':450,'ridge_start_m':2200,
        'ridge_scale_m':6000,'undulation_m':35,'earthwork_blend_m':180,'regional_transition_m':1200,'macro_resolution':4096,
        'generator':'Seeded river valley and local runway/apron earthworks; source BVR terrain retained beyond20km focus',
        'individual_building_tuning':'Road frontages and source-bound footprint foundations; no region-wide settlement/industry flattening'}
    r['terrain']['airport_height_m']=220
    r['budgets']['vegetation_instances']=20000
    r['materials']['farmland']['color']=[.98,.94,.83,1]
    r['materials']['forest']['color']=[.7,.76,.6,1]
    r['airfields'][0].update(runway_width_m=45,taxi_offset_m=160,apron=[-2200,-3000],apron_size_m=[1100,400],hangars=6)
    r['rivers'][0].update(width_m=95,bank_width_m=120,points=[[-80000,600],[-10000,600],[-7000,820],[-5200,510],[-3400,140],[-1800,280],[-400,700],[1100,820],[2500,600],[4200,200],[6000,430],[8200,900],[10000,600],[80000,600]])
    r['roads']=[
        {'id':'airport_village','width_m':8,'points':[[-1400,-3000],[-1150,-2500],[-700,-2300],[-800,-4600],[-2100,-5000],[-3500,-5400]]},
        {'id':'village_link','width_m':9,'points':[[-3500,-5400],[-2500,-5100],[-800,-4600],[300,-4200],[1400,-2700],[2300,-2000],[2450,-600],[2500,600],[2800,1800],[4500,2400]]},
        {'id':'north_town','width_m':8,'points':[[1400,-2700],[2200,-3200],[3300,-2700],[4300,-1800],[6000,-1600],[8800,-1100]]},
        {'id':'regional_highway','width_m':12,'points':[[-10000,-7100],[-6500,-6300],[-3500,-5400],[-800,-4600],[1400,-2700],[3300,-2700],[6000,-1600],[10000,-600]]},
        {'id':'industrial_service','width_m':8,'points':[[2300,-2000],[2600,-1900],[2850,-1700],[2900,-1000]]},
        {'id':'industrial_cross','width_m':7,'points':[[2450,-2050],[2450,-1500],[2700,-1300],[2900,-1000]]},
        {'id':'south_lane','width_m':5,'points':[[-4100,-5700],[-3650,-5600],[-3300,-6000],[-2400,-6100]]},
        {'id':'town_lane','width_m':5,'points':[[2900,-3100],[3150,-3300],[3700,-3150],[4100,-2700]]}]
    r['settlements']=[{'id':'south_village','center':[-3500,-5400],'road':'village_link','houses':75,'radius_m':850,'height_m':250},
        {'id':'north_town','center':[3300,-2700],'road':'north_town','houses':90,'radius_m':1050,'height_m':210},
        {'id':'south_hamlet','center':[-3300,-6000],'road':'south_lane','houses':22,'radius_m':480,'height_m':250},
        {'id':'town_hamlet','center':[3700,-3150],'road':'town_lane','houses':24,'radius_m':450,'height_m':210}]
    for z in r['zones']:
        if z['type']=='industrial':z['polygon']=[[2100,-2200],[3100,-2050],[3200,-800],[2300,-700]]
        if z['id']=='sample_woodland':z['polygon']=[[-3900,-2200],[-3300,-1850],[-1900,-1800],[-1200,-2100],[-2000,-2400]]
    r['zones'].append({'id':'valley_west_woodland','type':'forest','polygon':[[-6500,-2200],[-4200,-1500],[-2500,-1800],[-1800,-800],[-400,-700],[-1000,-1800],[-3500,-2500],[-5300,-2900]]})
    for scatter in r['scatter_rules']:
        if scatter['id']=='forest_canopy':scatter['count']=15000;scatter['zones'].extend(['valley_west_woodland','sample_woodland'])
        elif scatter['id']=='riverbank_vegetation':scatter['count']=3000
        elif scatter['id']=='hedgerows':scatter['count']=1400
        elif scatter['id']=='sample_woodland':scatter['count']=400
    r['mission'].update(player_start=[-7000,-3500,650],speed_mps=180,enemy_range_m=160000,target=[2650,-1400])
    if 'convoy_target' in r['mission']:r['mission']['convoy_target']=[2600,-1900]
    r['mission']['ground_units']=[]
    r['detail_sample'].update(center=[-2500,-3000],size_m=[2000,2000],relief_amplitude_m=1.2,texture_resolution=2048,material_blend_m=24,
        roadside_signs=[{'position':[-1390,-2990],'yaw':0},{'position':[-790,-4590],'yaw':1.4}])
    r['exclusion_zones'][1].update(center=[-2200,-3000],size_m=[1250,600])
    r['bridges']=[{'id':'valley_crossing','road':'village_link','center':[2500,600],'length_m':480,'width_m':10,'ramp_length_m':100,'deck_height_m':140}]
    r['gates']=[]
    r['display_flight']={'minimum_seconds':180,'waypoints_nwu':[[-4500,-3500,550],[-2200,-2900,480],[0,-800,400],[2200,600,380],[3700,-2300,520],[5200,-1800,750],[7500,-1000,1200]],
        'sequence':['airfield','river_valley_low','town_turn','climb','observed_contact_approach'],'contact_rule':'Only true radar tracks may be selected; no hidden enemy coordinates'}
    return r

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bake',action='store_true');p.add_argument('--output',type=Path,default=ROOT/'game/maps/river_valley_airfield');a=p.parse_args()
    r=recipe();path=ROOT/'game/recipes/river_valley_airfield.json';write_json(path,r)
    if a.bake:
        from bvr_game.worldgen import Baker
        from bvr_game.scene_runtime import BakedScene
        from bvr_game.content import sha
        import numpy as np
        # Complete and verify an immutable data version before publishing one
        # root map pointer. A failed bake cannot corrupt the last working map.
        a.output=a.output.resolve();stage=a.output/('._bake-'+uuid.uuid4().hex)
        report=Baker(r).bake(stage)
        doc=json.loads((stage/'generated-map.json').read_text(encoding='utf-8'))
        arrays=np.load(stage/'terrain.npz',allow_pickle=False);fine=arrays['sample']
        if not np.isfinite(fine).all() or max(np.max(abs(np.diff(fine,axis=0))),np.max(abs(np.diff(fine,axis=1))))>25:
            raise ValueError('Airfield fine terrain contains a nonphysical discontinuity; failed staging data retained')
        def relocate(value,destination):
            if isinstance(value,str):return value.replace(str(stage),destination)
            if isinstance(value,list):return [relocate(v,destination) for v in value]
            if isinstance(value,dict):return {k:relocate(v,destination) for k,v in value.items()}
            return value
        normalized=json.dumps(relocate(doc,'<MAP_VERSION>'),sort_keys=True,separators=(',',':')).encode('utf-8')
        id=hashlib.sha256(normalized).hexdigest()[:24];version=a.output/'versions'/id;version.mkdir(parents=True,exist_ok=True)
        for file in stage.iterdir():
            if not file.is_file() or file.name=='generated-map.json':continue
            dest=version/file.name
            if dest.exists() and sha(dest)!=sha(file):raise ValueError('Immutable map version collision: '+str(dest))
            if not dest.exists():shutil.copy2(file,dest)
        resolved=relocate(doc,str(version));write_json(version/'generated-map.json',resolved)
        BakedScene(version/'generated-map.json')
        published={**resolved,'terrain':{**resolved['terrain'],'file':f'versions/{id}/terrain.npz'},'data_version':id}
        pointer=a.output/'generated-map.json';temporary=pointer.with_suffix('.pending.json');write_json(temporary,published);temporary.replace(pointer)
        print(json.dumps({**report,'map':str(pointer),'generated_map_sha256':sha(pointer),'data_version':id,'version_directory':str(version),
            'fine_height_min_max':[float(fine.min()),float(fine.max())],'publication':'Atomic root pointer after full immutable-version validation; staging data retained for diagnosis'},ensure_ascii=False,indent=2))
    else:print(path)
if __name__=='__main__':main()
