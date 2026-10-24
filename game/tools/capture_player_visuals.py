"""Actual DX12 candidate frames and keyboard/core/model response evidence."""
from pathlib import Path
import argparse,json,math,os,sys
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,serialize
from bvr_game.content import write_json,sha

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--action',choices=['map','input','projection'],default='map')
    p.add_argument('--map',type=Path,default=ROOT/'game/maps/river_valley_airfield/generated-map.json')
    p.add_argument('--profile-file',type=Path,help='Frozen candidate player profile, without editing the game defaults')
    p.add_argument('--visual-profile',type=Path,default=ROOT/'game/recipes/player_daylight.json',help='Explicit presentation candidate without changing game defaults')
    p.add_argument('--views',nargs='+',help='Named map cameras to capture; default captures every map camera')
    a=p.parse_args()
    os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sortie-logs')
    g=FlightGame(render=True,visible=False,map_path=a.map,
        visual_profile=a.visual_profile,output=a.output/'client')
    if a.profile_file:
        from bvr_game.player_profiles import PlayerProfileStore
        g.profile_store=PlayerProfileStore(a.profile_file)
    g.player_profiles_frozen=True
    rows=[]
    try:
        g.quality='high';g.renderer.set_quality('high');g.select_aircraft('F16');g.config.mission='training';g.start()
        if a.action=='map':
            cameras={
                'airfield_overview':([4600,1100,-4200],[2950,220,-2100]),
                'runway_approach':([3550,280,-4400],[3500,220,-1400]),
                'airport_apron':([3400,340,-2700],[2800,225,-2100]),
                'river_valley':([1100,500,500],[-650,120,2850]),
                'river_bank_low':([-1100,145,-300],[-680,120,500]),
                'river_channel_overhead':([-650,900,100],[-650,120,101]),
                'forest_edge':([2250,245,-2900],[2100,225,-2500]),
                'forest_overflight':([2250,620,-2700],[2100,210,-2200]),
                'forest_transition':([2900,420,-3400],[2100,210,-2200]),
                'town_roads':([3400,600,2200],[2700,210,3500]),
                'industry_frontage':([2400,520,1700],[1400,180,2650]),
                'regional_transition':([3500,4200,-7000],[0,170,6000])}
            g.show_hud=False
            if a.views:
                unknown=set(a.views)-set(cameras)-{'fixed_high_horizon'}
                if unknown:raise ValueError('Unknown map cameras: '+str(sorted(unknown)))
            for name,(eye,target) in cameras.items():
                if a.views and name not in a.views:continue
                g.set_camera(eye,target,fov=1.)
                for _ in range(40):g.draw()
                rows.append({'view':name,'capture':g.capture(name),'shader_errors':g.renderer.shader_errors()})
            if not a.views or 'fixed_high_horizon' in a.views:
                g.select_aircraft('F22');g.config.mission='training';g.start(start_position=[-20000,0,8500],initial_speed=300)
                g.set_camera([32,8511,-20032],[0,8501,-20000],.92)
                for _ in range(40):g.draw()
                rows.append({'view':'fixed_high_horizon','capture':g.capture('fixed_high_horizon'),'shader_errors':g.renderer.shader_errors()})
        elif a.action=='projection':
            from bvr_game.player_input import camera_ray
            for width,height in [(1920,1080),(1280,720),(1600,1000)]:
                g.renderer.resize(width,height);event=g.renderer.poll();g.width,g.height=event.width,event.height
                assert [g.width,g.height]==[width,height]
                for fov in [1.,.55]:
                    g.set_camera([0,9000,-20000],[0,9000,-19000],fov)
                    for _ in range(20):g.draw()
                    errors=[]
                    for fx in [.25,.5,.75]:
                        for fy in [.25,.5,.75]:
                            ray=camera_ray(fx*width,fy*height,width,height,g.camera_params)
                            eye=g.camera_params['eye'];origin=[eye[2],-eye[0],eye[1]]
                            pixel=list(g.renderer.project([origin[i]+ray[i]*10000 for i in range(3)]))
                            errors.append(math.hypot(pixel[0]-fx*width,pixel[1]-fy*height))
                    assert max(errors)<1.5,(width,height,fov,errors)
                    rows.append({'viewport':[width,height],'fov':fov,'maximum_roundtrip_error_pixels':max(errors),
                        'actual_settings':json.loads(g.renderer.visual_settings())['actual_output'],'capture':g.capture(f'projection-{width}-{height}-{fov}')})
            terrain=g.sim.terrain();height_samples=[];surface_samples=[]
            for n in range(-5000,5001,1250):
                for w in range(-6000,2001,1000):
                    actual=g.renderer.render_height(n,w);expected=terrain.height(n,w)
                    height_samples.append({'point':[n,w],'core':expected,'renderer':actual,'error_m':abs(actual-expected)})
            # Exercise both sides of material/height-resolution boundaries,
            # including the outer mesh; interior samples cannot prove seams.
            for tile in g.baked_scene.document['terrain']['details']:
                n0,w0=tile['origin_north'],tile['origin_west'];dn=tile['spacing']*(tile['columns']-1);dw=tile['spacing']*(tile['rows']-1)
                for fraction in [.13,.57,.89]:
                    for delta in [-.5,.5]:
                        for n,w in [(n0+delta,w0+fraction*dw),(n0+dn+delta,w0+fraction*dw),
                                    (n0+fraction*dn,w0+delta),(n0+fraction*dn,w0+dw+delta)]:
                            actual=g.renderer.render_height(n,w);expected=terrain.height(n,w)
                            height_samples.append({'point':[n,w],'boundary_sample':True,'core':expected,'renderer':actual,'error_m':abs(actual-expected)})
            if g.baked_scene.document.get('landscape',{}).get('river_channel'):
                from shapely.geometry import Point,LineString
                for river in g.baked_scene.document['rivers']:
                    line=LineString(river['points'])
                    for north in [-7000,-3500,0,2500,6500]:
                        station=line.project(Point(north,600));p=line.interpolate(station)
                        left=line.interpolate(station-1);right=line.interpolate(station+1)
                        dn,dw=right.x-left.x,right.y-left.y;length=math.hypot(dn,dw)
                        half=river['width_m']/2;bank=g.baked_scene.document['landscape']['river_channel']['bank_width_m']
                        for across in [-half-bank,-half,-half/2,0,half/2,half,half+bank]:
                            n=p.x-dw/length*across;w=p.y+dn/length*across
                            actual=g.renderer.render_height(n,w);expected=terrain.height(n,w)
                            height_samples.append({'point':[n,w],'river_cross_section':True,'core':expected,'renderer':actual,'error_m':abs(actual-expected)})
            for surface in g.baked_scene.document['environment']['contact_surfaces']:
                vertices=surface['vertices'];n=sum(v[0] for v in vertices)/len(vertices);w=sum(v[1] for v in vertices)/len(vertices)
                expected=terrain.contact(n,w,0,float('inf')).height;actual=g.renderer.render_surface_height(n,w)
                surface_samples.append({'id':surface['id'],'point':[n,w],'core':expected,'renderer':actual,'error_m':abs(actual-expected)})
            assert max(x['error_m'] for x in height_samples+surface_samples)<=.1
            rows.append({'terrain_height_parity':height_samples,'contact_surface_height_parity':surface_samples,
                'terrain_sha256':g.baked_scene.document['terrain']['sha256'],
                'method':'Independent renderer CPU vertices/triangles versus core GameTerrain; actual uploaded geometry, not a second terrain formula'})
        else:
            for model in ['F22','F16','FG-A-10']:
                g.select_aircraft(model);g.config.mission='training';g.config.speed=180 if model=='FG-A-10' else 300;g.config.altitude=8500
                for key in ['W','S','A','D']:
                    g.start(start_position=[-20000,0,8500],initial_speed=180 if model=='FG-A-10' else 300);initial=serialize(g.player())
                    for _ in range(20):g.draw()
                    for i in range(50):
                        g.input(SimpleNamespace(held=[ord(key)],pressed=[],x=960,y=540,wheel=0,quit=False,active=True),.02);g.step();g.draw(.02)
                    actual=g.player();forward=list(g.renderer.entity_forward('player'));state=serialize(g.sim.player_flight_state())
                    if key in ['W','S']:
                        expected_up=key=='S';assert (actual.orientation[1]<initial['orientation'][1])==expected_up,(model,key,actual.orientation)
                        assert (forward[1]>0)==expected_up,(model,key,forward)
                    else:assert state['measured']['body_rates'][0]*(1 if key=='D' else -1)>.02,(model,key,state)
                    roll,pitch,yaw=actual.orientation
                    f=[math.cos(yaw)*math.cos(pitch),math.sin(yaw)*math.cos(pitch),-math.sin(pitch)]
                    right=[math.sin(yaw),-math.cos(yaw),0];up=[math.cos(yaw)*math.sin(pitch),math.sin(yaw)*math.sin(pitch),math.cos(pitch)]
                    r=[right[i]*math.cos(roll)-up[i]*math.sin(roll) for i in range(3)]
                    u=[up[i]*math.cos(roll)+right[i]*math.sin(roll) for i in range(3)]
                    expected=[[-a[1],a[2],a[0]] for a in [r,u,f]]
                    rendered=[list(axis) for axis in g.renderer.entity_basis('player')]
                    basis_error=max(abs(a-b) for arow,brow in zip(expected,rendered) for a,b in zip(arow,brow))
                    assert basis_error<1e-5,(model,key,basis_error,expected,rendered)
                    rows.append({'model':model,'key':key,'initial':initial,'core':serialize(actual),'player_state':state,
                        'rendered_forward':forward,'rendered_basis':rendered,'independently_expected_basis':expected,'basis_max_component_error':basis_error,
                        'capture':g.capture(model+'_'+key),'shader_errors':g.renderer.shader_errors(),
                        'input_path':'Real FlightGame.input handler with explicit deterministic events; not a claim of physical keyboard hardware injection'})
        write_json(a.output/'report.json',{'captures':rows,'visual_settings':json.loads(g.renderer.visual_settings()),'statistics':serialize(g.renderer.statistics()),
            'inspector_sha256':sha(Path(__file__)),'renderer_sha256':sha(Path(g.r.__file__)),'vram':serialize(g.renderer.memory_usage()),
            'source_card_materials':serialize(g.renderer.source_card_materials()) if hasattr(g.renderer,'source_card_materials') else None,
            'map_sha256':g.scene_hash,'shader_errors':g.renderer.shader_errors(),'profile_file_sha256':g.profile_store.file_sha256,
            'native_core':str(__import__('bvr_game.app',fromlist=['native']).native.__file__)})
        print('GPU_CANDIDATE_CAPTURED',a.action,len(rows),'shader',g.renderer.shader_errors(),flush=True)
    finally:g.close()
if __name__=='__main__':main()
