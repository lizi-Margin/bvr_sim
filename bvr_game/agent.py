"""Composable Agent CLI. JSON output; saved sorties replay typed commands exactly.

Examples: python -m bvr_game.agent map validate --map ...
          python -m bvr_game.agent game step --state sortie.json --ticks 50 --command '{"lock":true,"target_uid":"bandit"}'
"""
from pathlib import Path
import argparse,json,shutil,sys,subprocess,time,statistics
from .content import ROOT,ASSETS,KENNEY,fetch_kenney,sha,write_json
DEFAULT_MAP=ROOT/'game/maps/training_range_v2/generated-map.json'

def inspect_asset(id):
    p=ASSETS/'registered'/id/'manifest.json'
    if not p.exists():raise FileNotFoundError('Asset is not registered: '+id)
    m=json.loads(p.read_text(encoding='utf8'))
    if id=='audio':
        for item in m['sounds'].values():
            if sha(item['file'])!=item['sha256']:raise ValueError('Audio hash mismatch')
    else:
        for item in m.get('lods',[{'file':m['file'],'sha256':m['glb_sha256']}]):
            if sha(p.parent/item['file'])!=item['sha256']:raise ValueError('Asset/LOD hash mismatch: '+id)
    return m

def game_from_state(state,render=False,output=None):
    from .app import FlightGame
    if sha(state['map'])!=state['map_sha256']:raise ValueError('Saved sortie map changed')
    game=FlightGame(render=render,visible=False,map_path=state['map'],output=output or ROOT/'game/captures/agent')
    for key,value in state['config'].items():setattr(game.config,key,value)
    game.start()
    for action in state['actions']:
        if 'paused' in action:game.sim.set_paused(action['paused']);continue
        if action.get('command'):game.command(**action['command'])
        if action.get('exact'):game.sim.step_exact(action['ticks'])
        else:game.step(action['ticks'])
    if state.get('camera'):game.set_camera(**state['camera'])
    return game

def run(a):
    if a.domain=='asset':
        if a.action=='inspect':return inspect_asset(a.id)
        if a.action=='register':
            if a.spec:
                from .registration import register_spec
                return register_spec(a.spec,a.blender)
            from .catalog import prepare
            return prepare(blender=a.blender,rebuild=a.rebuild)
        if a.source=='kenney':
            if a.action=='fetch':return fetch_kenney(a.value)
            return [{'id':id,**m,'source':'kenney','license':'CC0-1.0'} for id,m in KENNEY.items() if a.value.lower() in ' '.join([id,m['name'],*m['tags']]).lower()]
        script=ROOT/'game/tools/asset_library.py';arguments=[sys.executable,str(script),a.action,a.source,a.value]
        if a.action=='fetch':arguments+=['--resolution',a.resolution,'--max-mb',str(a.max_mb)]
        return json.loads(subprocess.check_output(arguments,cwd=ROOT,text=True,encoding='utf8'))
    if a.domain=='map':
        if a.action=='recipe':
            d=json.loads((ROOT/'game/recipes/training_range_v2.json').read_text());d['seed']=a.seed;d['name']=a.name;write_json(a.output,d);return {'recipe':str(a.output.resolve()),'sha256':sha(a.output)}
        if a.action=='build':
            from .worldgen import Baker
            return Baker(json.loads(a.recipe.read_text())).bake(a.output)
        if a.action=='validate':
            from .mapcheck import validate
            result=validate(a.map)
            if a.output:write_json(a.output,result)
            if result['status']!='passed':raise ValueError(json.dumps(result['failures']))
            return {k:v for k,v in result.items() if k!='resource_inventory'}
        if a.action=='inspect':
            from .scene_runtime import BakedScene
            from .app import native
            scene=BakedScene(a.map);d=scene.document;result={k:d[k] for k in ['name','seed','counts','chunk_m','budgets','terrain','coordinates']}
            result['map_sha256']=sha(a.map)
            if a.render_height and not a.point:raise ValueError('--render-height requires --point north west')
            if a.point:
                result['simulation_height']=scene.terrain(native).height(*a.point)
                if a.render_height:
                    from .app import FlightGame
                    game=FlightGame(render=True,visible=False,map_path=a.map)
                    try:
                        game.start();game.draw()
                        result['render_vertex_height']=game.renderer.render_height(*a.point)
                        result['absolute_height_error_m']=abs(result['render_vertex_height']-result['simulation_height'])
                        result['shader_errors']=game.renderer.shader_errors()
                        result['height_method']='Independent interpolation over renderer CPU vertices uploaded to GPU versus typed GameTerrain'
                    finally:game.close()
            return result
        from .app import FlightGame,serialize
        game=FlightGame(render=True,visible=False,map_path=a.map,output=a.output);game.quality='high';game.renderer.set_quality('high');game.start()
        try:
            if a.camera:game.set_camera(**json.loads(a.camera.read_text()))
            for _ in range(60):game.draw()
            if a.action=='capture':return {'capture':game.capture(a.name)}
            samples=[]
            for _ in range(a.frames):
                start=time.perf_counter();game.step();game.draw();samples.append((time.perf_counter()-start)*1000)
            result={'frames':len(samples),'resolution':[1920,1080],'quality':'high','fps':1000/statistics.mean(samples),'p50_ms':statistics.median(samples),'p95_ms':sorted(samples)[int(len(samples)*.95)],'includes':'simulation tick and complete rendering','excludes':'downloads, conversion, warmup and image encoding','shader_errors':game.renderer.shader_errors(),'statistics':serialize(game.renderer.statistics()),'capture':game.capture('benchmark')}
            write_json(a.output/'benchmark.json',result);return result
        finally:game.close()
    from .app import FlightGame,serialize
    if a.action=='play':
        from .app import main
        sys.argv=['bvr_game','play','--map',str(a.map)];main();return {'closed':True}
    if a.action=='run':
        game=FlightGame(map_path=a.map);game.config.mission=a.mission;game.config.seed=a.seed;game.config.player_model=a.aircraft;game.start()
        state={'schema':1,'map':str(a.map.resolve()),'map_sha256':sha(a.map),'config':serialize(game.config),'actions':[]}
        write_json(a.state,state);result={'state':str(a.state.resolve()),'frame':serialize(game.sim.frame())};game.close();return result
    state=json.loads(a.state.read_text());game=game_from_state(state,render=a.action=='capture',output=a.output)
    try:
        if a.action=='step':
            command=json.loads(a.command);game.command(**command) if command else None
            if a.exact:game.sim.step_exact(a.ticks)
            else:game.step(a.ticks)
            state['actions'].append({'command':command,'ticks':a.ticks,'exact':a.exact});write_json(a.state,state)
        if a.action=='pause':game.sim.set_paused(a.paused);state['actions'].append({'paused':a.paused});write_json(a.state,state)
        if a.action=='camera':
            game.set_camera(a.eye,a.target,a.fov);state['camera']=game.camera_params;write_json(a.state,state)
        if a.action=='capture':
            if a.camera:game.set_camera(**json.loads(a.camera.read_text()))
            for _ in range(20):game.draw()
            return {'capture':game.capture(a.name),'frame':serialize(game.sim.frame())}
        if not game.camera_params:game.follow_camera(0)
        return {'frame':serialize(game.sim.frame()),'camera':game.camera_params,'aim':game.aim,'mode':game.mode}
    finally:game.close()

def main():
    p=argparse.ArgumentParser(description=__doc__);domains=p.add_subparsers(dest='domain',required=True)
    asset=domains.add_parser('asset').add_subparsers(dest='action',required=True)
    for action in ['search','fetch']:
        s=asset.add_parser(action);s.add_argument('source',choices=['kenney','ambientcg','polyhaven','aircraft']);s.add_argument('value')
        if action=='fetch':s.add_argument('--resolution',default='1k');s.add_argument('--max-mb',type=float,default=80)
    s=asset.add_parser('inspect');s.add_argument('id')
    s=asset.add_parser('register');s.add_argument('--blender',default=r'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe');s.add_argument('--rebuild',action='store_true');s.add_argument('--spec',type=Path)
    maps=domains.add_parser('map').add_subparsers(dest='action',required=True)
    s=maps.add_parser('recipe');s.add_argument('create',choices=['create']);s.add_argument('--seed',type=int,default=7);s.add_argument('--name',default='training_range');s.add_argument('--output',type=Path,required=True)
    s=maps.add_parser('build');s.add_argument('--recipe',type=Path,default=ROOT/'game/recipes/training_range_v2.json');s.add_argument('--output',type=Path,required=True)
    for action in ['inspect','validate','benchmark','capture']:
        s=maps.add_parser(action);s.add_argument('--map',type=Path,default=DEFAULT_MAP)
        if action=='inspect':s.add_argument('--point',nargs=2,type=float);s.add_argument('--render-height',action='store_true')
        if action=='validate':s.add_argument('--output',type=Path)
        if action in ['benchmark','capture']:
            s.add_argument('--output',type=Path,default=ROOT/'game/captures/agent');s.add_argument('--camera',type=Path);s.add_argument('--frames',type=int,default=600);s.add_argument('--name',default='map')
    games=domains.add_parser('game').add_subparsers(dest='action',required=True)
    for action in ['run','play','step','query','capture','pause','camera']:
        s=games.add_parser(action)
        if action in ['run','play']:s.add_argument('--map',type=Path,default=DEFAULT_MAP)
        if action!='play':s.add_argument('--state',type=Path,required=True)
        if action=='run':
            s.add_argument('--mission',choices=['air','strike','combined'],default='air');s.add_argument('--aircraft',choices=['F22','F16'],default='F22');s.add_argument('--seed',type=int,default=7)
        if action=='step':s.add_argument('--ticks',type=int,default=1);s.add_argument('--command',default='{}');s.add_argument('--exact',action='store_true')
        if action=='pause':s.add_argument('--paused',action=argparse.BooleanOptionalAction,default=True)
        if action=='camera':s.add_argument('--eye',type=float,nargs=3,required=True);s.add_argument('--target',type=float,nargs=3,required=True);s.add_argument('--fov',type=float,default=1.05)
        if action in ['query','step','pause','camera']:s.set_defaults(output=None)
        if action=='capture':s.add_argument('--camera',type=Path);s.add_argument('--name',default='game');s.add_argument('--output',type=Path,default=ROOT/'game/captures/agent')
    try:print(json.dumps(run(p.parse_args()),ensure_ascii=False,indent=2))
    except Exception as error:print(json.dumps({'error':str(error)},ensure_ascii=False));raise SystemExit(1)
if __name__=='__main__':main()
