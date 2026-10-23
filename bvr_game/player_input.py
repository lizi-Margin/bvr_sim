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

class PlayerInputAdapter:
    def __init__(self,profile,direction=(1,0,0)):
        self.profile=profile;self.direction=unit(direction);self.edge_yaw=0.;self.edge_pitch=0.
        self.mode='assisted';self.last_projection={}
    def reset(self,direction):self.direction=unit(direction);self.edge_yaw=self.edge_pitch=0.
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
        if not hold_direction and not pad_aim and getattr(event,'active',True):
            nx=2*x/width-1;ny=1-2*y/height
            sx=shaped(nx,p['deadzone'],p['curve'])*p['sensitivity'];sy=shaped(ny,p['deadzone'],p['curve'])*p['sensitivity']
            ray=camera_ray((sx+1)*width/2,(1-sy)*height/2,width,height,camera)
            def edge(v):return math.copysign(max(0,(abs(v)-p['edge_fraction'])/(1-p['edge_fraction'])),v)
            ex,ey=edge(nx),edge(ny)
            limit=p['max_edge_pan'];decay=math.exp(-dt/p['edge_recenter_seconds'])
            self.edge_yaw=max(-limit,min(limit,self.edge_yaw-ex*p['edge_pan_rate']*dt)) if ex else self.edge_yaw*decay
            self.edge_pitch=max(-limit,min(limit,self.edge_pitch+ey*p['edge_pan_rate']*dt)) if ey else self.edge_pitch*decay
            az=math.atan2(ray[1],ray[0])+self.edge_yaw
            el=max(-p['max_target_elevation'],min(p['max_target_elevation'],math.atan2(ray[2],math.hypot(*ray[:2]))+self.edge_pitch))
            desired=[math.cos(el)*math.cos(az),math.cos(el)*math.sin(az),math.sin(el)]
            # Core does spherical target filtering; this client filter only
            # removes pointer quantization and never rotates the aircraft.
            alpha=1-math.exp(-dt/p['direction_response'])
            if dot(self.direction,desired)<-.95:self.direction=desired
            else:self.direction=unit([a+(b-a)*alpha for a,b in zip(self.direction,desired)])
            self.last_projection={'pointer':[x,y],'viewport':[width,height],'camera':camera,'projected_ray':ray,'edge_yaw':self.edge_yaw,'edge_pitch':self.edge_pitch}
        if len(pad)>=4:
            if abs(pad[0])>p['deadzone']:manual_roll=True;roll=shaped(pad[0],p['deadzone'],p['curve'])
            if abs(pad[1])>p['deadzone']:manual_pitch=True;pitch=-shaped(pad[1],p['deadzone'],p['curve'])
            if not hold_direction and max(abs(pad[2]),abs(pad[3]))>p['deadzone']:
                az=math.atan2(self.direction[1],self.direction[0])-pad[2]*p['edge_pan_rate']*dt
                el=max(-p['max_target_elevation'],min(p['max_target_elevation'],math.asin(self.direction[2])+pad[3]*p['edge_pan_rate']*dt))
                self.direction=[math.cos(el)*math.cos(az),math.cos(el)*math.sin(az),math.sin(el)]
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
