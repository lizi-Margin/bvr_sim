# shc 2023
import math
import numpy as np

import uhtk.c3utils.i3utils as utils 
from uhtk.c3utils.i3utils import norm, Vector3, feet_to_meters

class SimpleScalarFilter:
    def __init__(self, alpha: float, initial_value: float = 0.0):
        self.alpha = alpha
        self.init_value = initial_value
        self.value = initial_value
    
    def reset(self) -> None:
        self.value = self.init_value

    def update(self, x: float) -> float:
        self.value = self.alpha * x + (1 - self.alpha) * self.value
        return self.value

class CrashingCounter:
    def __init__(self, dt: float, max_time: float = 1.0):
        self.dt = dt
        self.max_time = max_time
        self.timer = max_time
    
    def update(self, crashing: bool) -> int:
        if crashing:
            self.timer = 0.
        else:
            self.timer += self.dt
        return self.timer < self.max_time

class StdFlightController:
    def __init__(self, dt) :
        self.kroll_p = 1.2
        self.kroll_i = 0.2
        self.kroll_d = -0.

        self.kpitch_p = -3.4
        self.kpitch_i = -0.0
        # self.kpitch_d = 0 #0.5
        self.kpitch_d = -0.5

        self.kthrottle_p = 0.03
        self.kthrottle_i = 0.06
        self.kthrottle_d = 500
        self.dt = dt

        self.sum_err_roll =0
        self.last_err_roll =0
        self.sum_err_pitch =0
        self.last_err_pitch =0
        self.sum_err_throttle =0 
        self.last_err_throttle = 0

        self.right_turn = 0

        # self.error_pitch_filter = SimpleScalarFilter(alpha=0.05)

        # # dt is not considered !!!!
        # self.filters = [
        #     SimpleScalarFilter(alpha=0.20),
        #     SimpleScalarFilter(alpha=0.10),
        #     SimpleScalarFilter(alpha=0.10),
        #     SimpleScalarFilter(alpha=0.10),
        # ]
        self.crashing_counter = CrashingCounter(dt, max_time=5.)
    
    

    def reset(self) -> None:
        for filter in self.filters:
            filter.reset()
        self.crashing_counter.reset()

    def norm_fc_output(self, action4 : list):
        action4[0] =  norm(action4[0])
        action4[1] =  norm(action4[1])
        action4[2] =  norm(action4[2])
        action4[3] =  norm(action4[3],lower_side=0.,upper_side=1.)
        # action4 = [filter.update(x) for filter, x in zip(self.filters, action4)]
        return action4

    def direct_LU_flight_controler(
        self,
        fighter,
        fix_vec:Vector3,
        intent_mach,
        strength_bias = 0.
    ):
        

        intent_heading = fix_vec.get_list()
        intent_heading_vec_fix_origin = Vector3(intent_heading)

        crashing = False 
        # 低高度保护
        if (
            (max(fighter.height, 0)/max(fighter.vd, 1e-3)) < 25  or 
            fighter.pitch < np.deg2rad(-45) or
            fighter.height < feet_to_meters(800)
        ) and ( 
            fighter.height < feet_to_meters(12000) or fighter.mach > 0.6
        ): ##in 15 seconds 
            crashing = True         
        crashing = self.crashing_counter.update(crashing)
        if crashing:
            # intent_heading= Vector3(fighter.heading)
            intent_heading[2] = 0 
            intent_heading[2] = Vector3(intent_heading).get_module()
                
        # # 高高度保护
        # over_height = False
        # if (
        #     (((15000 - fighter.height)/(-fighter.vd )) < 25 and fighter.vd < 0) or 
        #     (fighter.pitch > math.pi / 4 and fighter.height > 12000)
        # ) and fighter.height > 10000: 
        #     intent_heading=fighter.heading.get_list()
        #     intent_heading[2] = 0
        #     over_height = True
        #     crashing = True



        # NEU to ego
        
        intent_heading[2] = -intent_heading[2]
        intent_heading = Vector3(intent_heading)
        intent_heading.rev_rotate_zyx_self(fighter.roll, fighter.pitch, fighter.yaw)
        intent_heading[2] = -1 * intent_heading[2]
        intent_heading.prod(1/intent_heading.get_module())

        # world_up = Vector3([0,0,1])
        # world_up[2] = -world_up[2]
        # world_up = Vector3(world_up)
        # world_up.rev_rotate_zyx_self(fighter.roll, fighter.pitch, fighter.yaw)
        # world_up[2] = -1 * world_up[2]
        # world_up.prod(1/world_up.get_module())

        # # pitch 
        # intent_heading_saver = utils.Vector3(intent_heading.get_list())
        # err_pitch = math.asin(intent_heading[2])
        # if err_pitch < 0 : err_pitch*=4
        # if err_pitch > math.pi/6: err_pitch = math.pi/6
        # if err_pitch < -math.pi/6 : err_pitch =- math.pi/6
        # if intent_heading[0] < 0: # 后半球拉杆 
        #     err_pitch = math.pi/6                
        # err_pitch *= 1.5/2
        
        # # roll 
        # gain = 1.*math.tanh(-(fighter.vd - 50*(fighter.height-6000)/11500) * 1e-2)

        # intent_location_angle = intent_heading_saver.get_angle(utils.Vector3([1,0,0]))

        # if ((intent_location_angle> math.pi*0.95 )):

        #     err_roll = 0

        #     if (intent_heading[1]> 0 and self.right_turn == 0): self.right_turn = 1
        #     if (intent_heading[1]< 0 and self.right_turn == 0): self.right_turn = -1

        #     if (self.right_turn == 1 ):err_roll+=  (-1.4 * (fighter.roll - math.pi/2) ) 
        #     if (self.right_turn == -1):err_roll +=  (-1.4*(fighter.roll + math.pi/2) ) 
        #     if (fighter.roll > 0):err_roll+=  1* gain
        #     else:err_roll +=  -1*gain 
        # else :
        #     err_psi = math.atan2(intent_heading[1], intent_heading[0])
        #     if abs(err_psi) < 0.1:
        #         err_roll=math.atan(intent_heading[1])
        #     else:
        #         if err_pitch < 0 and err_pitch > -math.pi / 12:
        #             err_roll = math.atan2(intent_heading[1],-5*intent_heading[2])
        #         else:
        #             err_roll = math.atan2(intent_heading[1],5*intent_heading[2])
        #     self.right_turn = 0

        # intent_heading = intent_heading_saver

        # pitch 
        intent_heading_saver = utils.Vector3(intent_heading.get_list())
        # err_pitch = math.asin(intent_heading[2])
        err_pitch = utils.Vector3([1,0,0]).get_angle(intent_heading,pid_set_zero=1)
        if err_pitch < 0 : err_pitch*=4
        if err_pitch > math.pi/6: err_pitch = math.pi/6
        if err_pitch < -math.pi/6 : err_pitch =- math.pi/6
        if intent_heading[0] < 0  : # 后半球拉杆 
            err_pitch = math.pi/6                
        err_pitch *= 1.5/2

        # roll 
        gain = 1.*math.tanh(-(fighter.vd - 50*(fighter.height-6000)/11500) * 1e-2)

        intent_location_angle = fighter.heading.get_angle(intent_heading_vec_fix_origin)
        low_alt_thre = feet_to_meters(8000)
        if False and crashing:
            # Original ver.
            # err_roll = utils.Vector3([0,0,1]).get_angle(world_up,pid_set_zero=0) 

            err_roll = utils.Vector3([0,0,1]).get_angle(intent_heading,pid_set_zero=0) 
            # # By Tom-line
            # err_psi = math.atan2(intent_heading.vec[1], intent_heading.vec[0])
            # if abs(err_psi) < 0.1:
            #     err_roll = math.atan(intent_heading.vec[1])
            # else:
            #     err_roll = math.atan2(intent_heading.vec[1], 5 * intent_heading.vec[2])

            self.right_turn = 0

        # elif (fighter.height < low_alt_thre and err_pitch > np.deg2rad(10)):
        #     # hori turn
        #     err_roll = 0
        #     # err_roll = 0.3*pwr(utils.Quaternion4([0,0,1]).get_angle(intent_heading,pid_set_zero=0))

        #     if (intent_heading[1]> 0 and self.right_turn == 0): self.right_turn = 1
        #     if (intent_heading[1]< 0 and self.right_turn == 0): self.right_turn = -1

        #     deg_turn = np.deg2rad(90)
        #     if fighter.height < low_alt_thre:
        #         deg_turn = ((1 - (low_alt_thre - max(fighter.height, 0))) * 0.8 + 0.2) * np.deg2rad(90)
        #     if (self.right_turn == 1 ):err_roll+=  (-1.4 * (fighter.roll - deg_turn)) 
        #     if (self.right_turn == -1):err_roll += (-1.4 * (fighter.roll + deg_turn)) 
        #     if (fighter.roll > 0):err_roll+=  1* gain
        #     else:err_roll +=  -1*gain 
        # elif (intent_location_angle > np.deg2rad(99)):
        elif intent_location_angle > np.deg2rad(99):
            # hori turn
            err_roll = 0
            # err_roll = 0.3*pwr(utils.Quaternion4([0,0,1]).get_angle(intent_heading,pid_set_zero=0))

            if (intent_heading[1]> 0 and self.right_turn == 0): self.right_turn = 1
            if (intent_heading[1]< 0 and self.right_turn == 0): self.right_turn = -1

            deg_turn = np.deg2rad(85)
            if (self.right_turn == 1 ):err_roll+=  (-1.4 * (fighter.roll - deg_turn)) 
            if (self.right_turn == -1):err_roll += (-1.4 * (fighter.roll + deg_turn)) 
            if (fighter.roll > 0):err_roll+=  1* gain
            else:err_roll +=  -1*gain 
        else :
            # Original ver.
            if err_pitch < 0 and err_pitch > np.deg2rad(-15):err_roll =  utils.Vector3([0,0,-1]).get_angle(intent_heading,pid_set_zero=0)
            else :err_roll = utils.Vector3([0,0,1]).get_angle(intent_heading,pid_set_zero=0) #and (fighter.height>10000 or fighter.height < 5000 or fighter.mach < 0.8)

            # # By Tom-line
            # err_psi = math.atan2(intent_heading.vec[1], intent_heading.vec[0])
            # if abs(err_psi) < 0.1:
            #     err_roll=math.atan(intent_heading.vec[1])
            # else:
            #     if err_pitch < 0 and err_pitch > -math.pi / 12:
            #         err_roll = math.atan2(intent_heading.vec[1],-5*intent_heading.vec[2])
            #     else:
            #         err_roll = math.atan2(intent_heading.vec[1],5*intent_heading.vec[2])

            self.right_turn = 0
        intent_heading = intent_heading_saver


        err_roll_angle = err_roll
        if (err_roll > math.pi/3): err_roll = math.pi/3
        if (err_roll < -math.pi/3): err_roll = -math.pi/3
            
        # throttle
        err_throttle = intent_mach - fighter.mach

        ### PID  ###
        roll_bias = 0.75*utils.norm(strength_bias,lower_side=-1.,upper_side=1.) +1.
        pitch_bias = 0.75*utils.norm(strength_bias,lower_side=-1.,upper_side=0.) +1.
        kroll_p = self.kroll_p * roll_bias
        kroll_i = self.kroll_i * roll_bias
        kroll_d = self.kroll_d * roll_bias
        kpitch_p = self.kpitch_p * pitch_bias
        kpitch_i = self.kpitch_i * pitch_bias
        kpitch_d = self.kpitch_d * pitch_bias 
        if fighter.height> 11000:
            kpitch_p *=   (20000 - fighter.height )/9000
            kpitch_i *=   (20000 - fighter.height )/9000  
            kroll_p *=   (16000 - fighter.height )/5000
            kroll_i *=   (16000 - fighter.height )/5000
        

        if(crashing != True) :
            if fighter.mach >0.3:
                kpitch_p *= (fighter.mach + 0.2)
                kpitch_i *= (fighter.mach + 0.2)

                if err_pitch > -math.pi/12:
                    kroll_p *= 0.7 + 0.3*(abs(err_pitch)/(1.5 * math.pi/12))
                    kroll_i *= 0.7 + 0.3*(abs(err_pitch)/(1.5 * math.pi/12))
            else: 
                kpitch_p *= 0.5
                kpitch_i *= 0.5
                kroll_p *=  0.8
                kroll_i *=  0.8

            kpitch_d *= fighter.mach
        
        # err_pitch = self.error_pitch_filter.update(err_pitch)

        action = self.pid(err_roll, err_pitch, err_throttle,
                          kroll_p, kroll_i, kroll_d,
                          kpitch_p, kpitch_i, kpitch_d,
                          throttle_base=self.get_throttle_base(fighter, intent_mach))
        if not crashing:
            if abs(err_roll_angle) > np.deg2rad(45) and abs(err_roll_angle) < np.deg2rad(180 - 25):  
                action[1] = 0

        ## 低速度超控 
        if (fighter.mach < 0.5): 
            action[3] = 1
            if (fighter.mach < 0.18): 
                action[1] /= 10
                action[0] /= 2
        ## 高速低高超控
        if(fighter.height<3200 and fighter.pitch < -1.15 and fighter.mach > 1.2): 
            action[3] =0           
        
        # ## 防止pitch轴抖动
        # if action[1] > 0:
        #     action[1] = action[1] * 0.20
        # action[1] = np.clip(action[1], -1.0, 0.20)

        return self.norm_fc_output(action)





    # def flight_controler(self,fighter,intent_heading,intent_mach,dodge,dodge_range,target_height ,crashing = False,over_speed = False,strength_bias= 0.):
    #     intent_heading_list = intent_heading
    #     dodge_list = [1,0,0]
    #     action  = [0,0,0,1]
    #     dodge_flg =False
    #     emergency_pull = False
        
    #     if (dodge != False and dodge_range < 40e3): 
    #         intent_heading = dodge
    #         dodge_list = dodge
    #         dodge_flg = True

    #     # 低高度保护
    #     if ( crashing ) : 
    #         intent_heading=fighter.heading.get_list()
    #         intent_heading[2]   = 0 
            



                
    #     # 高高度保护
    #     over_height = False
    #     if   (  (((15000 - fighter.height)/(-fighter.vd ))< 25 and fighter.vd <0)  or (fighter.pitch > math.pi / 4 and fighter.height > 12000)   ) and dodge_flg == False  and fighter.strategy_mode== False    and fighter.height>6000 : 
    #         intent_heading=fighter.heading.get_list()
    #         intent_heading[2]   = 0
    #         over_height = True
    #         crashing = True
        
    #     # 低速
    #     low_speed = False
    #     if fighter.mach < 0.3 and (not dodge_flg) :
    #         intent_heading=fighter.heading.get_list()
    #         intent_heading[2]   = 0
    #         low_speed = True

    #     # 北东上坐标系转本机坐标系(好像是前左上？)
    #     # error calc 有点bug但能跑 
    #     intent_heading[2] = -intent_heading[2]  #-------------
    #     intent_heading = utils.Vector3(intent_heading)
    #     intent_heading.prod(1/intent_heading.get_module())
    #     if crashing : 
    #         if over_height : intent_heading[2] += 0.6
    #         elif ( fighter.mach > 0.3) :intent_heading[2] -= 0.6   
    #     if low_speed : 
    #         intent_heading[2] += 0.6
    #     if (not( crashing or low_speed or dodge_flg)) and fighter.mrm_guide_flg:
    #         intent_heading[2] +=  0.05          
            
                    
    #     intent_heading.rev_rotate_zyx_self(fighter.roll,fighter.pitch,fighter.yaw)
    #     intent_heading[2] = -1* intent_heading[2]   # ----------------------
    #     if crashing == True and intent_heading[0] < 0 : intent_heading[0] *=-1

    #     intent_heading.prod(1/intent_heading.get_module())

    #     # pitch 
    #     intent_heading_saver = utils.Vector3(intent_heading.get_list())
    #     err_pitch = math.asin(intent_heading[2])
    #     # err_pitch = utils.Vector3([1,0,0]).get_angle(intent_heading,pid_set_zero=1)
    #     if err_pitch < 0 : err_pitch*=4
    #     if err_pitch > math.pi/6: err_pitch = math.pi/6
    #     if err_pitch < -math.pi/6 : err_pitch =- math.pi/6
    #     if intent_heading[0] < 0  : # 后半球拉杆 
    #         err_pitch = math.pi/6                
    #     err_pitch *= 1.5/2
        

    #     # roll 
    #     gain = 1.*math.tanh(-(fighter.vd - 50*(fighter.height-6000)/11500) * 1e-2)
    #     turn_flg = False 

    #     dodge_location_angle = 0
    #     if (dodge_flg):  
    #         dodge_location_angle = fighter.heading.get_angle(utils.Vector3(dodge_list))
    #     intent_location_angle = fighter.heading.get_angle(utils.Vector3(intent_heading_list))
    #     if ( (crashing  ) or dodge_flg or   
    #         (intent_heading_list[2]>5000 and fighter.height< 5000) ):

    #         # Original ver.
    #         err_roll = utils.Vector3([0,0,1]).get_angle(intent_heading,pid_set_zero=0) 

    #         # By Tom-line
    #         # err_psi = math.atan2(intent_heading.vec[1], intent_heading.vec[0])
    #         # if abs(err_psi) < 0.1:
    #         #     err_roll=math.atan(intent_heading.vec[1])
    #         # else:
    #         #     err_roll = math.atan2(intent_heading.vec[1],5*intent_heading.vec[2])

    #         self.right_turn = 0
    #     elif (((intent_location_angle> math.pi*0.55 or  
    #         (target_height > 9000 and intent_location_angle > math.pi * 0.45 )) and dodge_flg == False ) 
    #         # or (dodge_flg and dodge_location_angle > math.pi * 0.82 )
    #             ):

    #         err_roll = 0
    #         # err_roll = 0.3*pwr(utils.Quaternion4([0,0,1]).get_angle(intent_heading,pid_set_zero=0))
    #         turn_flg = True 

    #         if (intent_heading[1]> 0 and self.right_turn == 0): self.right_turn = 1
    #         if (intent_heading[1]< 0 and self.right_turn == 0): self.right_turn = -1

    #         if (self.right_turn == 1 ):err_roll+=  (-1.4 * (fighter.roll - math.pi/2) ) 
    #         if (self.right_turn == -1):err_roll +=  (-1.4*(fighter.roll + math.pi/2) ) 
    #         if (fighter.roll > 0):err_roll+=  1* gain
    #         else:err_roll +=  -1*gain 

    #     else :
    #         # Original ver.
    #         if err_pitch < 0 and err_pitch > -math.pi/12:err_roll =  utils.Vector3([0,0,-1]).get_angle(intent_heading,pid_set_zero=0)
    #         else :err_roll = utils.Vector3([0,0,1]).get_angle(intent_heading,pid_set_zero=0) #and (fighter.height>10000 or fighter.height < 5000 or fighter.mach < 0.8)

    #         # By Tom-line
    #         # err_psi = math.atan2(intent_heading.vec[1], intent_heading.vec[0])
    #         # if abs(err_psi) < 0.1:
    #         #     err_roll=math.atan(intent_heading.vec[1])
    #         # else:
    #         #     if err_pitch < 0 and err_pitch > -math.pi / 12:
    #         #         err_roll = math.atan2(intent_heading.vec[1],-5*intent_heading.vec[2])
    #         #     else:
    #         #         err_roll = math.atan2(intent_heading.vec[1],5*intent_heading.vec[2])

    #         self.right_turn = 0
    #     intent_heading = intent_heading_saver

    #     err_roll_angle = err_roll
    #     if (err_roll > math.pi/3): err_roll = math.pi/3
    #     if (err_roll < -math.pi/3): err_roll = -math.pi/3
            


    #     # throttle
    #     err_throttle = intent_mach - fighter.mach








    #     ### PID  ###
    #     roll_bias = 0.5*utils.norm(strength_bias,lower_side=-1.,upper_side=1.) +1.
    #     pitch_bias = 0.5*utils.norm(strength_bias,lower_side=-1.,upper_side=0.) +1.
    #     kroll_p = self.kroll_p * roll_bias
    #     kroll_i = self.kroll_i * roll_bias
    #     kroll_d = self.kroll_d * roll_bias
    #     kpitch_p = self.kpitch_p * pitch_bias
    #     kpitch_i = self.kpitch_i * pitch_bias
    #     kpitch_d = self.kpitch_d * pitch_bias 
    #     if fighter.height> 11000:
    #         kpitch_p *=   (20000 - fighter.height )/9000
    #         kpitch_i *=   (20000 - fighter.height )/9000  
    #         kroll_p *=   (16000 - fighter.height )/5000
    #         kroll_i *=   (16000 - fighter.height )/5000
        
    

    #     # if fighter.save_yourself:
    #     #     kpitch_p *=0.4
    #     #     kpitch_i *=0.4
    #     #     kpitch_d *=0.4
    #     #     kroll_p *= 0.6
    #     #     kroll_i *= 0.6
    #     #     kroll_d *= 0.6



    #     if(  dodge_flg!= True and crashing != True) :
    #         if fighter.mach >0.3:
    #             kpitch_p *= (fighter.mach + 0.2)
    #             kpitch_i *= (fighter.mach + 0.2)

    #             if err_pitch > -math.pi/12:
    #                 kroll_p *= 0.7 + 0.3*(abs(err_pitch)/(1.5 * math.pi/12))
    #                 kroll_i *= 0.7 + 0.3*(abs(err_pitch)/(1.5 * math.pi/12))
    #             # kroll_p *= (fighter.mach/2 + 0.5)
    #             # kroll_i *=  (fighter.mach/2 + 0.5)
    #         else: 
    #             kpitch_p *= 0.5
    #             kpitch_i *= 0.5
    #             kroll_p *=  0.8
    #             kroll_i *=  0.8
    #         if fighter.mrm_guide_flg :
    #             kpitch_i *=0.5
    #             # kroll_p *= 0.7
    #             # kroll_i *= 0.7

    #         # if (fighter.my_target_ind == -1 or fighter.strategy_mode) : 
    #         #     kpitch_p *= 1
    #         #     kroll_p *= 1
    #         kpitch_d *= fighter.mach
    #     if(  dodge_flg!= True and crashing != True and ((intent_location_angle)) < math.pi/30) : 
    #         kroll_p *= 0.8

    #         # kroll_i *= ((fighter.mach -1.6)*0.5 + 1) * 0.2
    #         # kroll_d *= ((fighter.mach -1.6)*0.5 + 1) * 0.2
    
    #     action = self.pid(err_roll, err_pitch, err_throttle,
    #                       kroll_p, kroll_i, kroll_d,
    #                       kpitch_p, kpitch_i, kpitch_d,
    #                       throttle_base=self.get_throttle_base(fighter, intent_mach))
    #     if not (dodge_flg or crashing):
    #         if  abs(err_roll_angle) > math.pi/4 and  abs(err_roll_angle) < math.pi *3/4:  
    #             action[1] =0
    #         # else :pid_output[1] *= 1-0.35*abs(err_roll)

    #     # ## RWR超控
    #     # if((dodge_flg == True and dodge_range < 1e3) or emergency_pull and self.height<13000):
    #     #     action[1] = -1
    #     ## 低速度超控 
    #     if (fighter.mach < 0.18): 
    #         action[1] /= 10
    #         action[0] /= 2
    #         action[3] =1
    #     ## 高速低高超控
    #     if(fighter.height<3200 and fighter.pitch < -1.15 and fighter.mach > 1.2): 
    #         # action[1] = -1 
    #         action[3] =0    
    #     return self.norm_fc_output(action)


    def pid(self, err_roll, err_pitch, err_throttle,
            kroll_p, kroll_i, kroll_d,
            kpitch_p, kpitch_i, kpitch_d,
            throttle_base=0.5) -> list:
        pid_output = [0, 0, 0, 1]

        # roll
        # I
        self.sum_err_roll += err_roll * self.dt
        # D
        d_err_roll = (err_roll - self.last_err_roll)/self.dt 
        # output
        pid_output[0] = kroll_p * err_roll +  kroll_d * d_err_roll 
        if(abs(err_roll)<0.32):pid_output[1] +=kroll_i * self.sum_err_roll # 引入积分
        self.sum_err_roll = norm(self.sum_err_roll, -2.5, 2.5)

        # pitch
        # I
        if abs(err_pitch ) < math.pi/6 : 
            if  (err_pitch <= math.pi/90 ) and (err_pitch>=-math.pi/90): 
                self.sum_err_pitch = 0
            else :self.sum_err_pitch += err_pitch * self.dt
        else :
            self.sum_err_pitch = 0
        # D
        d_err_pitch = (err_pitch - self.last_err_pitch)/self.dt 
        # output
        pid_output[1] = kpitch_p * err_pitch  + kpitch_d * d_err_pitch            
        if abs(err_pitch ) < math.pi/6 : 
            pid_output[1] +=kpitch_i * self.sum_err_pitch  # 引入积分

        self.sum_err_pitch = norm(self.sum_err_pitch, -8., 8.)

        # throttle 
        # I
        self.sum_err_throttle += err_throttle
        # D
        d_err_throttle = (err_throttle - self.last_err_throttle)
        # output
        pid_output[3] = throttle_base + self.kthrottle_p * err_throttle + self.kthrottle_i * self.sum_err_throttle + self.kthrottle_d * d_err_throttle
        pid_output[3] = norm(pid_output[3], 0., 1.)

        self.sum_err_throttle = norm(self.sum_err_throttle, -10., 10.)

        self.last_err_roll = err_roll
        self.last_err_pitch = err_pitch
        self.last_err_throttle = err_throttle

        return pid_output


    @staticmethod
    def get_throttle_base(fighter, intent_mach) -> float:
        base = 0.5

        if fighter.height > 7500: 
            base +=  0.5 * ((fighter.height - 7500)/7500)

        if intent_mach > 1 : 
            base +=  (intent_mach - 1)

        if (fighter.height < 10000 or fighter.pitch > 0 ) : 
            base += 0.4 * fighter.pitch/(math.pi/2)
        
        if fighter.mach < 0.7:
            base = 1
        
        return base