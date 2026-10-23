"""GPU evidence and deterministic input tapes for the content-rich Alpha.

Historical screenshots are retained separately. Controlled comparisons use the
archived presentation code and map, a common current simulation, identical
camera matrices, and an explicit studio-origin adapter. No outcomes are edited.
"""
from pathlib import Path
import argparse,json,sys,time,hashlib,statistics,shutil,importlib.util,importlib,os,types
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,serialize,load_runtime
from bvr_game.content import write_json,sha
from bvr_game.pilots import CombatPilot,StrikePilot
MAP=ROOT/'game/maps/training_range_v2/generated-map.json'

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

class Evidence:
    def __init__(self,game,out):self.g=game;self.out=out;self.records=[];self.tapes={};self.tape=None
    def start(self,id,mission='air',model='F22'):
        g=self.g;g.config.mission=mission;g.config.player_model=model;g.config.enemy_attacks=True;g.start();g.show_hud=True
        self.tape={'id':id,'config':serialize(g.config),'actions':[]};self.tapes[id]=self.tape
    def step(self,command,ticks=5):
        self.tape['actions'].append({'command':command,'ticks':ticks});self.g.command(**command);return self.g.step(ticks)
    def snapshot(self,name,camera=None,mode=None,hud=True):
        g=self.g;old_manual=g.camera_manual;old_mode=g.mode;g.show_hud=hud
        if mode:g.mode=mode
        if camera:g.set_camera(**camera)
        else:
            g.camera_manual=False;g.draw();g.set_camera(**g.camera_params)
        for _ in range(5):g.draw()
        image=g.capture(name);metadata=json.loads(Path(image).with_suffix('.json').read_text())
        self.records.append({'name':name,'tape':self.tape['id'],'action_count':len(self.tape['actions']),'tick':g.sim.frame().tick,'paused':g.sim.frame().paused,'mode':g.mode,'hud':hud,'camera':dict(g.camera_params),'frame_sha256':digest(serialize(g.sim.frame())),'after_image':image})
        print('CAPTURE',name,g.sim.frame().tick,flush=True)
        g.camera_manual=old_manual;g.mode=old_mode;g.show_hud=True
        return image
    def finish(self,name):
        frame=serialize(self.g.sim.frame());self.tape['final_frame']=frame;write_json(self.out/'reports'/('rendered_'+name+'.json'),{'status':'passed' if frame['result']=='succeeded' else 'failed','frame':frame,'input_tape':self.tape['id'],'shader_errors':self.g.renderer.shader_errors()})
        if frame['result']!='succeeded':raise AssertionError(name+' did not succeed')

def capture_after(out):
    out=Path(out);g=FlightGame(render=True,visible=False,map_path=MAP,output=out/'after');g.quality='high';g.renderer.set_quality('high');e=Evidence(g,out)
    try:
        e.start('scenery');g.sim.set_paused(True)
        cameras=json.loads((out/'maps/comparison-cameras.json').read_text())
        for name in ['01_overview','02_low_flight','03_airport','04_village_roads','05_industrial','06_river_fields_forest']:e.snapshot(name,cameras[name],hud=False)
        for model,id in [('F22','07_hangar_F22'),('F16','08_hangar_F16')]:
            e.start(id,model=model);g.sim.set_paused(True);e.snapshot(id,{'eye':[26,12,-26],'target':[-6,3,0],'fov':.92},mode='hangar')
        e.start('air');pilot=CombatPilot();flags=set();e.snapshot('09_radar_search')
        for _ in range(1800):
            f=g.sim.frame();f=e.step(pilot.command(f,g.player(f)));g.draw()
            if f.envelope.target_uid and 'lock' not in flags:e.snapshot('10_lock_envelope');flags.add('lock')
            friendly=next((m for m in f.missiles if m.owner=='player' and 3<m.age<6),None)
            if friendly and 'missile' not in flags:
                entity=next(x for x in f.entities if x.uid==friendly.uid);n,w,h=entity.position
                e.snapshot('11_missile_in_flight',{'eye':[-w+14,h+7,n-28],'target':[-w,h,n],'fov':.8});flags.add('missile')
            hit=next((x for x in f.events if x.kind=='missile_hit' and x.actor=='player'),None)
            if hit and 'hit' not in flags:
                n,w,h=hit.position;e.snapshot('12_missile_outcome',{'eye':[-w+60,h+28,n-90],'target':[-w,h,n],'fov':.9},mode='flight');flags.add('hit')
            if f.result!='running':break
        assert {'lock','missile','hit'}<=flags
        e.snapshot('14_debrief_air',mode='result');e.finish('air')
        e.start('strike',mission='strike');g.weapon='Mk-82';pilot=StrikePilot(g.map['ground_target']['position']);flags=set()
        for _ in range(1200):
            f=g.sim.frame();f=e.step(pilot.command(f,g.player(f)));g.draw()
            bomb=next((x for x in f.entities if x.kind=='bomb' and x.alive),None)
            release=next((x for x in f.events if x.kind=='bomb_released'),None)
            if bomb and release and f.tick-release.tick>=50 and 'release' not in flags:
                n,w,h=bomb.position;e.snapshot('13a_bomb_release',{'eye':[-w+8,h-4,n-16],'target':[-w,h,n],'fov':.75},hud=False);flags.add('release')
            hit=next((x for x in f.events if x.kind=='bomb_impact'),None)
            if hit:
                n,w,h=hit.position;e.snapshot('13_bomb_explosion',{'eye':[-w+100,h+55,n-150],'target':[-w,h+2,n],'fov':.85},mode='flight');break
        e.snapshot('14_debrief_strike',mode='result');e.finish('strike')
        e.start('combined',mission='combined');combat=CombatPilot();strike=StrikePilot(g.map['ground_target']['position'])
        for _ in range(3000):
            f=g.sim.frame();pilot=strike if f.air_kills else combat;g.weapon='Mk-82' if f.air_kills else 'AIM-120C7';f=e.step(pilot.command(f,g.player(f)));g.draw()
            if f.result!='running':break
        e.snapshot('14_debrief_combined',mode='result');e.finish('combined')
        assert g.renderer.shader_errors()==0
        write_json(out/'maps/controlled-comparison-views.json',{'method':'Common deterministic simulation inputs; identical fixed camera eye/target/FOV/up per pair. Legacy baseline uses archived v1 presentation and map; studio origin is normalized to match the independent hangar presentation. Historical original captures are retained.','views':e.records})
        for id,tape in e.tapes.items():write_json(out/'reports/input-tapes'/(id+'.json'),tape)
        return {'views':len(e.records),'air_seconds':e.tapes['air']['final_frame']['sim_time'],'strike_seconds':e.tapes['strike']['final_frame']['sim_time'],'combined_seconds':e.tapes['combined']['final_frame']['sim_time'],'shader_errors':g.renderer.shader_errors()}
    finally:g.close()

def replay_headless(out):
    out=Path(out);reports={}
    for mission in ['air','strike','combined']:
        tape=json.loads((out/'reports/input-tapes'/(mission+'.json')).read_text());g=FlightGame(map_path=MAP,output=out/'reports/headless'/mission)
        try:
            for k,v in tape['config'].items():setattr(g.config,k,v)
            g.start()
            for action in tape['actions']:g.command(**action['command']);g.step(action['ticks'])
            frame=serialize(g.sim.frame());same=frame==tape['final_frame'];reports[mission]={'status':'passed' if same else 'failed','frame_sha256':digest(frame),'result':frame['result'],'sim_seconds':frame['sim_time'],'ticks':frame['tick'],'exact_frame_equality':same}
            write_json(out/'reports'/('headless_'+mission+'.json'),{'frame':frame})
            if not same:raise AssertionError('Rendering changed GameFrame: '+mission)
        finally:g.close()
    result={'status':'passed','map_sha256':sha(MAP),'terrain_sha256':json.loads(MAP.read_text())['terrain']['sha256'],'missions':reports};write_json(out/'render-headless-parity.json',result);return result

def capture_before(out):
    out=Path(out);before=out/'before';archive=before/'historical-original';archive.mkdir(exist_ok=True)
    for image in before.glob('*.png'):
        metadata=image.with_suffix('.json')
        if metadata.exists() and 'comparison_method' not in json.loads(metadata.read_text()):
            for file in [image,metadata]:
                if not (archive/file.name).exists():shutil.copy2(file,archive/file.name)
    legacy_map_path=out/'maps/baseline-map.json';legacy_map=json.loads(legacy_map_path.read_text())
    runtime=load_runtime(ROOT.parent/'work/baseline-runtime.json')
    sys.path.insert(0,runtime['renderer_module']);dll=os.add_dll_directory(runtime['renderer_module']);r=importlib.import_module('bvr_game_render')
    spec=importlib.util.spec_from_file_location('archived_alpha_presentation',ROOT.parent/'work/alpha_baseline_source/bvr_game/app.py');legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
    g=FlightGame(render=False,map_path=MAP,output=before);g.runtime=runtime;g.r=r;g.dll=dll
    g.renderer=r.Renderer(1920,1080,False,runtime['engine_source'],runtime['shader_cache'],runtime['models']);g.quality='high';g.renderer.set_quality('high')
    terrain=legacy.native.GameTerrain()
    for k,v in legacy_map['terrain'].items():setattr(terrain,k,v)
    g.renderer.configure_world(terrain,legacy_map['ground_target']['position'],legacy_map['runway']['position'],legacy_map['runway']['length_m'],legacy_map['runway']['width_m'],legacy_map.get('scenery_seed',7),runtime.get('asphalt_texture',''),runtime.get('terrain_texture',''))
    for item in legacy_map.get('assets',[]):g.renderer.place_asset(item['id'],item['model'],item['position'],item.get('scale',1))
    g.hud=types.MethodType(legacy.FlightGame.hud,g)
    index=json.loads((out/'maps/controlled-comparison-views.json').read_text());pairs=[]
    try:
        for view in index['views']:
            tape=json.loads((out/'reports/input-tapes'/(view['tape']+'.json')).read_text())
            for key,value in tape['config'].items():setattr(g.config,key,value)
            g.start()
            for action in tape['actions'][:view['action_count']]:g.command(**action['command']);g.step(action['ticks'])
            g.sim.set_paused(view['paused']);g.mode=view['mode'];g.show_hud=view['hud'];g.set_camera(**view['camera'])
            if digest(serialize(g.sim.frame()))!=view['frame_sha256']:raise AssertionError('Comparison snapshot differs: '+view['name'])
            for _ in range(12):g.draw()
            image=g.capture(view['name']);path=Path(image).with_suffix('.json');metadata=json.loads(path.read_text())
            metadata['comparison_method']=index['method'];metadata['simulation_scene']=str(MAP);metadata['simulation_scene_sha256']=sha(MAP);metadata['simulation_terrain_sha256']=g.baked_scene.document['terrain']['sha256']
            metadata['scene']=str(legacy_map_path);metadata['scene_sha256']=sha(legacy_map_path);metadata['terrain_sha256']=digest(legacy_map['terrain']);metadata['terrain_hash_format']='canonical JSON of v1 height field; v1 did not have a separate height archive'
            metadata['rendered_textures']={key:sha(value) for key,value in runtime.items() if key.endswith('_texture')}
            metadata['baseline_adapter']='Original renderer/UI/map with a normalized hangar origin, camera-up setter and read-only resource counters. Original unadapted captures retained in before/historical-original.'
            write_json(path,metadata)
            after_metadata=json.loads(Path(view['after_image']).with_suffix('.json').read_text())
            assert metadata['camera']==after_metadata['camera']
            pairs.append({'name':view['name'],'before':image,'after':view['after_image'],'identical_camera':True,'identical_game_frame':True,'resolution':[1920,1080]})
            print('BASELINE',view['name'],flush=True)
        result={'status':'passed','method':index['method'],'pairs':pairs,'historical_originals':str(archive)};write_json(out/'reports/fixed-camera-comparison.json',result);return {'pairs':len(pairs),'identical_camera':True,'identical_game_frame':True}
    finally:g.close()

def performance(out,frames=600):
    out=Path(out);g=FlightGame(render=True,visible=False,map_path=MAP,output=out/'after/performance');g.quality='high';g.renderer.set_quality('high');results={}
    try:
        cameras=json.loads((out/'maps/comparison-cameras.json').read_text())
        for name in ['normal_bvr','low_flight','forest_boundary']:
            g.config.mission='air';g.config.player_model='F22';g.start();pilot=CombatPilot()
            if name=='low_flight':
                g.config.player_north=5000;g.config.player_west=-7500;g.config.altitude=g.sim.terrain().height(5000,-7500)+700;g.sim.reset(g.config)
            if name=='forest_boundary':g.set_camera(**cameras['06_river_fields_forest'])
            initial=serialize(g.sim.frame())
            # Warm the actual combat/effect path, then restart the same initial
            # condition. No timed download, conversion, shader warmup or capture.
            for _ in range(100):
                f=g.sim.frame();g.command(**pilot.command(f,g.player(f)));g.step();g.draw()
            g.sim.reset(g.config);g.renderer.reload();g.chase.reset();pilot=CombatPilot()
            for _ in range(40):g.draw()
            samples=[];statistics_samples=[]
            for i in range(frames):
                start=time.perf_counter();f=g.sim.frame();g.command(**pilot.command(f,g.player(f)));g.step();g.draw();samples.append((time.perf_counter()-start)*1000)
                if i%100==0:statistics_samples.append({'tick':g.sim.frame().tick,'statistics':serialize(g.renderer.statistics())})
            report={'resolution':[1920,1080],'quality':'high','frames':frames,'fps':1000/statistics.mean(samples),'p50_ms':statistics.median(samples),'p95_ms':sorted(samples)[int(len(samples)*.95)],'sample_ms':samples,'shader_errors':g.renderer.shader_errors(),'statistics_samples':statistics_samples,'statistics':serialize(g.renderer.statistics()),'initial_frame':initial,'capture':g.capture('performance_'+name)}
            report['status']='passed' if report['fps']>=120 and report['p95_ms']<=8.33 and report['shader_errors']==0 else 'failed'
            results[name]=report;print('PERFORMANCE',name,report['fps'],report['p95_ms'],flush=True)
        result={'status':'passed' if all(x['status']=='passed' for x in results.values()) else 'failed','hardware':'RTX 2080 Ti / Ryzen 9 5950X','includes':'Observation/Agent command submission, simulation tick, HUD and full Wicked render + Present','excludes':'Asset fetch/conversion, shader warmup, statistics scans, screenshot encoding','quality_settings':{'shadows':True,'FXAA':True,'bloom':True,'SSR':True,'SSGI':True,'FSR2':False,'motion_blur':False},'visibility_policy':'Unchanged recipe: 30-35 km object distances, 512-km coarse terrain, 20-km focus; no content hiding or reduced distances for benchmark','map_sha256':sha(MAP),'terrain_sha256':g.baked_scene.document['terrain']['sha256'],'profiles':results}
        write_json(out/'performance-1080p-high.json',result)
        if result['status']!='passed':raise AssertionError('High performance gate failed; see measurements')
        return {key:{k:value[k] for k in ['fps','p95_ms','status']} for key,value in results.items()}
    finally:g.close()

def miss_recovery(out):
    out=Path(out);g=FlightGame(map_path=MAP,output=out/'reports/miss-recovery');g.config.enemy_attacks=False;g.start();g.config.enemy_range=60000;g.config.altitude=6000;g.sim.reset(g.config);pilot=CombatPilot(True);actions=[]
    try:
        initial=serialize(g.config)
        for _ in range(1300):
            f=g.sim.frame();command=pilot.command(f,g.player(f));actions.append({'command':command,'ticks':5});g.command(**command);f=g.step(5)
            if any(e.kind=='missile_missed' and e.actor=='player' for e in f.events):break
            if f.result!='running':raise AssertionError('Miss recovery scenario ended before a natural miss')
        missed=serialize(f);assert any(e['kind']=='missile_missed' and e['actor']=='player' for e in missed['events']);assert f.result=='running'
        command={'heading':g.player(f).orientation[2],'pitch':0,'throttle':1};actions.append({'command':command,'ticks':250});g.command(**command);g.step(250);after=serialize(g.sim.frame());assert after['result']=='running'
        result={'status':'passed','initial_config':initial,'first_miss_frame':missed,'after_another_five_seconds':after,'actions':actions,'mechanism':'Actual early turn breaks midcourse support; native missile eventually exhausts energy. No target health, missile velocity or outcome was modified.'};write_json(out/'reports/miss-recovery-report.json',result);return {'status':'passed','miss_time':missed['sim_time'],'continued_to':after['sim_time']}
    finally:g.close()

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['after','before','headless','performance','miss']);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps({'after':capture_after,'before':capture_before,'headless':replay_headless,'performance':performance,'miss':miss_recovery}[a.action](a.output),indent=2))
if __name__=='__main__':main()
