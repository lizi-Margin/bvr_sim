"""Client input/projection only; actual assistance runs in the native core."""
import math

def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def unit(a,fallback=(1,0,0)):
    length=math.sqrt(dot(a,a));return [x/length for x in a] if length>1e-10 else list(fallback)
def body_forward(rpy):
    _,pitch,yaw=rpy;return [math.cos(yaw)*math.cos(pitch),math.sin(yaw)*math.cos(pitch),-math.sin(pitch)]
def shaped(value,deadzone,exponent):
    return math.copysign(max(0.,(abs(value)-deadzone)/(1-deadzone))**exponent,value)
def camera_ray(x,y,width,height,camera):
    """Actual vertical-FOV/aspect projection, renderer (-W,U,N) -> world NWU."""
    f=unit([b-a for a,b in zip(camera['eye'],camera['target'])],(0,0,1))
    r=unit(cross(camera.get('up',[0,1,0]),f),(1,0,0));u=unit(cross(f,r),(0,1,0))
    tangent=math.tan(camera['fov']/2);nx=(2*x/width-1)*width/height*tangent;ny=(1-2*y/height)*tangent
    v=unit([f[i]+r[i]*nx+u[i]*ny for i in range(3)])
    return [v[2],-v[0],v[1]]

def rotated(vector,axis,angle):
    axis=unit(axis);c,s=math.cos(angle),math.sin(angle);side=cross(axis,vector);along=dot(axis,vector)*(1-c)
    return unit([vector[i]*c+side[i]*s+axis[i]*along for i in range(3)])

def aim_marker(direction,camera,projected,width,height):
    """Logical HUD point plus truthful edge/behind status for the world intent."""
    f=unit([b-a for a,b in zip(camera['eye'],camera['target'])],(0,0,1))
    r=unit(cross(camera.get('up',[0,1,0]),f),(1,0,0));u=unit(cross(f,r),(0,1,0))
    d=[-direction[1],direction[2],direction[0]];behind=dot(d,f)<=0
    x,y=projected[0]*1920/width,projected[1]*1080/height
    if not behind and 0<projected[2]<1 and 450<=x<=1480 and 180<=y<=810:
        return {'point':[x,y],'edge':False,'behind':False,'bearing':0.}
    tangent=math.tan(camera['fov']/2)
    dx=dot(d,r)/(tangent*width/height)*960;dy=-dot(d,u)/tangent*540
    if math.hypot(dx,dy)<1e-6:dx=1. # Exactly aft has no unique turn direction.
    limits=[(1480-960)/dx if dx>0 else (450-960)/dx] if dx else []
    if dy:limits.append((810-540)/dy if dy>0 else (180-540)/dy)
    scale=min(limits)
    return {'point':[960+dx*scale,540+dy*scale],'edge':True,'behind':behind,'bearing':math.atan2(dy,dx)}

class PlayerInputAdapter:
    def __init__(self,profile,direction=(1,0,0)):
        self.profile=profile;self.mode='assisted';self.last_projection={};self.reset(direction)
    def reset(self,direction):
        self.direction=unit(direction);self.raw_direction=list(self.direction)
        self.last_pointer=None;self.last_viewport=None;self.edge_armed=True
        self.edge_yaw_rate=0.;self.edge_pitch_rate=0.;self.rebase_pointer=False
    def adopt_direction(self,direction):
        """Hand an external world intent to the pointer without stale filtering."""
        self.direction=unit(direction);self.raw_direction=list(self.direction)
        self.edge_armed=False;self.edge_yaw_rate=self.edge_pitch_rate=0.
        self.rebase_pointer=True
    def throttle(self,current,event,dt):
        pad=getattr(event,'pad_axes',()) if getattr(event,'pad_connected',False) else ()
        if len(pad)>=6:current+=(pad[5]-pad[4])*max(0,min(dt,.1))*self.profile['input']['throttle_rate']
        return min(max(current,0),1)
    def update(self,event,dt,own,camera,width,height,*,hold_direction=False):
        p=self.profile['input'];dt=min(max(float(dt),0),.1);held=set(event.held)
        x=min(max(float(event.x),0),width);y=min(max(float(event.y),0),height)
        manual_pitch=87 in held or 83 in held;manual_roll=65 in held or 68 in held
        pitch=int(83 in held)-int(87 in held);roll=int(68 in held)-int(65 in held)
        yaw=int(69 in held)-int(90 in held) # E right / Z left, raw yaw takeover.
        pad=getattr(event,'pad_axes',()) if getattr(event,'pad_connected',False) else ()
        pad_aim=len(pad)>=4 and max(abs(pad[2]),abs(pad[3]))>p['deadzone']
        nx=2*x/width-1;ny=1-2*y/height
        if self.rebase_pointer:
            self.last_pointer=(nx,ny);self.last_viewport=[width,height];self.rebase_pointer=False
        def projected(pointer):
            sx=shaped(pointer[0],p['deadzone'],p['curve'])*p['sensitivity'];sy=shaped(pointer[1],p['deadzone'],p['curve'])*p['sensitivity']
            return camera_ray((sx+1)*width/2,(1-sy)*height/2,width,height,camera)
        ray=projected((nx,ny));active=getattr(event,'active',True)
        if hold_direction or pad_aim or not active:
            # Rebase during observation/focus changes. Pointer motion used for
            # looking must not become a flight command when control resumes.
            self.raw_direction=list(self.direction);self.edge_armed=False
            self.edge_yaw_rate=self.edge_pitch_rate=0.
        else:
            moved=False
            if self.last_pointer is None:self.raw_direction=ray
            elif self.last_viewport==[width,height]:
                previous_ray=projected(self.last_pointer)
                axis=cross(previous_ray,ray);length=math.sqrt(dot(axis,axis))
                moved=max(abs(nx-self.last_pointer[0]),abs(ny-self.last_pointer[1]))>1e-12
                if moved:self.edge_armed=True
                if length>1e-12:
                    # Transport only the measured pointer displacement, using
                    # this frame's actual camera/FOV for both rays. Camera
                    # translation, roll, zoom and chase return cannot steer.
                    self.raw_direction=rotated(self.raw_direction,axis,math.atan2(length,dot(previous_ray,ray)))
            def edge(v):return math.copysign(max(0,(abs(v)-p['edge_fraction'])/(1-p['edge_fraction'])),v)
            ex,ey=(edge(nx),edge(ny)) if self.edge_armed else (0,0)
            response=1-math.exp(-dt/p['edge_recenter_seconds'])
            self.edge_yaw_rate+=(-ex*p['edge_pan_rate']-self.edge_yaw_rate)*response
            self.edge_pitch_rate+=(ey*p['edge_pan_rate']-self.edge_pitch_rate)*response
            view=unit([b-a for a,b in zip(camera['eye'],camera['target'])],(0,0,1))
            camera_right=unit(cross(camera.get('up',[0,1,0]),view),(1,0,0))
            camera_right=[camera_right[2],-camera_right[0],camera_right[1]]
            candidate=rotated(self.raw_direction,[0,0,1],self.edge_yaw_rate*dt)
            candidate=rotated(candidate,camera_right,self.edge_pitch_rate*dt)
            forward=[view[2],-view[0],view[1]]
            separation=lambda d:math.acos(max(-1,min(1,dot(d,forward))))
            # Bound edge-pan lead relative to the view, not total world turn.
            # As the aircraft/camera follow, edge input can keep turning through
            # any heading without a permanent near-nose angular ceiling.
            if separation(candidate)<=p['max_edge_pan'] or separation(candidate)<separation(self.raw_direction):self.raw_direction=candidate
            if moved or self.edge_yaw_rate or self.edge_pitch_rate:
                az=math.atan2(self.raw_direction[1],self.raw_direction[0])
                el=max(-p['max_target_elevation'],min(p['max_target_elevation'],math.asin(max(-1,min(1,self.raw_direction[2])))))
                self.raw_direction=[math.cos(el)*math.cos(az),math.cos(el)*math.sin(az),math.sin(el)]
            # Core does spherical target filtering; this client filter only
            # removes pointer quantization and never rotates the aircraft.
            alpha=1-math.exp(-dt/p['direction_response'])
            if dot(self.direction,self.raw_direction)<-.95:self.direction=list(self.raw_direction)
            else:self.direction=unit([a+(b-a)*alpha for a,b in zip(self.direction,self.raw_direction)])
        self.last_pointer=(nx,ny);self.last_viewport=[width,height]
        self.last_projection={'pointer':[x,y],'viewport':[width,height],'camera':camera,'projected_ray':ray,
            'direction_source':'world-anchored pointer displacement and explicit edge pan','hold_direction':hold_direction,
            'edge_yaw_rate_rad_s':self.edge_yaw_rate,'edge_pitch_rate_rad_s':self.edge_pitch_rate,'edge_lead_limit_rad':p['max_edge_pan']}
        if len(pad)>=4:
            if abs(pad[0])>p['deadzone']:manual_roll=True;roll=shaped(pad[0],p['deadzone'],p['curve'])
            if abs(pad[1])>p['deadzone']:manual_pitch=True;pitch=-shaped(pad[1],p['deadzone'],p['curve'])
            if not hold_direction and max(abs(pad[2]),abs(pad[3]))>p['deadzone']:
                az=math.atan2(self.direction[1],self.direction[0])-pad[2]*p['edge_pan_rate']*dt
                el=max(-p['max_target_elevation'],min(p['max_target_elevation'],math.asin(self.direction[2])+pad[3]*p['edge_pan_rate']*dt))
                self.direction=[math.cos(el)*math.cos(az),math.cos(el)*math.sin(az),math.sin(el)]
                self.raw_direction=list(self.direction)
        return {'direction':list(self.direction),'pitch_input':float(pitch),'roll_input':float(roll),'yaw_input':float(yaw),
                'manual_pitch':manual_pitch,'manual_roll':manual_roll,'manual_yaw':bool(yaw),'mode':self.mode,'protection':True}

def native_intent(native,values):
    out=native.PlayerFlightIntent()
    for key,value in values.items():
        if key=='mode':
            if value not in ('raw_manual','RawManual','assisted','Assisted'):raise ValueError('Unknown player control mode: '+str(value))
            value=native.PlayerFlightMode.RawManual if value in ('raw_manual','RawManual') else native.PlayerFlightMode.Assisted
        setattr(out,key,value)
    return out
