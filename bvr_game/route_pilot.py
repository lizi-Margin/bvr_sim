"""Public scenic route and copied local observations only; no world entity access."""
import math

class ScenicRoutePilot:
    def __init__(self,waypoints,minimum_seconds=180,speed=180):
        self.waypoints=[list(p) for p in waypoints];self.minimum_seconds=minimum_seconds;self.speed=speed
        self.index=0;self.phase='airfield';self.arrivals=[];self.throttle_integral=0.
        self.first_contact=None;self.approach_started=None;self.approach_initial_range=None;self.latest_range=None
    def intent(self,o):
        own=o.own;p=own['position'];v=own['velocity'];speed=math.sqrt(sum(x*x for x in v))
        self.throttle_integral=max(-.35,min(.35,self.throttle_integral+(self.speed-speed)*.0005*.5))
        throttle=max(.12,min(.95,.5+(self.speed-speed)*.008+self.throttle_integral))
        result={'throttle':throttle,'mode':'assisted'}
        if self.index<len(self.waypoints):
            target=self.waypoints[self.index];distance=math.hypot(target[0]-p[0],target[1]-p[1])
            if distance<1100 and abs(target[2]-p[2])<250:
                self.arrivals.append({'index':self.index,'time':o.time,'position':list(p),'distance_m':distance,'height_error_m':p[2]-target[2]})
                self.index+=1
            if self.index<len(self.waypoints):
                target=self.waypoints[self.index];dn,dw=target[0]-p[0],target[1]-p[1]
                az=math.atan2(dw,dn);el=math.atan2(target[2]-p[2],max(500,math.hypot(dn,dw)))
                self.phase=['airfield','airfield_exit','river_low','river_bend','town_turn','climb','regional_climb'][self.index]
            else:az=math.atan2(v[1],v[0]);el=0;self.phase='public_loiter'
        else:
            # A public orbit after the scenic waypoints; its centre is map
            # navigation data, not an enemy coordinate or hidden observation.
            dn,dw=p[0]-3500,p[1]+1000;radius=math.hypot(dn,dw);bearing=math.atan2(dw,dn)
            az=bearing+math.pi/2+math.atan2(radius-3500,3500)
            el=math.atan2(1000-p[2],max(1500,speed*8));self.phase='public_loiter'
        if o.contacts and self.first_contact is None:
            self.first_contact={'time':o.time,'tracks':[dict(c) for c in o.contacts]}
        if self.index>=len(self.waypoints) and o.time>=self.minimum_seconds and o.contacts:
            track=min(o.contacts,key=lambda c:math.dist(c['position'],p));dn,dw,dh=[a-b for a,b in zip(track['position'],p)]
            distance=math.sqrt(dn*dn+dw*dw+dh*dh)
            if self.approach_started is None:self.approach_started=o.time;self.approach_initial_range=distance
            self.latest_range=distance;self.phase='observed_contact_approach'
            az=math.atan2(dw,dn);el=math.atan2(dh,max(1500,math.hypot(dn,dw)))
            result.update(lock=True,target_uid=track['uid'])
        # This is the route pilot's ordinary navigation policy, not a limit on
        # the core's full-angle direction interface. Envelope tests are separate.
        el=max(-math.radians(10),min(math.radians(10),el))
        if own['agl']<180:el=max(el,math.radians(10))
        result['direction']=[math.cos(el)*math.cos(az),math.cos(el)*math.sin(az),math.sin(el)]
        return result
    def complete(self,time):
        return self.approach_started is not None and time-self.approach_started>=15 and self.latest_range<self.approach_initial_range-1000
