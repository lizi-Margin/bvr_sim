"""Pure presentation math, available to headless Agent layout/camera checks."""
import math

def curve(value,deadzone=.035,limit=.55):
    magnitude=max(0,(abs(value)-deadzone)/(1-deadzone))
    return math.copysign(min(magnitude,1)**1.7*limit,value)

def safe_aim(x,y,width,height):
    return (min(max(x,420/1920*width),1500/1920*width),
            min(max(y,230/1080*height),780/1080*height))

def mouse_pitch(y,height):
    # Normalize to the actual asymmetric aiming rectangle, not the full window.
    center=height*.5
    extent=height*((540-230) if y<center else (780-540))/1080
    return -curve((y-center)/extent,limit=math.pi/4)

def mouse_roll_rate(x,width):
    """YASim rate assist: reachable left/right aim edges give +/-60 deg/s."""
    dx=(x/width-.5)*2
    edge=(1500/1920-.5)*2
    return max(-1.,min(1.,curve(dx)/curve(edge)))*math.pi/3

def overlap(a,b):
    return a[0]<b[2] and a[2]>b[0] and a[1]<b[3] and a[3]>b[1]

class Labels:
    def __init__(self):
        self.rectangles=[(0,0,410,360),(600,0,1320,110),(1530,200,1900,650),(570,820,1370,1080)]
        self.placed=[]
    def place(self,x,y,text,size=18):
        width=min(490,max(60,len(text)*size*.58));height=size+9
        for dy in [0,-36,36,-72,72,-110,110,-160,160]:
            px=min(max(x,25),1895-width);py=min(max(y+dy,120),800-height)
            box=(px,py,px+width,py+height)
            if not any(overlap(box,r) for r in self.rectangles):
                self.rectangles.append(box);self.placed.append({'text':text,'bounds':box});return px,py
        # A dedicated left column is reserved for overflow labels.
        px,py=425,380+len(self.placed)*35;box=(px,py,px+width,py+height)
        self.rectangles.append(box);self.placed.append({'text':text,'bounds':box});return px,py

class ChaseCamera:
    def __init__(self,settings=None):
        if settings is None:
            from .player_profiles import PlayerProfileStore
            settings=PlayerProfileStore().resolve('F22')['camera']
        self.settings=dict(settings)
        self.framing_state={}
        self.eye=None;self.target=None;self.yaw=None;self.fov=self.settings['normal_fov'];self.free=[0.,0.];self.roll=0.;self.last_position=None
    def reset(self):self.__init__(self.settings)
    def update(self,entity,dt,free,aim,width,height,zoom):
        cfg=self.settings;dt=min(max(dt,0),.1);alpha=1-math.exp(-dt*cfg['smoothing_hz'])
        yaw=math.atan2(entity.velocity[1],entity.velocity[0]) if math.hypot(*entity.velocity[:2])>.1 else entity.orientation[2]
        if self.yaw is None:self.yaw=yaw
        self.yaw+=math.remainder(yaw-self.yaw,2*math.pi)*alpha
        desired=[-(aim[0]/width-.5)*2*cfg['free_yaw_range'],(aim[1]/height-.5)*2*cfg['free_pitch_range']] if free else [0,0]
        self.free=[a+(b-a)*alpha for a,b in zip(self.free,desired)]
        self.roll+=(max(-cfg['roll_limit_rad'],min(cfg['roll_limit_rad'],entity.orientation[0]*cfg['roll_feedback']))-self.roll)*alpha
        self.fov+=((cfg['zoom_fov'] if zoom else cfg['normal_fov'])-self.fov)*alpha
        yaw=self.yaw+self.free[0];pitch=math.atan2(entity.velocity[2],math.hypot(*entity.velocity[:2]))-self.free[1]
        scale=getattr(self,'scale',1.)
        north,west,alt=entity.position;distance=cfg['distance_spans']*19*scale
        forward=[-math.sin(yaw)*math.cos(pitch),math.sin(pitch),math.cos(yaw)*math.cos(pitch)]
        position=[-west,alt,north];lift=cfg['lift_spans']*19*scale
        if 'subject_y' in cfg:
            # Source model origins need not coincide with their visible centre
            # (the imported A-10 extends almost entirely behind its origin).
            # Follow that measured visual offset without moving the aircraft.
            x,y,z=getattr(self,'subject_offset_blender',(0,0,0));roll,pitch_body,yaw_body=entity.orientation
            c,s=math.cos(yaw_body),math.sin(yaw_body);cp,sp=math.cos(pitch_body),math.sin(pitch_body)
            f=[c*cp,s*cp,-sp];right_body=[s,-c,0];up_body=[c*sp,s*sp,cp]
            r=[right_body[i]*math.cos(roll)-up_body[i]*math.sin(roll) for i in range(3)]
            u=[up_body[i]*math.cos(roll)+right_body[i]*math.sin(roll) for i in range(3)]
            offset=[x*r[i]+y*f[i]+z*u[i] for i in range(3)]
            position=[position[0]-offset[1],position[1]+offset[2],position[2]+offset[0]]
        eye=[position[i]-forward[i]*distance+(lift if i==1 else 0) for i in range(3)]
        target=[position[i]+forward[i]*cfg['lookahead_m'] for i in range(3)]
        current=position
        if self.eye is None:self.eye=eye;self.target=target
        elif self.last_position is not None:
            # Smooth the relative chase offset; carry measured translation
            # immediately so high airspeed or exact stepping cannot leave the
            # aircraft hundreds of metres ahead of a lagging world-space camera.
            delta=[a-b for a,b in zip(current,self.last_position)]
            self.eye=[a+b for a,b in zip(self.eye,delta)];self.target=[a+b for a,b in zip(self.target,delta)]
        self.last_position=current
        self.eye=[a+(b-a)*alpha for a,b in zip(self.eye,eye)]
        self.target=[a+(b-a)*alpha for a,b in zip(self.target,target)]
        right=[math.cos(yaw),0,math.sin(yaw)]
        up=[right[i]*math.sin(self.roll)+(math.cos(self.roll) if i==1 else 0) for i in range(3)]
        if 'subject_y' not in cfg:
            # Frozen legacy profiles retain their original camera/replay path.
            self.framing_state={}
            return self.eye,self.target,self.fov,up
        from .player_input import dot,cross,unit
        zoom_scale=(math.tan(cfg['normal_fov']/2)/math.tan(self.fov/2))**cfg.get('zoom_dolly',0)
        offset=unit([a-b for a,b in zip(self.eye,position)],unit([a-b for a,b in zip(eye,position)]))
        # Interpolate orbital direction, retaining the declared camera radius.
        # Apply dolly compensation after smoothing so FOV and subject size do
        # not temporarily disagree during the zoom transition.
        radius=math.dist(eye,position);render_eye=[position[i]+offset[i]*radius*zoom_scale for i in range(3)]
        forward=unit([b-a for a,b in zip(self.eye,self.target)],forward)
        r=unit(cross(up,forward),right);u=unit(cross(forward,r))
        subject=[a-b for a,b in zip(position,render_eye)];y=dot(subject,u);z=dot(subject,forward)
        tangent=(2*cfg['subject_y']-1)*math.tan(self.fov/2)
        angle=math.atan2(y+tangent*z,z-tangent*y)
        framed=[forward[i]*math.cos(angle)+u[i]*math.sin(angle) for i in range(3)]
        framed_up=[u[i]*math.cos(angle)-forward[i]*math.sin(angle) for i in range(3)]
        render_target=[render_eye[i]+framed[i]*(distance+cfg['lookahead_m']) for i in range(3)]
        self.framing_state={'subject_y':cfg['subject_y'],'subject_position_wicked':position,'zoom_scale':zoom_scale,'distance_m':math.dist(render_eye,position),'pitch_reframe_rad':angle}
        return render_eye,render_target,self.fov,framed_up
