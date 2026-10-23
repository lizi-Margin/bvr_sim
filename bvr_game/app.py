"""Flight Operations: typed simulation, optional Wicked renderer, CLI acceptance runs."""
from __future__ import annotations
import argparse, hashlib, importlib, json, math, os, statistics, sys, time
from .presentation import ChaseCamera,Labels,safe_aim,curve
from contextlib import redirect_stdout
from pathlib import Path
with redirect_stdout(sys.stderr):
    from bvr_sim.bvr_env_cpp import bvr_sim_cpp as native

ROOT=Path(__file__).resolve().parents[1]
GAME=Path(os.environ.get('BVR_GAME_ROOT',ROOT/'game'))
WHITE=0xffeeeeee; GREEN=0xff86f2a6; RED=0xff6d75ff; BLUE=0xffffc885; MUTED=0xffb3b6ad

def serialize(value):
    if isinstance(value,(str,int,float,bool,type(None))):return value
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
        if m['id']!=model.split('::')[0] or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
            raise ValueError('Asset registration/hash mismatch: '+model)
    for id,file in r.get('audio',{}).items():
        p=Path(file);manifest=json.loads((p.parent/'manifest.json').read_text(encoding='utf8'))
        if hashlib.sha256(p.read_bytes()).hexdigest()!=manifest['sounds'][id]['sha256']:raise ValueError('Audio registration/hash mismatch: '+id)
    return r

class FlightGame:
    """One owner steps GameSession. Renderer receives a value snapshot only."""
    def __init__(self,*,render=False,visible=True,width=1920,height=1080,runtime=GAME/'runtime.json',map_path=GAME/'maps/training.json',output=GAME/'captures'):
        self.output=Path(output).resolve();self.output.mkdir(parents=True,exist_ok=True)
        self.map_path=Path(map_path).resolve();self.map=json.loads(self.map_path.read_text(encoding='utf8'))
        self.baked_scene=None
        if self.map.get('schema_version')==2:
            from .scene_runtime import BakedScene
            self.baked_scene=BakedScene(self.map_path,self.map);self.map=self.baked_scene.compatibility_view()
        self.scene_hash=hashlib.sha256(self.map_path.read_bytes()).hexdigest()
        self.sim=native.GameSession(str(self.output/'simulation.log'))
        terrain=self.baked_scene.terrain(native) if self.baked_scene else native.GameTerrain()
        if not self.baked_scene:
            for k,v in self.map['terrain'].items():setattr(terrain,k,v)
        self.sim.set_terrain(terrain)
        self.config=native.GameConfig();self.config.enemy_range=9000;self.config.altitude=self.map['player_start'][2]
        if self.baked_scene:
            self.config.enemy_range=self.map['mission']['enemy_range_m'];self.config.speed=self.map['mission']['speed_mps'];self.config.enemy_evasion=True
        self.config.player_north,self.config.player_west=self.map['player_start'][:2]
        self.config.ground_north,self.config.ground_west=self.map['ground_target']['position'][:2]
        self.width,self.height=width,height;self.renderer=None;self.r=None;self.runtime={}
        self.mode='hangar';self.weapon='AIM-120C7';self.target='';self.throttle=.85
        self.camera_state=None;self.camera_params={};self.camera_manual=False;self.aim=(width/2,height/2)
        self.chase=ChaseCamera();self.hud_layout=[]
        self.show_hud=True
        self.quality='medium';self.last_event_tick=-1;self.fps=0;self.frame_times=[];self.closed=False;self.interactive=False
        self.start()
        self.mode='hangar';self.sim.set_paused(True)
        if render:
            self.runtime=load_runtime(runtime)
            sys.path.insert(0,self.runtime['renderer_module'])
            self.dll=os.add_dll_directory(self.runtime['renderer_module']) if os.name=='nt' else None
            self.r=importlib.import_module('bvr_game_render')
            self.renderer=self.r.Renderer(width,height,visible,self.runtime['engine_source'],self.runtime['shader_cache'],self.runtime['models'])
            if self.runtime.get('audio') and hasattr(self.renderer,'configure_audio'):self.renderer.configure_audio(self.runtime['audio'],visible)
            if self.baked_scene:self.baked_scene.configure(self.renderer,self.r,terrain)
            else:
                self.renderer.configure_world(terrain,self.map['ground_target']['position'],self.map['runway']['position'],self.map['runway']['length_m'],self.map['runway']['width_m'],self.map.get('scenery_seed',7),self.runtime.get('asphalt_texture',''),self.runtime.get('terrain_texture',''))
                for obj in self.map.get('assets',[]):
                    self.renderer.place_asset(obj['id'],obj['model'],obj['position'],obj.get('scale',1))

    def start(self):
        if self.baked_scene:
            start=self.map['mission']['strike_start'] if self.config.mission=='strike' else self.map['mission']['player_start']
            self.config.player_north,self.config.player_west,self.config.altitude=start
        self.sim.reset(self.config);self.mode='flight';self.target='';self.camera_state=None;self.camera_manual=False;self.last_event_tick=-1
        self.chase.reset()
        pilot=native.PilotCommand();pilot.throttle=self.throttle;self.sim.submit(pilot)
        if self.renderer:self.renderer.reload()

    def close(self):
        if self.closed:return
        self.closed=True;self.sim.close()
        if self.renderer:self.renderer.close()

    def player(self,frame=None):
        return next((e for e in (frame or self.sim.frame()).entities if e.uid=='player'),None)

    def command(self,**kwargs):
        if 'throttle' in kwargs:self.throttle=max(0,min(1,float(kwargs['throttle'])))
        c=native.PilotCommand()
        p=self.player()
        c.heading=p.orientation[2] if p else 0;c.throttle=self.throttle
        for k,v in kwargs.items():setattr(c,k,v)
        self.sim.submit(c)

    def step(self,ticks=1):
        self.sim.step(ticks)
        if self.sim.frame().result!='running':self.mode='result'
        return self.sim.frame()

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
            self.set_camera([26,12,-26],[-6,3,0],.92,manual=False);return
        else:
            eye,target,fov,up=self.chase.update(p,dt,free,aim or self.aim,self.width,self.height,getattr(self,'zoom',False))
            self.camera_state=eye;self.set_camera(eye,target,fov,manual=False,up=up)

    def capture(self,name='frame'):
        if not self.renderer:raise RuntimeError('Capture needs --render')
        self.draw(0)
        frame=self.sim.frame();base=self.output/(name+f'_tick{frame.tick:06d}')
        image=self.renderer.capture(str(base.with_suffix('.png')))
        metadata={'scene':str(self.map_path),'scene_sha256':self.scene_hash,'tick':frame.tick,'seed':self.config.seed,'camera':self.camera_params,'quality':self.quality,'frame':serialize(frame),'assets':{k:json.loads((Path(v).parent/'manifest.json').read_text(encoding='utf8'))['glb_sha256'] for k,v in self.runtime.get('models',{}).items()},'textures':{k:hashlib.sha256(Path(v).read_bytes()).hexdigest() for k,v in self.runtime.items() if k.endswith('_texture')},'shader_errors':self.renderer.shader_errors()}
        metadata['assets']={k:hashlib.sha256(Path(v).read_bytes()).hexdigest() for k,v in self.runtime.get('models',{}).items()}
        metadata['mission_mode']=frame.mission
        metadata['camera_mode']='manual' if self.camera_manual else 'follow'
        metadata['hud_visible']=self.show_hud
        if hasattr(self.renderer,'audio_available'):metadata['audio']={'available':self.renderer.audio_available(),'play_counts':self.renderer.audio_counts()}
        metadata['hud_layout']=self.hud_layout
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
        if self.mode=='hangar':
            panel(0,0,490,1080);text(40,40,'BVR / FLIGHT OPERATIONS',29)
            text(40,100,'SINGLE PLAYER',18,GREEN)
            text(40,170,'AIRCRAFT',17,MUTED);text(40,210,self.config.player_model+'  /  JSBSim',30)
            text(40,255,'[1] F-22A Raptor     [2] F-16',20)
            text(40,330,'MISSION',17,MUTED);text(40,370,self.config.mission.upper(),28)
            text(40,420,'[M] Air intercept / Strike / Combined',19)
            text(40,490,'LOADOUT',17,MUTED)
            text(40,530,f'{self.config.missiles} x AIM-120C7    {self.config.bombs} x Mk-82',23)
            text(40,575,'[L] Cycle missile / mixed / strike loadout',18)
            text(40,635,'[G] AI weapons: '+('LIVE' if self.config.enemy_attacks else 'TRAINING'),19)
            text(40,680,'[Q] Quality: '+self.quality.upper(),19)
            line(40,760,390,70,0xff31583b);text(85,780,'ENTER  /  TAKE TO THE SKY',24)
            text(40,890,'Mouse aim | W/S throttle | A/D roll',18)
            text(40,925,'R lock | Space fire | V weapon | B bomb',18)
            text(40,960,'C free look | P pause | F12 capture',18)
            text(520,1010,'FlightGear  /  Wicked Engine  /  Powered by Poly Haven  /  ambientCG',19,MUTED)
            return texts,lines
        speed=math.sqrt(sum(v*v for v in p.velocity)) if p else 0
        text(40,30,'BVR / '+frame.mission.upper(),22)
        text(40,77,f'THR   {(p.throttle if p else self.throttle)*100:3.0f} %',22)
        text(40,108,f'SPD   {speed*3.6:4.0f} km/h',22)
        text(40,139,f'ALT   {p.position[2] if p else 0:5.0f} m',22)
        text(40,170,f'MACH  {p.mach if p else 0:.2f}',22)
        text(40,213,f'AAM   {frame.missiles_left}   AIM-120C7',20)
        text(40,244,f'BOMB  {frame.bombs_left}   Mk-82',20)
        text(40,285,'SELECTED  '+self.weapon,18,GREEN)
        text(40,320,'P / PAUSE' if not frame.paused else 'PAUSED  |  P resume, . step',18,GREEN)
        text(40,1018,f'{self.fps:.0f} FPS   {frame.sim_time:6.1f}s',18,MUTED)
        line(610,35,350,4,BLUE);line(960,35,350,4,RED)
        text(610,57,'BLUE: PLAYER',18,BLUE);text(1110,57,'RED: HOSTILE',18,RED)
        # Aim mark is input intent. Aircraft flight-path marker uses measured velocity.
        ax,ay=self.aim[0]/sx,self.aim[1]/sy
        box(ax-10,ay-10,20,20);line(ax-20,ay,8);line(ax+12,ay,8)
        if p:
            dot=self.renderer.project([p.position[i]+p.velocity[i]*2 for i in range(3)])
            if 0<dot[2]<1:box(dot[0]/sx-5,dot[1]/sy-5,10,10,WHITE)
        for c in frame.contacts:
            v=self.renderer.project(c.position)
            if 0<v[2]<1:
                x,y=min(max(v[0]/sx,450),1490),min(max(v[1]/sy,200),760);color=GREEN if c.locked else RED
                box(x-22,y-22,44,44,color)
                distance=math.dist(p.position,c.position)/1000
                caption=c.uid+'  '+f'{distance:.1f} km'+(' / STT LOCK' if c.locked else '')
                lx,ly=labels.place(x+28,y-18,caption);text(lx,ly,caption,18,color)
        # Radar is fed only by measured contacts, never all render entities.
        panel(1550,250,320,320);box(1550,250,320,320)
        for v in range(1,4):line(1550,250+80*v,320,1,0x6663b17b)
        line(1710,250,1,320,0x6663b17b)
        text(1555,220,frame.radar_mode+f'   {frame.radar_range/1000:.0f} km',18,GREEN)
        text(1550,582,'R lock   SPACE fire',17,GREEN)
        if p:
            yaw=p.orientation[2]
            for c in frame.contacts:
                dx=c.position[0]-p.position[0];dy=c.position[1]-p.position[1]
                bearing=math.remainder(math.atan2(dy,dx)-yaw,2*math.pi);dist=math.hypot(dx,dy)
                rx=1710-bearing/(math.pi/3)*160;ry=570-min(dist/frame.radar_range,1)*320
                if 1550<rx<1870:box(rx-4,ry-4,8,8,GREEN if c.locked else RED)
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
        for i,e in enumerate(recent[-4:]):text(650,840+i*28,e.message,22,GREEN if 'hit' in e.kind or 'destroyed' in e.kind else WHITE)
        panel(580,980,760,60)
        text(600,995,'V weapon   R lock   SPACE launch   B release   ESC hangar',18)
        if self.mode=='result':
            panel(600,310,720,410);text(665,355,'MISSION '+frame.result.upper(),38,GREEN if frame.result=='succeeded' else RED)
            text(665,440,f'AIR KILLS {frame.air_kills}    GROUND KILLS {frame.ground_kills}',24)
            text(665,495,f'FLIGHT TIME {frame.sim_time:.1f} s',22)
            text(665,575,'ENTER / FLY AGAIN',26);text(665,635,'ESC / RETURN TO HANGAR',20)
        self.hud_layout=labels.placed
        return texts,lines

    def draw(self,dt=1/60,*,free=False):
        if not self.renderer:return
        if hasattr(self.renderer,'presentation'):self.renderer.presentation(self.mode=='hangar')
        self.follow_camera(dt,free=free)
        texts,lines=self.hud() if self.show_hud else ([],[])
        if not self.show_hud:self.hud_layout=[]
        start=time.perf_counter();self.renderer.render(self.sim.frame(),texts,lines)
        self.frame_times.append(time.perf_counter()-start)
        if not self.interactive:self.fps=1/max(statistics.median(self.frame_times[-60:]),1e-6)

    def input(self,event,dt):
        held=set(event.held);pressed=set(event.pressed)
        if event.quit:return False
        self.aim=safe_aim(event.x,event.y,self.width,self.height)
        if 123 in pressed:self.capture('manual') # F12
        if 81 in pressed:
            self.quality=['low','medium','high'][(['low','medium','high'].index(self.quality)+1)%3];self.renderer.set_quality(self.quality)
        if self.mode=='hangar':
            changed=False
            if 49 in pressed:self.config.player_model='F22';changed=True
            if 50 in pressed:self.config.player_model='F16';changed=True
            if 77 in pressed:self.config.mission=['air','strike','combined'][(['air','strike','combined'].index(self.config.mission)+1)%3]
            if 76 in pressed:
                self.config.missiles,self.config.bombs={(4,2):(6,0),(6,0):(0,4),(0,4):(4,2)}.get((self.config.missiles,self.config.bombs),(4,2))
            if 71 in pressed:self.config.enemy_attacks=not self.config.enemy_attacks
            if changed:
                self.sim.reset(self.config);self.sim.set_paused(True)
                if self.renderer:self.renderer.reload()
            click=1 in pressed and 40/1920*self.width<=event.x<=430/1920*self.width and 760/1080*self.height<=event.y<=830/1080*self.height
            if 13 in pressed or click:self.start()
            if 27 in pressed:return False
            return True
        if 27 in pressed:self.mode='hangar';self.sim.set_paused(True);return True
        if self.mode=='result':
            if 13 in pressed:self.start()
            return True
        frame=self.sim.frame()
        if 80 in pressed:self.sim.set_paused(not frame.paused)
        if 190 in pressed:self.sim.step_exact()
        if 86 in pressed:self.weapon='Mk-82' if self.weapon=='AIM-120C7' else 'AIM-120C7'
        self.throttle=max(0,min(1,self.throttle+dt*(int(87 in held)-int(83 in held))*.3))
        self.zoom=2 in held
        if 67 in held:return True
        p=self.player(frame)
        if not p:return True
        dx=(self.aim[0]/self.width-.5)*2;dy=(self.aim[1]/self.height-.5)*2
        c=native.PilotCommand();c.heading=p.orientation[2]-curve(dx);c.pitch=-curve(dy,limit=.35);c.throttle=self.throttle
        c.manual_roll=65 in held or 68 in held;c.roll_input=int(68 in held)-int(65 in held)
        if 82 in pressed or 9 in pressed:
            candidates=[x.uid for x in frame.contacts]
            if candidates:
                self.target=candidates[(candidates.index(self.target)+1)%len(candidates)] if self.target in candidates else candidates[0]
                c.lock=True;c.target_uid=self.target
        c.fire=(32 in pressed or 1 in pressed) and self.weapon=='AIM-120C7';c.target_uid=self.target;c.weapon='AIM-120C7'
        c.drop_bomb=66 in pressed or (32 in pressed and self.weapon=='Mk-82')
        self.sim.submit(c);return True

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
    p.add_argument('--render',action='store_true');p.add_argument('--hidden',action='store_true');p.add_argument('--mission',choices=['air','strike','combined'],default='air');p.add_argument('--aircraft',choices=['F22','F16'],default='F22');p.add_argument('--seed',type=int,default=7)
    p.add_argument('--width',type=int,default=1920);p.add_argument('--height',type=int,default=1080);p.add_argument('--quality',choices=['low','medium','high'],default='high');p.add_argument('--frames',type=int,default=300);p.add_argument('--output',type=Path,default=GAME/'captures');p.add_argument('--runtime',type=Path,default=GAME/'runtime.json');p.add_argument('--map',type=Path,default=GAME/'maps/training_range_v2/generated-map.json')
    a=p.parse_args();game=FlightGame(render=a.render or a.command=='play' or a.command=='benchmark',visible=not a.hidden,width=a.width,height=a.height,runtime=a.runtime,map_path=a.map,output=a.output)
    game.config.player_model=a.aircraft;game.config.mission=a.mission;game.config.seed=a.seed;game.quality=a.quality
    if game.renderer:game.renderer.set_quality(a.quality)
    try:
        if a.command=='run':acceptance(game,a.mission)
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
                now=time.perf_counter();dt=min(now-last,.1);last=now;game.fps=.9*game.fps+.1/max(dt,.0001)
                event=game.renderer.poll()
                if not game.input(event,dt):break
                if game.mode=='flight':
                    accumulator+=dt
                    ticks=min(int(accumulator/game.config.dt),5)
                    if ticks:game.step(ticks);accumulator-=ticks*game.config.dt
                else:accumulator=0
                game.draw(dt,free=67 in event.held)
    finally:game.close()

if __name__=='__main__':main()
