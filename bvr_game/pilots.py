"""Repeatable Agent pilots using observations and normal PilotCommand only."""
import math

class CombatPilot:
    def __init__(self,force_early_support_break=False):
        self.last_fire=-100.;self.last_warning=-100.;self.position=None;self.velocity=None;self.observed_at=0.
        self.force_early_support_break=force_early_support_break;self.miss_seen=False
    def command(self,frame,player):
        command={'throttle':1.,'heading':player.orientation[2],'pitch':0.}
        self.miss_seen=any(e.kind=='missile_missed' and e.actor=='player' for e in frame.events)
        if frame.contacts:
            contact=next((c for c in frame.contacts if c.uid==frame.selected_target),frame.contacts[0])
            self.position=contact.position;self.velocity=contact.velocity;self.observed_at=frame.sim_time
            if not frame.selected_target:command.update(lock=True,target_uid=contact.uid)
        if self.position is None:return command
        estimate=[a+b*(frame.sim_time-self.observed_at) for a,b in zip(self.position,self.velocity)]
        bearing=math.atan2(estimate[1]-player.position[1],estimate[0]-player.position[0])
        airborne=any(m.owner=='player' for m in frame.missiles)
        if frame.missile_warning:self.last_warning=frame.sim_time
        offset=math.radians(25) if airborne else 0
        if frame.sim_time-self.last_warning<8:offset=math.radians(110)
        if self.force_early_support_break and not self.miss_seen and airborne:offset=math.radians(150)
        command['heading']=bearing+offset
        command['pitch']=-.12 if offset>1.5 and player.position[2]>2000 else 0.
        if frame.envelope.in_range and frame.envelope.target_uid and frame.sim_time-self.last_fire>8 and not airborne:
            command.update(fire=True,target_uid=frame.selected_target);self.last_fire=frame.sim_time
        return command

class StrikePilot:
    def __init__(self,target):self.target=target;self.released=False
    def command(self,frame,player):
        command={'throttle':.85,'pitch':0.,'heading':player.orientation[2]}
        if not self.released:
            command['heading']=math.atan2(self.target[1]-player.position[1],self.target[0]-player.position[0])
            if frame.bomb_impact and math.dist(frame.bomb_impact,self.target)<25:
                command['drop_bomb']=True;self.released=True
        return command
