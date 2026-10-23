"""Pure presentation math, available to headless Agent layout/camera checks."""
import math

def curve(value,deadzone=.035,limit=.55):
    magnitude=max(0,(abs(value)-deadzone)/(1-deadzone))
    return math.copysign(min(magnitude,1)**1.7*limit,value)

def safe_aim(x,y,width,height):
    return (min(max(x,420/1920*width),1500/1920*width),
            min(max(y,230/1080*height),780/1080*height))

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
    def __init__(self):self.eye=None;self.target=None;self.yaw=None;self.fov=1.0;self.free=[0.,0.];self.roll=0.;self.last_position=None
    def reset(self):self.__init__()
    def update(self,entity,dt,free,aim,width,height,zoom):
        dt=min(max(dt,.001),.1);alpha=1-math.exp(-dt*7)
        yaw=math.atan2(entity.velocity[1],entity.velocity[0])
        if self.yaw is None:self.yaw=yaw
        self.yaw+=math.remainder(yaw-self.yaw,2*math.pi)*alpha
        desired=[(aim[0]/width-.5)*4.5,(aim[1]/height-.5)*1.1] if free else [0,0]
        self.free=[a+(b-a)*alpha for a,b in zip(self.free,desired)]
        self.roll+=(max(-.25,min(.25,entity.orientation[0]*.18))-self.roll)*alpha
        self.fov+=((.72 if zoom else 1.0)-self.fov)*(1-math.exp(-dt*9))
        yaw=self.yaw+self.free[0];pitch=math.atan2(entity.velocity[2],math.hypot(*entity.velocity[:2]))
        north,west,alt=entity.position;distance=33 if not zoom else 28
        forward=(-math.sin(yaw),math.cos(yaw));lift=8+math.sin(self.free[1])*distance
        eye=[-west-forward[0]*distance,alt+lift-math.sin(pitch)*distance*.4,north-forward[1]*distance]
        target=[-west+forward[0]*24,alt+2+math.sin(pitch)*12,north+forward[1]*24]
        current=[-west,alt,north]
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
        return self.eye,self.target,self.fov,[math.sin(self.roll),math.cos(self.roll),0]
