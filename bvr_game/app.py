"""Flight Operations: typed simulation, optional Wicked renderer, CLI acceptance runs."""
from __future__ import annotations
import argparse, hashlib, importlib, json, math, os, statistics, sys, time
import textwrap
from .aircraft import aircraft_catalog,aircraft,loadout,runtime_models
from .presentation import ChaseCamera,Labels,safe_aim,curve,mouse_pitch,mouse_roll_rate
from .player_profiles import PlayerProfileStore
from .player_input import PlayerInputAdapter,native_intent,body_forward,unit,aim_marker
from contextlib import redirect_stdout
from pathlib import Path
from .sortie_logs import SortieJournal,open_logs_directory
with redirect_stdout(sys.stderr):
    from bvr_sim.bvr_env_cpp import bvr_sim_cpp as native

ROOT=Path(__file__).resolve().parents[1]
GAME=Path(os.environ.get('BVR_GAME_ROOT',ROOT/'game'))
DEFAULT_VISUAL_PROFILE=GAME/'recipes/player_daylight.json'
DEFAULT_WORLD_MAP=GAME/'maps/training_range_v3/generated-map.json'
WHITE=0xffeeeeee; GREEN=0xff86f2a6; RED=0xff6d75ff; BLUE=0xffffc885; MUTED=0xffb3b6ad

def serialize(value):
    if isinstance(value,(str,int,float,bool,type(None))):return value
    if hasattr(value,'name') and hasattr(value,'value') and type(value).__module__==native.__name__:return value.name
    if isinstance(value,(list,tuple)):return [serialize(x) for x in value]
    if isinstance(value,dict):return {str(k):serialize(v) for k,v in value.items()}
    return {k:serialize(getattr(value,k)) for k in dir(value) if not k.startswith('_') and not callable(getattr(value,k))}

def load_runtime(path):
    r=json.loads(Path(path).read_text(encoding='utf8'))
    for model,file in r['models'].items():
        p=Path(file);manifest=p.parent/'manifest.json'
        if not p.is_file() or not manifest.is_file():raise FileNotFoundError('Unregistered model: '+str(p))
        m=json.loads(manifest.read_text(encoding='utf8'))
        expected=next((x['sha256'] for x in m.get('lods',[]) if x['file']==p.name),m['glb_sha256'])
        expected_id=r.get('model_aliases',{}).get(model,model.split('::')[0])
        if m['id']!=expected_id or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
            raise ValueError('Asset registration/hash mismatch: '+model)
    for id,file in r.get('audio',{}).items():
        p=Path(file);manifest=json.loads((p.parent/'manifest.json').read_text(encoding='utf8'))
        if hashlib.sha256(p.read_bytes()).hexdigest()!=manifest['sounds'][id]['sha256']:raise ValueError('Audio registration/hash mismatch: '+id)
    return r

class FlightGame:
    """One owner steps GameSession. Renderer receives a value snapshot only."""
    def __init__(self,*,render=False,visible=True,width=1920,height=1080,runtime=GAME/'runtime.json',map_path=GAME/'maps/training.json',output=GAME/'captures',visual_profile=DEFAULT_VISUAL_PROFILE):
        self.output=Path(output).resolve();self.output.mkdir(parents=True,exist_ok=True)
        self.map_path=Path(map_path).resolve();self.map=json.loads(self.map_path.read_text(encoding='utf8'))
        self.baked_scene=None
        if self.map.get('schema_version')==2:
            from .scene_runtime import BakedScene
            self.baked_scene=BakedScene(self.map_path,self.map);self.map=self.baked_scene.compatibility_view()
        self.scene_hash=hashlib.sha256(self.map_path.read_bytes()).hexdigest()
        self.sim=native.GameSession(str(self.output/'simulation.log'))
        self.journal=SortieJournal(self.sim,os.environ.get('BVR_SORTIE_LOG_ROOT',GAME/'logs/sorties'))
        self.logs_enabled=True;self._journal_tick=0
        terrain=self.baked_scene.terrain(native) if self.baked_scene else native.GameTerrain()
        if not self.baked_scene:
            for k,v in self.map['terrain'].items():setattr(terrain,k,v)
        self.sim.set_terrain(terrain)
        self.config=native.GameConfig();self.config.enemy_range=9000;self.config.altitude=self.map['player_start'][2]
        if self.baked_scene:
            self.config.enemy_range=self.map['mission']['enemy_range_m'];self.config.speed=self.map['mission']['speed_mps'];self.config.enemy_evasion=True
        self.config.player_north,self.config.player_west=self.map['player_start'][:2]
        self.config.ground_north,self.config.ground_west=self.map['ground_target']['position'][:2]
        self.width,self.height=width,height;self.renderer=None;self.r=None;self.runtime={};self.visual_profile={}
        self.mode='hangar';self.weapon='AIM-120C7';self.target='';self.throttle=.85
        self.camera_state=None;self.camera_params={};self.camera_manual=False;self.aim=(width/2,height/2)
        self.chase=ChaseCamera();self.hud_layout=[]
        self.show_hud=True
        self.aircraft_rows=aircraft_catalog(include_library=True)['aircraft'];self.aircraft_scroll=0;self.menu_notice=''
        self.aircraft_search='';self.search_active=False;self._preview_model=None
        self.quality='medium';self.last_event_tick=-1;self.fps=0;self.frame_times=[];self.closed=False;self.interactive=False
        self.profile_store=PlayerProfileStore();self.player_profile=None;self.player_input=None;self.player_profiles_frozen=False
        self.start(record=False)
        self.mode='hangar';self.sim.set_paused(True)
        if render:
            self.runtime=load_runtime(runtime)
            self.runtime['models']=runtime_models(self.runtime,self.baked_scene.document.get('resource_versions',{}) if self.baked_scene else None)
            sys.path.insert(0,self.runtime['renderer_module'])
            self.dll=os.add_dll_directory(self.runtime['renderer_module']) if os.name=='nt' else None
            self.r=importlib.import_module('bvr_game_render')
            profile=Path(visual_profile)
            args=[width,height,visible,self.runtime['engine_source'],self.runtime['shader_cache'],self.runtime['models']]
            if getattr(self.r,'VISUAL_BETA',False) and profile.is_file():
                self.visual_profile=json.loads(profile.read_text(encoding='utf8'));args.append(str(profile))
            self.renderer=self.r.Renderer(*args)
            if self.runtime.get('audio') and hasattr(self.renderer,'configure_audio'):self.renderer.configure_audio(self.runtime['audio'],visible)
            if self.baked_scene:self.baked_scene.configure(self.renderer,self.r,terrain,self.visual_profile)
            else:
                self.renderer.configure_world(terrain,self.map['ground_target']['position'],self.map['runway']['position'],self.map['runway']['length_m'],self.map['runway']['width_m'],self.map.get('scenery_seed',7),self.runtime.get('asphalt_texture',''),self.runtime.get('terrain_texture',''))
                for obj in self.map.get('assets',[]):
                    self.renderer.place_asset(obj['id'],obj['model'],obj['position'],obj.get('scale',1))

    def start(self,record=True,*,start_position=None,initial_speed=None):
        self.finish_sortie('restarted')
        if self.baked_scene:
            start=self.map['mission'].get('convoy_start',self.map['mission']['strike_start']) if self.config.mission=='convoy' else (self.map['mission']['strike_start'] if self.config.mission=='strike' else self.map['mission']['player_start'])
            self.config.player_north,self.config.player_west,self.config.altitude=start
            if self.config.mission=='convoy':
                from .ground import spec_from_data
                self.config.ground_units=[spec_from_data(native,s) for s in self.map['mission'].get('ground_units',[])]
            elif getattr(self,'_map_ground_units',False):self.config.ground_units=[]
            self._map_ground_units=self.config.mission=='convoy'
        if self.config.library_aircraft:
            row=self.current_aircraft();self.config.speed=max(80,min(800,row['validation'].get('initial_speed_mps',200)))
            terrain=self.baked_scene.terrain(native) if self.baked_scene else None
            floor=terrain.height(self.config.player_north,self.config.player_west) if terrain else 0
            self.config.altitude=max(floor+500,min(19500,max(1000,row['validation'].get('initial_altitude_m',5000))))
        if self.config.mission=='intercept_patrol':
            spec=json.loads((GAME/'recipes/intercept_patrol.json').read_text())
            self.config.enemy_attacks=self.config.enemy_evasion=True
            self.config.enemy_range=spec['initial_enemy_range_m'];self.config.speed=spec['initial_speed_mps'];self.config.altitude=spec['initial_altitude_m']
            self.config.intercept_waves=spec['wave_count'];self.config.intercept_interval=spec['wave_interval_s'];self.config.intercept_timeout=spec['timeout_s']
            self.config.missiles=6;self.config.bombs=0
        if start_position is not None:
            if len(start_position)!=3 or not all(math.isfinite(float(v)) for v in start_position):raise ValueError('Start position must be finite NWU metres')
            self.config.player_north,self.config.player_west,self.config.altitude=map(float,start_position)
        if initial_speed is not None:self.config.speed=float(initial_speed)
        self.sim.reset(self.config);self.mode='flight';self.target='';self.camera_state=None;self.camera_manual=False;self.last_event_tick=-1
        self._preview_model=None
        self.chase.reset()
        self.configure_player_flight()
        self._journal_tick=0
        if record and self.logs_enabled:
            row=self.current_aircraft()
            context={'map':str(self.map_path),'map_sha256':self.scene_hash,'aircraft_id':row['id'],'fdm':row['fdm'],'appearance':{k:row['appearance'].get(k) for k in ['asset_id','glb_sha256','file']},'resource_versions':self.baked_scene.document['resource_versions'] if self.baked_scene else {}}
            context['visual_profile']=self.visual_profile
            context['player_flight_profile']=self.player_profile
            context['core_sha256']=hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest()
            context['entry']=getattr(self,'entry_point','flight_game')
            self.journal.start(serialize(self.config),context)
        pilot=native.PilotCommand();pilot.throttle=self.throttle;self.submit_command(pilot)
        if self.renderer:self.renderer.reload()

    def select_aircraft(self,id,loadout_id=None):
        self.finish_sortie('aircraft_changed')
        row=aircraft(id,require_available=self.renderer is not None)
        preset=loadout(row,loadout_id)
        self.config.player_model=row['simulation_model'];self.config.fdm=row['fdm']['type']
        self.config.library_aircraft=row.get('library_aircraft',False)
        if self.config.library_aircraft:self.config.enemy_attacks=False
        self.config.missiles=preset['missiles'];self.config.bombs=preset['bombs']
        self.weapon='AIM-120C7' if self.config.missiles else 'Mk-82'
        if self.config.mission not in row['missions']:self.config.mission=row['missions'][0]
        if self.config.mission=='intercept_patrol':self.config.missiles=6;self.config.bombs=0
        filtered=self.filtered_aircraft()
        index=next((i for i,r in enumerate(filtered) if r['id']==id),None)
        if index is None:self.aircraft_search='';filtered=self.filtered_aircraft();index=next(i for i,r in enumerate(filtered) if r['id']==id)
        self.aircraft_scroll=max(0,min(max(0,len(filtered)-4),index-3))
        if self.config.library_aircraft:
            self.config.speed=max(80,min(800,row['validation'].get('initial_speed_mps',200)))
            self.config.altitude=max(1000,min(19500,row['validation'].get('initial_altitude_m',5000)))
        else:
            self.config.speed=self.map.get('mission',{}).get('speed_mps',250)
        self.sim.reset(self.config);self.sim.set_paused(True);self.mode='hangar'
        self.configure_player_flight()
        self.camera_manual=False;self.chase.reset();self.menu_notice=''
        self._preview_model=None
        if self.renderer:self.renderer.reload()
        return row

    def filtered_aircraft(self):
        normalize=lambda s:''.join(c for c in s.casefold() if c.isalnum())
        words=[normalize(w) for w in self.aircraft_search.split()]
        return [r for r in self.aircraft_rows if all(w in normalize(r['id']+' '+r['display_name']) for w in words)]

    def set_loadout(self,id):
        row=aircraft(self.config.player_model);preset=loadout(row,id)
        self.config.missiles=preset['missiles'];self.config.bombs=preset['bombs']
        self.weapon='AIM-120C7' if self.config.missiles else 'Mk-82'
        if self.mode=='hangar':self.sim.reset(self.config);self.sim.set_paused(True);self.configure_player_flight()

    def current_aircraft(self):
        return next(r for r in self.aircraft_rows if r['simulation_model']==self.config.player_model)

    def close(self):
        if self.closed:return
        try:self.finish_sortie('closed')
        finally:
            self.closed=True;self.sim.close()
            if self.renderer:self.renderer.close()

    def finish_sortie(self,reason,error=None):
        if self.journal.current:self.journal.finish(reason,serialize(self.sim.frame()),error)

    def log_paths(self):return self.journal.paths()

    def configure_player_flight(self):
        self.player_profile=self.profile_store.apply(self.sim,native,self.current_aircraft()['id'])
        self.player_input=PlayerInputAdapter(self.player_profile,unit(self.player().velocity))
        self.chase.settings=self.player_profile['camera']

    def reload_player_flight(self):
        if self.player_profiles_frozen:raise ValueError('Player profiles are frozen for this evaluation')
        if not self.sim.frame().paused:raise ValueError('Press P to pause before reloading player profiles')
        candidate=PlayerProfileStore(self.profile_store.path)
        resolved=candidate.apply(self.sim,native,self.current_aircraft()['id'])
        self.profile_store=candidate;self.player_profile=resolved;self.player_input.profile=resolved;self.chase.settings=resolved['camera']
        self.journal.record('player_profile_reload',resolved,self._journal_tick)
        return resolved

    def apply_recorded_player_profile(self,profile):
        if profile['aircraft_id']!=self.current_aircraft()['id']:raise ValueError('Recorded player profile belongs to a different aircraft')
        self.sim.configure_player_flight(self.profile_store.native_resolved(native,profile))
        self.player_profile=profile;self.player_input.profile=profile;self.chase.settings=profile['camera']

    def submit_player(self,intent=None,**values):
        if intent is None:intent=native_intent(native,values)
        self._dispatch_player_intent(intent)
        self.player_input.adopt_direction(intent.direction)
        self.player_input.mode='raw_manual' if intent.mode==native.PlayerFlightMode.RawManual else 'assisted'

    def _dispatch_player_intent(self,intent):
        # The client adapter already owns its filtered/raw pointer state.
        # Only the public typed API performs an external-input handoff.
        self.throttle=max(0,min(1,float(intent.throttle)))
        self.sim.submit_player(intent)
        self.journal.record('player_intent',serialize(intent),self._journal_tick)

    def submit_command(self,command):
        self.sim.submit(command)
        self.journal.record('command',serialize(command),self._journal_tick)

    def player(self,frame=None):
        return next((e for e in (frame or self.sim.frame()).entities if e.uid=='player'),None)

    def command(self,**kwargs):
        if 'throttle' in kwargs:self.throttle=max(0,min(1,float(kwargs['throttle'])))
        c=native.PilotCommand()
        p=self.player()
        c.heading=p.orientation[2] if p else 0;c.throttle=self.throttle
        for k,v in kwargs.items():setattr(c,k,v)
        self.submit_command(c)

    def step(self,ticks=1):
        try:self.sim.step(ticks)
        except Exception as error:
            self.finish_sortie('exception',str(error));raise
        self.journal.record('step',{'ticks':ticks,'exact':False},self._journal_tick)
        frame=self.sim.frame();self._journal_tick=frame.tick
        if frame.result!='running':self.mode='result';self.finish_sortie('result')
        return frame

    def step_exact(self,ticks=1):
        self.sim.step_exact(ticks);self.journal.record('step',{'ticks':ticks,'exact':True},self._journal_tick)
        frame=self.sim.frame();self._journal_tick=frame.tick
        if frame.result!='running':self.mode='result';self.finish_sortie('result')
        return frame

    def set_camera(self,eye,target,fov=1.05,manual=True,up=None):
        if len(eye)!=3 or len(target)!=3 or not all(math.isfinite(v) for v in [*eye,*target,fov]) or not .3<=fov<=1.6 or math.dist(eye,target)<.1:raise ValueError('Camera requires finite eye/target, a nonzero direction and FOV in [0.3,1.6]')
        self.camera_manual=manual
        self.camera_params={'eye':list(eye),'target':list(target),'fov':fov}
        if self.renderer:self.renderer.camera(eye,target,fov)
        if up is not None:
            if len(up)!=3 or not all(math.isfinite(v) for v in up) or math.hypot(*up)<.1:raise ValueError('Camera up must be a finite nonzero vector')
            self.camera_params['up']=list(up)
            if self.renderer and hasattr(self.renderer,'camera_up'):self.renderer.camera_up(up)

    def follow_camera(self,dt,free=False,aim=None):
        if self.camera_manual:return
        p=self.player()
        if not p:return
        north,west,alt=p.position;yaw=p.orientation[2]
        if self.mode=='hangar':
            row=self.current_aircraft();bounds=row['appearance'].get('bounds')
            center=[0,3,0];scale=1
            if bounds:
                lo,hi=bounds['min'],bounds['max'];center=[(lo[0]+hi[0])/2,2.1+(lo[2]+hi[2])/2,(lo[1]+hi[1])/2]
                scale=max(.35,max(bounds['span'])/19)
                if row.get('library_aircraft'):center[1]+=max(0,-lo[2])
            self.set_camera([center[0]+26*scale,center[1]+9*scale,center[2]-26*scale],
                            [center[0]-6*scale,center[1],center[2]],.92,manual=False);return
        else:
            bounds=self.current_aircraft()['appearance'].get('bounds')
            self.chase.scale=max(.35,max(bounds['span'])/19) if bounds else 1
            self.chase.subject_offset_blender=[(a+b)/2 for a,b in zip(bounds['min'],bounds['max'])] if bounds else [0,0,0]
            eye,target,fov,up=self.chase.update(p,dt,free,aim or self.aim,self.width,self.height,getattr(self,'zoom',False))
            self.camera_state=eye;self.set_camera(eye,target,fov,manual=False,up=up)

    def capture(self,name='frame'):
        if not self.renderer:raise RuntimeError('Capture needs --render')
        self.draw(0)
        frame=self.sim.frame();base=self.output/(name+f'_tick{frame.tick:06d}')
        image=self.renderer.capture(str(base.with_suffix('.png')))
        used={e.model for e in frame.entities}
        if self.baked_scene:
            for id,version in self.baked_scene.document['resource_versions'].items():
                used.add(id)
                used.update(id+'::lod'+str(i) for i in range(1,len(version['lods'])))
        metadata={'scene':str(self.map_path),'scene_sha256':self.scene_hash,'tick':frame.tick,'seed':self.config.seed,'camera':self.camera_params,'quality':self.quality,'frame':serialize(frame),'assets':{k:hashlib.sha256(Path(v).read_bytes()).hexdigest() for k,v in self.runtime.get('models',{}).items() if k in used},'textures':{k:hashlib.sha256(Path(v).read_bytes()).hexdigest() for k,v in self.runtime.items() if k.endswith('_texture')},'shader_errors':self.renderer.shader_errors()}
        metadata['asset_scope']='Current frame models and all registered map LODs; unloaded library aircraft are excluded.'
        metadata['mission_mode']=frame.mission
        metadata['aircraft_id']=self.config.player_model
        metadata['resolution']=[self.width,self.height]
        metadata['visual_settings']=json.loads(self.renderer.visual_settings()) if hasattr(self.renderer,'visual_settings') else {}
        metadata['core_sha256']=hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest()
        metadata['renderer_sha256']=hashlib.sha256(Path(self.r.__file__).read_bytes()).hexdigest()
        if hasattr(self.renderer,'memory_usage'):metadata['vram']=self.renderer.memory_usage()
        metadata['camera_mode']='manual' if self.camera_manual else 'follow'
        metadata['player_flight_profile']=self.player_profile
        metadata['player_flight_state']=serialize(self.sim.player_flight_state())
        metadata['mouse_projection']=self.player_input.last_projection
        metadata['flight_marks']=getattr(self,'flight_marks',{})
        metadata['flight_mark_labels']=getattr(self,'flight_mark_labels',{})
        metadata['flight_mark_projection']=getattr(self,'flight_mark_projection',{})
        metadata['hud_visible']=self.show_hud
        if hasattr(self.renderer,'audio_available'):metadata['audio']={'available':self.renderer.audio_available(),'play_counts':self.renderer.audio_counts()}
        if hasattr(self.renderer,'aircraft_statistics'):metadata['aircraft_statistics']=serialize(self.renderer.aircraft_statistics())
        metadata['hud_layout']=self.hud_layout
        metadata['camera_framing']=self.chase.framing_state
        if self.baked_scene:
            metadata['terrain_sha256']=self.baked_scene.document['terrain']['sha256']
            metadata['statistics']=serialize(self.renderer.statistics())
            for id,material in self.baked_scene.document['materials'].items():
                for slot in ['base_color','normal','roughness_map']:
                    if slot in material:metadata['textures'][id+':'+slot]=material[slot+'_sha256']
        base.with_suffix('.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf8')
        return image

    def hud(self):
        frame=self.sim.frame();p=self.player(frame);texts=[];lines=[]
        labels=Labels()
        sx=self.width/1920;sy=self.height/1080
        def text(x,y,s,size=20,color=WHITE):
            t=self.r.HudText();t.x=x*sx;t.y=y*sy;t.text=s;t.size=int(size*sy);t.color=color;texts.append(t)
        def line(x,y,w,h=1,color=GREEN,rotation=0):
            l=self.r.HudLine();l.x=x*sx;l.y=y*sy;l.w=w*sx;l.h=h*sy;l.color=color;l.rotation=rotation;lines.append(l)
        def panel(x,y,w,h):line(x,y,w,h,0xb51b211b)
        def box(x,y,w,h,color=GREEN):
            line(x,y,w,1,color);line(x,y+h,w,1,color);line(x,y,1,h,color);line(x+w,y,1,h,color)
        def segment(x1,y1,x2,y2,color=GREEN,thick=1):
            dx,dy=x2-x1,y2-y1;length=math.hypot(dx,dy)
            line((x1+x2-length)/2,(y1+y2-thick)/2,length,thick,color,math.atan2(dy,dx))
        def circle(x,y,r,color):
            for i in range(24):
                a=math.tau*i/24;b=math.tau*(i+1)/24
                segment(x+r*math.cos(a),y+r*math.sin(a),x+r*math.cos(b),y+r*math.sin(b),color,2)
        if self.mode=='hangar':
            panel(0,0,520,1080);text(30,35,'BVR / FLIGHT OPERATIONS',28)
            text(30,90,'SELECT AIRCRAFT  /  CLICK OR SCROLL',17,GREEN)
            rows=self.filtered_aircraft()
            line(26,128,466,36,0xff35483c if self.search_active else 0xff25342c)
            text(38,135,('/ SEARCH: '+self.aircraft_search+('_' if self.search_active else ''))[:51],16,GREEN)
            text(30,1010,f'{len(rows)} aircraft | wheel / arrows / PgUp PgDn',15,MUTED)
            for index,row in enumerate(rows[self.aircraft_scroll:self.aircraft_scroll+4]):
                y=180+index*74;selected=row['id']==self.config.player_model
                line(26,y,466,66,0xff31583b if selected else 0xd52c342e)
                text(38,y+8,row['display_name'][:38],20,WHITE if row['available'] else MUTED)
                caption=' / '.join(row['supported_weapons']) or 'UNARMED'
                text(38,y+37,caption+'  |  '+(('TEST FLIGHT' if row.get('library_aircraft') else 'READY') if row['available'] else 'UNAVAILABLE'),14,GREEN if row['available'] else RED)
            row=self.current_aircraft();text(30,495,row['id']+'  /  '+row['fdm']['type'].upper(),22)
            for index,part in enumerate(textwrap.wrap(row['appearance']['variant_note'],59)[:3]):text(30,530+index*19,part,14,MUTED)
            text(30,599,'[M] MISSION: '+self.config.mission.upper(),20)
            text(30,633,'[L] LOADOUT',16,MUTED)
            text(30,660,f'{self.config.missiles} AIM-120C7  /  {self.config.bombs} Mk-82',21)
            text(30,700,'[G] ENEMY WEAPONS: '+('LIVE' if self.config.enemy_attacks else 'TRAINING'),16)
            text(30,729,'[Q] QUALITY: '+self.quality.upper(),16)
            line(40,760,390,70,0xff31583b);text(85,780,'ENTER  /  TAKE TO THE SKY',24)
            notice=self.menu_notice or row['unavailable_reason'] or ('Flight: '+row['validation']['flight'])
            for index,part in enumerate(textwrap.wrap(notice,55)[:3]):text(30,855+index*19,part,14,RED if self.menu_notice else MUTED)
            text(30,912,'F9 LOGS / game/logs/sorties',16,MUTED)
            text(30,943,'Mouse aim | W push DOWN / S pull UP',16)
            text(30,975,'R lock | Space fire | B bomb | C look | P pause',15)
            text(550,1020,'FlightGear / Wicked Engine / Kenney / ambientCG / Poly Haven',17,MUTED)
            return texts,lines
        speed=math.sqrt(sum(v*v for v in p.velocity)) if p else 0
        standalone=getattr(self,'entry_point','')=='aircraft_library.fly'
        text(40,30,'UNARMED PLAYER TEST FLIGHT' if standalone else 'BVR / '+frame.mission.upper(),22)
        text(40,77,f'THR   {(p.throttle if p else self.throttle)*100:3.0f} %',22)
        text(40,108,f'SPD   {speed*3.6:4.0f} km/h',22)
        text(40,139,f'ALT   {p.position[2] if p else 0:5.0f} m',22)
        text(40,170,f'MACH  {p.mach if p else 0:.2f}',22)
        text(40,213,f'AAM   {frame.missiles_left}   AIM-120C7',20)
        text(40,244,f'BOMB  {frame.bombs_left}   Mk-82',20)
        text(40,285,'SELECTED  '+self.weapon,18,GREEN)
        text(40,320,'P / PAUSE' if not frame.paused else 'PAUSED  |  P resume, . step',18,GREEN)
        text(40,350,'F9 / OPEN SORTIE LOGS',16,MUTED)
        text(40,1018,f'{self.fps:.0f} FPS   {frame.sim_time:6.1f}s',18,MUTED)
        line(610,35,350,4,BLUE);line(960,35,350,4,RED)
        text(610,57,'BLUE: PLAYER',18,BLUE);text(1110,57,'RED: HOSTILE',18,RED)
        if frame.mission=='intercept_patrol':
            text(610,88,f'INTERCEPT / GROUP {frame.mission_wave}/{frame.mission_total}   DESTROYED {frame.air_kills}/{frame.mission_kills_required}',17,GREEN)
            text(610,110,'SEARCH NORTH / SUPPORT YOUR MISSILE / F9 REPLAY LOGS',14,MUTED)
        state=self.sim.player_flight_state()
        text(610,1018,'F5 '+self.player_input.mode.upper()+'  /  F6 reload while paused',15,MUTED)
        if state.energy_limited:text(610,968,'ENERGY / CLIMB DEMAND LIMITED',15,0xff77dfff)
        elif state.protecting:text(610,968,'ASSIST / ENVELOPE LIMIT',15,0xff77dfff)
        if self.menu_notice:
            for index,part in enumerate(textwrap.wrap(self.menu_notice,42)[:2]):text(40,380+index*18,part,14,RED)
            labels.rectangles.append((30,375,410,425))
        # Three different symbols: amber aim ring, white nose cross, cyan path
        # ring/wings. All positions are projected from real world directions.
        self.flight_marks={};self.flight_mark_labels={};self.flight_mark_projection={};mark_label_boxes=[]
        if p:
            distance=self.player_profile['input']['aim_distance_m']
            for name,direction,color in [('AIM',self.player_input.direction,0xff77dfff),('NOSE',body_forward(p.orientation),WHITE),('PATH',unit(p.velocity),0xfff5e575)]:
                mark=self.renderer.project([p.position[i]+direction[i]*distance for i in range(3)])
                if name!='AIM' and not 0<mark[2]<1:continue
                x,y=mark[0]/sx,mark[1]/sy
                caption=name
                if name=='AIM':
                    placement=aim_marker(direction,self.camera_params,mark,self.width,self.height)
                    x,y=placement['point']
                    self.flight_mark_projection['AIM']=placement
                    if placement['edge']:
                        a=placement['bearing'];dx,dy=math.cos(a),math.sin(a)
                        for side in [-1,1]:segment(x,y,x-dx*18-side*dy*8,y-dy*18+side*dx*8,color,2)
                        caption='AIM / BEHIND' if placement['behind'] else 'AIM / OFF VIEW'
                    else:circle(x,y,12,color)
                elif name=='NOSE':line(x-9,y,18,2,color);line(x,y-9,2,18,color)
                else:circle(x,y,5,color);line(x-16,y,9,2,color);line(x+7,y,9,2,color);line(x,y-12,2,5,color)
                for dy in [-24,0,24,-48,48]:
                    label=(x+18,y+dy,max(52,len(caption)*7),18)
                    if not any(label[0]<b[0]+b[2] and label[0]+label[2]>b[0] and abs(label[1]-b[1])<20 for b in mark_label_boxes):break
                mark_label_boxes.append(label);text(label[0],label[1],caption,12,color)
                labels.rectangles.extend([(label[0],label[1],label[0]+label[2],label[1]+label[3]),(x-16,y-16,x+16,y+16)])
                self.flight_mark_labels[name]=list(label);self.flight_marks[name]=[x*sx,y*sy]
        for c in frame.contacts:
            v=self.renderer.project(c.position)
            if 0<v[2]<1:
                x,y=min(max(v[0]/sx,450),1490),min(max(v[1]/sy,200),760);color=GREEN if c.locked else RED
                box(x-22,y-22,44,44,color)
                distance=math.dist(p.position,c.position)/1000
                caption=c.uid+'  '+f'{distance:.1f} km'+(' / STT LOCK' if c.locked else '')
                lx,ly=labels.place(x+28,y-18,caption);text(lx,ly,caption,18,color)
        # Combined RWR bearing ring and range-accurate sensor/SA plot.
        cx,cy,outer,plot=255,770,145,112
        # Dedicated forward radar display alongside the all-around warning/SA ring.
        # Plot only onboard radar tracks; never substitute world entity positions.
        rx,ry,rw,rh=1535,165,355,430
        panel(rx,ry,rw,rh);box(rx,ry,rw,rh,0xff496c55)
        text(rx+16,ry+14,'RADAR / '+('NO SENSOR' if self.config.library_aircraft else frame.radar_mode.upper()),20,GREEN)
        text(rx+16,ry+44,f'{frame.radar_range/1000:.0f} km   AZ -60 / +60',16,MUTED)
        gx,gy,gw,gh=rx+30,ry+87,rw-60,rh-140
        for fraction in (0,.25,.5,.75,1):
            line(gx,gy+gh*fraction,gw,1,0xff354f40)
        for fraction in (0,.5,1):line(gx+gw*fraction,gy,1,gh,0xff354f40)
        sweep=(frame.tick%200)/200;line(gx+gw*sweep,gy,1,gh,0xff416f4d)
        if p:
            for contact in frame.contacts:
                dn=contact.position[0]-p.position[0];dw=contact.position[1]-p.position[1]
                az=math.remainder(math.atan2(dw,dn)-p.orientation[2],2*math.pi)
                distance=math.hypot(dn,dw)
                if abs(az)<=math.pi/3 and distance<=frame.radar_range:
                    x=gx+gw*(.5+az/(2*math.pi/3));y=gy+gh*(1-distance/max(frame.radar_range,1))
                    color=BLUE if contact.locked else GREEN;box(x-5,y-4,10,8,color)
                    text(min(x+9,rx+rw-100),y-7,contact.uid[:11],14,color)
        text(rx+16,ry+rh-33,'UNARMED TEST FLIGHT' if self.config.library_aircraft else 'R / TAB lock   '+str(len(frame.contacts))+' tracks',15,MUTED)
        for i in range(48):
            a0=2*math.pi*i/48-math.pi/2;a1=2*math.pi*(i+1)/48-math.pi/2
            segment(cx+outer*math.cos(a0),cy+outer*math.sin(a0),cx+outer*math.cos(a1),cy+outer*math.sin(a1),0xff4b6657,2)
        for fraction in (.33,.66,1):
            rr=plot*fraction
            for i in range(48):
                a0=2*math.pi*i/48-math.pi/2;a1=2*math.pi*(i+1)/48-math.pi/2
                segment(cx+rr*math.cos(a0),cy+rr*math.sin(a0),cx+rr*math.cos(a1),cy+rr*math.sin(a1),0x995c8067,1)
        for i in range(24):
            a=2*math.pi*i/24-math.pi/2
            segment(cx+(outer-4)*math.cos(a),cy+(outer-4)*math.sin(a),cx+(outer+2)*math.cos(a),cy+(outer+2)*math.sin(a),0xff718a78,2)
        text(cx-47,cy-outer-31,'RWR / SA',18,GREEN)
        text(cx-25,cy-10,'N',14,MUTED)
        text(cx-28,cy+outer+9,f'{frame.radar_range/1000:.0f} km',16,MUTED)
        text(cx-65,cy+outer+31,'SA  /  RWR  /  MWS',13,MUTED)
        # Contacts are onboard radar observations only. RWS is rendered as a bearing tick;
        # MWS localization can be ranged and is shown inside in amber.
        if p:
            for c in frame.contacts:
                dx=c.position[0]-p.position[0];dy=c.position[1]-p.position[1]
                bearing=math.remainder(math.atan2(dy,dx)-p.orientation[2],2*math.pi);dist=math.hypot(dx,dy)
                radius=plot*min(dist/max(frame.radar_range,1),1)
                px=cx+radius*math.sin(bearing);py=cy-radius*math.cos(bearing)
                color=BLUE if c.locked else 0xff73e6e6
                box(px-4,py-4,8,8,color)
            for w in frame.warnings:
                if w.localized:
                    radius=plot*min(w.range/max(frame.radar_range,1),1)
                    px=cx+radius*math.sin(w.bearing);py=cy-radius*math.cos(w.bearing)
                    box(px-5,py-5,10,10,0xff45aaff)
                else:
                    a=w.bearing-math.pi/2
                    segment(cx+(outer-9)*math.cos(a),cy+(outer-9)*math.sin(a),cx+(outer+1)*math.cos(a),cy+(outer+1)*math.sin(a),RED,4)
        if frame.envelope.target_uid:
            z=frame.envelope;panel(1535,650,355,270)
            text(1550,670,'AIM-120 / LAUNCH ZONE',19,GREEN)
            text(1550,705,f'R {z.range/1000:.1f} km / AZ {math.degrees(z.bearing):+.0f} deg',18)
            text(1550,738,f'Vc {z.closing_speed:+.0f} m/s',18)
            text(1550,771,f'Rmax {z.rmax/1000:.1f} / Rtr {z.rtr/1000:.1f} km',17)
            text(1550,805,'IN ZONE' if z.in_range else 'OUT OF ZONE',21,GREEN if z.in_range else RED)
            text(1550,843,'1-D estimate / no kill guarantee',15,MUTED)
        for i,m in enumerate([x for x in frame.missiles if x.owner=='player'][-3:]):
            eta=f'{m.eta:.1f}s' if m.eta>=0 else 'opening'
            text(40,440+i*62,f'AIM-120 IN FLIGHT / {m.age:.1f}s',18,GREEN)
            text(40,465+i*62,f'{m.range/1000:.1f} km / ETA ~{eta} / '+('ACTIVE' if m.seeker_active else 'MIDCOURSE'),17)
        if frame.mission in ('strike','combined'):
            target=self.map['ground_target']['position'];q=self.renderer.project(target)
            if 0<q[2]<1:
                x,y=min(max(q[0]/sx,450),1490),min(max(q[1]/sy,200),760);box(x-16,y-16,32,32,RED)
                lx,ly=labels.place(x+20,y,'DEPOT / MISSION OBJECTIVE',17);text(lx,ly,'DEPOT / MISSION OBJECTIVE',17,RED)
            if frame.bomb_impact and self.weapon=='Mk-82':
                q=self.renderer.project(frame.bomb_impact)
                if 0<q[2]<1:
                    x,y=min(max(q[0]/sx,450),1490),min(max(q[1]/sy,200),760);line(x-25,y,50,2);line(x,y-25,2,50)
                    lx,ly=labels.place(x+30,y,'CCIP',17);text(lx,ly,'CCIP',17,GREEN)
        text(740,135,'RWR / '+frame.rwr_mode.upper(),24,RED if frame.rwr_mode in ('lock','missile') else GREEN)
        recent=[e for e in frame.events if frame.tick-e.tick<300 and e.kind not in ('sortie_started',)]
        for i,e in enumerate(recent[-4:]):
            own_loss=e.target=='player' and e.kind in ('missile_hit','aircraft_destroyed')
            message=('INCOMING MISSILE HIT' if e.kind=='missile_hit' else 'YOUR AIRCRAFT DESTROYED') if own_loss else e.message
            text(650,840+i*28,message,22,RED if own_loss else GREEN if 'hit' in e.kind or 'destroyed' in e.kind else WHITE)
        panel(580,980,760,60)
        text(600,995,'W/S pitch  A/D roll  C look  RMB zoom  ESC close' if standalone else 'V weapon   R lock   SPACE launch   B release   ESC hangar',18)
        if self.mode=='result':
            panel(600,310,720,410);text(665,355,'MISSION '+frame.result.upper(),38,GREEN if frame.result=='succeeded' else RED)
            text(665,440,f'AIR KILLS {frame.air_kills}    GROUND KILLS {frame.ground_kills}',24)
            text(665,495,f'FLIGHT TIME {frame.sim_time:.1f} s',22)
            if frame.result=='failed':
                reason='SHOT DOWN / INCOMING MISSILE' if any(e.kind=='missile_hit' and e.target=='player' for e in frame.events) else 'AIRCRAFT LOST' if p and not p.alive else 'TIME LIMIT / OBJECTIVES INCOMPLETE'
                text(665,535,reason,19,RED)
            text(665,575,'ENTER / FLY AGAIN',26);text(665,635,'ESC / RETURN TO HANGAR',20)
            text(665,680,'F9 / OPEN THIS SORTIE ACMI + CORE LOG',18,GREEN)
        self.hud_layout=labels.placed
        return texts,lines

    def draw(self,dt=1/60,*,free=False):
        if not self.renderer:return
        if hasattr(self.renderer,'presentation'):self.renderer.presentation(self.mode=='hangar')
        if self.mode=='hangar' and self.current_aircraft().get('library_aircraft'):
            model=self.config.player_model
            if self._preview_model!=model:
                self.renderer.preview_aircraft(model,self.player().animation_properties,0.)
                self._preview_model=model
        self.follow_camera(dt,free=free)
        texts,lines=self.hud() if self.show_hud else ([],[])
        if not self.show_hud:self.hud_layout=[]
        start=time.perf_counter()
        if getattr(self.r,'VISUAL_BETA',False):self.renderer.render(self.sim.frame(),texts,lines,dt)
        else:self.renderer.render(self.sim.frame(),texts,lines)
        self.frame_times.append(time.perf_counter()-start)
        if not self.interactive:self.fps=1/max(statistics.median(self.frame_times[-60:]),1e-6)

    def run_client_frame(self,event,dt,accumulator=0.):
        """Shared interactive frame for the game and standalone test flight.

        Frame time schedules unchanged fixed core ticks; presentation never
        changes the core dt. Headless clients advance the same camera math.
        """
        if not math.isfinite(dt) or dt<0:raise ValueError('Client frame time must be finite and nonnegative')
        dt=min(dt,.1);self.fps=.9*self.fps+.1/max(dt,.0001)
        if not self.input(event,dt):return False,0.
        if self.mode=='flight':
            accumulator+=dt;ticks=min(int(accumulator/self.config.dt),5)
            if ticks:self.step(ticks);accumulator-=ticks*self.config.dt
        else:accumulator=0.
        if self.renderer:self.draw(dt,free=67 in event.held)
        else:self.follow_camera(dt,free=67 in event.held)
        return True,accumulator

    def input(self,event,dt):
        held=set(event.held);pressed=set(event.pressed)
        if getattr(event,'width',0)>0 and getattr(event,'height',0)>0:self.width,self.height=event.width,event.height
        if event.quit:return False
        if 120 in pressed:
            try:self.last_log_opened=open_logs_directory(self.log_paths())
            except OSError as error:self.menu_notice='Cannot open logs: '+str(error)
            return True
        self.aim=(min(max(event.x,0),self.width),min(max(event.y,0),self.height))
        if 123 in pressed:self.capture('manual') # F12
        if 81 in pressed:
            self.quality=['low','medium','high'][(['low','medium','high'].index(self.quality)+1)%3];self.renderer.set_quality(self.quality)
        if self.mode=='hangar':
            if 191 in pressed or (1 in pressed and 26<=event.x/self.width*1920<=492 and 128<=event.y/self.height*1080<=164):
                self.search_active=True;return True
            if self.search_active:
                if 27 in pressed:self.aircraft_search='';self.search_active=False
                elif 13 in pressed:self.search_active=False
                else:
                    if 8 in pressed:self.aircraft_search=self.aircraft_search[:-1]
                    for key in sorted(pressed):
                        if 65<=key<=90 or 48<=key<=57:self.aircraft_search+=chr(key)
                        elif key==32:self.aircraft_search+=' '
                        elif key in (189,109):self.aircraft_search+='-'
                    self.aircraft_search=self.aircraft_search[:48]
                self.aircraft_scroll=0;return True
            rows=self.filtered_aircraft()
            wheel=getattr(event,'wheel',0)
            if wheel or pressed.intersection({38,40,33,34,36,35}):
                delta=-int(math.copysign(1,wheel)) if wheel else (4 if 34 in pressed else -4 if 33 in pressed else 1 if 40 in pressed else -1)
                self.aircraft_scroll=max(0,min(max(0,len(rows)-4),self.aircraft_scroll+delta))
                if 36 in pressed:self.aircraft_scroll=0
                if 35 in pressed:self.aircraft_scroll=max(0,len(rows)-4)
            selected=None
            for index,row in enumerate(self.aircraft_rows[:5]):
                if 49+index in pressed:selected=row['id']
            if 1 in pressed and 26<=event.x/self.width*1920<=492:
                slot=int((event.y/self.height*1080-180)//74)
                if 0<=slot<4 and self.aircraft_scroll+slot<len(rows):selected=rows[self.aircraft_scroll+slot]['id']
            if selected:
                try:self.select_aircraft(selected)
                except (ValueError,FileNotFoundError) as error:self.menu_notice=str(error)
            row=self.current_aircraft()
            if 77 in pressed:
                missions=[m for m in ['intercept_patrol','air','strike','combined','convoy','training'] if m in row['missions'] and (m!='convoy' or self.map.get('mission',{}).get('ground_units'))]
                self.config.mission=missions[(missions.index(self.config.mission)+1)%len(missions)] if self.config.mission in missions else missions[0]
                if self.config.mission=='intercept_patrol':self.config.missiles=6;self.config.bombs=0;self.config.enemy_attacks=True
            if 76 in pressed:
                if self.config.mission=='intercept_patrol':self.menu_notice='Patrol uses the fixed 6 x AIM-120C7 intercept loadout'
                else:
                    presets=row['legal_loadouts'];index=next((i for i,v in enumerate(presets) if (v['missiles'],v['bombs'])==(self.config.missiles,self.config.bombs)),-1)
                    self.set_loadout(presets[(index+1)%len(presets)]['id'])
            if 71 in pressed and not row.get('library_aircraft') and self.config.mission!='intercept_patrol':self.config.enemy_attacks=not self.config.enemy_attacks
            click=1 in pressed and 40/1920*self.width<=event.x<=430/1920*self.width and 760/1080*self.height<=event.y<=830/1080*self.height
            if 13 in pressed or click:self.start()
            if 27 in pressed:return False
            return True
        if 27 in pressed:self.finish_sortie('returned_to_hangar');self.mode='hangar';self.sim.set_paused(True);return True
        if self.mode=='result':
            if 13 in pressed:self.start()
            return True
        frame=self.sim.frame()
        if 80 in pressed:
            self.sim.set_paused(not frame.paused)
            self.journal.record('pause',not frame.paused,self._journal_tick)
        if 116 in pressed:self.player_input.mode='raw_manual' if self.player_input.mode=='assisted' else 'assisted'
        if 117 in pressed:
            try:self.reload_player_flight();self.menu_notice='Player profile reloaded: '+self.player_profile['effective_sha256'][:10]
            except (ValueError,RuntimeError) as error:self.menu_notice=str(error)
        if 190 in pressed:self.step_exact()
        if 86 in pressed:
            weapons=self.current_aircraft()['supported_weapons']
            if weapons:self.weapon=weapons[(weapons.index(self.weapon)+1)%len(weapons)] if self.weapon in weapons else weapons[0]
        self.throttle=max(0,min(1,self.throttle+getattr(event,'wheel',0)*.05))
        self.throttle=self.player_input.throttle(self.throttle,event,dt)
        self.zoom=2 in held
        p=self.player(frame)
        if not p:return True
        camera=self.camera_params
        if not camera:
            d=unit(p.velocity);camera={'eye':[-p.position[1],p.position[2],p.position[0]],'target':[-p.position[1]-d[1]*1000,p.position[2]+d[2]*1000,p.position[0]+d[0]*1000],'up':[0,1,0],'fov':self.player_profile['camera']['normal_fov']}
        values=self.player_input.update(event,dt,p,camera,self.width,self.height,
            hold_direction=67 in held or max(map(abs,self.chase.free))>.01)
        c=native_intent(native,{**values,'throttle':self.throttle})
        if 82 in pressed or 9 in pressed:
            candidates=[x.uid for x in frame.contacts]
            if candidates:
                self.target=candidates[(candidates.index(self.target)+1)%len(candidates)] if self.target in candidates else candidates[0]
                c.lock=True;c.target_uid=self.target
        c.fire=(32 in pressed or 1 in pressed) and self.weapon=='AIM-120C7';c.target_uid=self.target;c.weapon='AIM-120C7'
        c.drop_bomb=66 in pressed or (32 in pressed and self.weapon=='Mk-82')
        self._dispatch_player_intent(c);return True

def acceptance(game,mission,max_ticks=5000):
    """Repeatable real combat using the same typed commands as human input."""
    if game.baked_scene:return acceptance_alpha(game,mission)
    game.config.mission=mission;game.config.enemy_range=3500;game.config.enemy_attacks=False;game.start()
    game.weapon='Mk-82' if mission=='strike' else 'AIM-120C7'
    released=False;fired=False;captures=[]
    if game.renderer:
        for _ in range(20):game.draw()
        captures.append(game.capture(mission+'_start'))
    launch_captured=False
    while game.sim.frame().tick<max_ticks:
        f=game.sim.frame()
        if mission!='strike' and not fired and f.contacts:
            game.command(lock=True,fire=True,target_uid=f.contacts[0].uid);fired=True
        if mission!='air' and not released and f.bomb_impact and math.dist(f.bomb_impact,game.map['ground_target']['position'])<25:
            game.command(drop_bomb=True);released=True
        game.step(2)
        if game.renderer and game.sim.frame().tick%2==0:game.draw()
        if game.renderer and (fired or released) and not launch_captured:
            captures.append(game.capture(mission+'_weapon_away'));launch_captured=True
        if game.sim.frame().result!='running':break
    f=game.sim.frame()
    if game.renderer:
        for _ in range(5):game.draw()
        captures.append(game.capture(mission+'_result'))
    report={'mission':mission,'frame':serialize(f),'captures':captures,'render_frames':len(game.frame_times),'render_ms_median':statistics.median(game.frame_times)*1000 if game.frame_times else None,'shader_errors':game.renderer.shader_errors() if game.renderer else None}
    (game.output/(mission+'_report.json')).write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({'mission':mission,'result':f.result,'tick':f.tick,'air_kills':f.air_kills,'ground_kills':f.ground_kills,'captures':captures}),flush=True)
    if f.result!='succeeded':raise RuntimeError('Combat acceptance failed: '+mission)
    return report

def acceptance_alpha(game,mission):
    from .pilots import CombatPilot,StrikePilot
    game.config.mission=mission;game.start();combat=CombatPilot();strike=StrikePilot(game.map['ground_target']['position']);captures=[];away=False
    game.weapon='Mk-82' if mission=='strike' else 'AIM-120C7'
    if game.renderer:
        for _ in range(20):game.draw()
        captures.append(game.capture(mission+'_start'))
    while game.sim.frame().tick<(15000 if mission=='combined' else 9000):
        frame=game.sim.frame();pilot=strike if mission=='strike' or frame.air_kills else combat
        game.weapon='Mk-82' if pilot is strike else 'AIM-120C7';game.command(**pilot.command(frame,game.player(frame)));frame=game.step(5)
        if game.renderer:
            game.draw()
            if not away and any(e.kind in ('missile_launched','bomb_released') and e.actor=='player' for e in frame.events):captures.append(game.capture(mission+'_weapon_away'));away=True
        if frame.result!='running':break
    frame=game.sim.frame()
    if game.renderer:
        for _ in range(5):game.draw()
        captures.append(game.capture(mission+'_result'))
    report={'mission':mission,'frame':serialize(frame),'captures':captures,'render_frames':len(game.frame_times),'shader_errors':game.renderer.shader_errors() if game.renderer else None,'map_sha256':game.scene_hash}
    (game.output/(mission+'_report.json')).write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({'mission':mission,'result':frame.result,'tick':frame.tick,'sim_seconds':frame.sim_time,'air_kills':frame.air_kills,'ground_kills':frame.ground_kills}),flush=True)
    if frame.result!='succeeded':raise RuntimeError('Alpha combat acceptance failed: '+mission)
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['play','run','benchmark'],nargs='?',default='play')
    p.add_argument('--render',action='store_true');p.add_argument('--hidden',action='store_true');p.add_argument('--mission',choices=['intercept_patrol','air','strike','combined','convoy','training']);p.add_argument('--aircraft',choices=[r['id'] for r in aircraft_catalog(include_library=True)['aircraft']],default='F22');p.add_argument('--loadout');p.add_argument('--seed',type=int,default=7)
    p.add_argument('--width',type=int,default=1920);p.add_argument('--height',type=int,default=1080);p.add_argument('--quality',choices=['low','medium','high'],default='high');p.add_argument('--frames',type=int,default=300);p.add_argument('--output',type=Path,default=GAME/'captures');p.add_argument('--runtime',type=Path,default=GAME/'runtime.json');p.add_argument('--map',type=Path,default=DEFAULT_WORLD_MAP)
    p.add_argument('--visual-profile',type=Path,default=DEFAULT_VISUAL_PROFILE)
    a=p.parse_args();game=FlightGame(render=a.render or a.command=='play' or a.command=='benchmark',visible=not a.hidden,width=a.width,height=a.height,runtime=a.runtime,map_path=a.map,output=a.output,visual_profile=a.visual_profile)
    row=game.select_aircraft(a.aircraft,a.loadout)
    a.mission=a.mission or ('air' if a.command=='run' and 'air' in row['missions'] else row['missions'][0])
    if a.mission not in row['missions']:game.close();raise ValueError('Mission '+a.mission+' is unsupported for '+a.aircraft)
    game.config.mission=a.mission;game.config.seed=a.seed;game.quality=a.quality
    if a.mission=='intercept_patrol':game.config.missiles=6;game.config.bombs=0;game.config.enemy_attacks=True
    if game.renderer:game.renderer.set_quality(a.quality)
    try:
        if a.command=='run':
            if a.mission=='intercept_patrol':
                from .playtest import LocalCombatPilot,observe_local
                pilot=LocalCombatPilot(a.seed);game.start()
                while game.sim.frame().result=='running':
                    game.command(**pilot.command(observe_local(game)));game.step(25)
                    if game.renderer:game.draw()
                f=game.sim.frame();report={'mission':a.mission,'frame':serialize(f),'logs':game.log_paths(),'capture':game.capture('patrol_result') if game.renderer else None}
                (game.output/'intercept_patrol.json').write_text(json.dumps(report,indent=2),encoding='utf8')
                print(json.dumps({'mission':a.mission,'result':f.result,'tick':f.tick,'logs':game.log_paths()}),flush=True)
                if f.result!='succeeded':raise RuntimeError('Patrol failed: '+f.result)
            else:acceptance(game,a.mission)
        elif a.command=='benchmark':
            game.config.enemy_attacks=False;game.start()
            for _ in range(30):game.draw()
            samples=[]
            for i in range(a.frames):
                start=time.perf_counter();game.step();game.draw();samples.append(time.perf_counter()-start)
            result={'resolution':[a.width,a.height],'quality':a.quality,'frames':a.frames,'fps':len(samples)/sum(samples),'p50_ms':statistics.median(samples)*1000,'p95_ms':sorted(samples)[int(len(samples)*.95)]*1000,'tick':game.sim.frame().tick,'shader_errors':game.renderer.shader_errors(),'capture':game.capture('benchmark')}
            (game.output/'benchmark.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result),flush=True)
        else:
            game.interactive=True
            game.sim.reset(game.config);game.sim.set_paused(True);last=time.perf_counter();accumulator=0
            while True:
                now=time.perf_counter();dt=min(now-last,.1);last=now
                event=game.renderer.poll()
                running,accumulator=game.run_client_frame(event,dt,accumulator)
                if not running:break
    except BaseException as error:
        game.finish_sortie('exception',repr(error));raise
    finally:game.close()

if __name__=='__main__':main()
