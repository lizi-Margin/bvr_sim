#pragma once

#include <string>
#include <map>
#include <memory>
#include "support/check.hxx"
#include "c3utils/c3utils.hxx"

namespace bvr_sim {

struct FlightControllerParams {
    double kroll_p;
    double kroll_i;
    double kroll_d;

    double kpitch_p;
    double kpitch_i;
    double kpitch_d;

    double kthrottle_p;
    double kthrottle_i;
    double kthrottle_d;

    double crash_height_threshold_B; 
    double severe_crash_height;      
    double crash_height_threshold_A; 
    double pi_decay_start;     
    double pitch_pi_decay_end;       
    double roll_pi_decay_end;        

    double minimum_speed_B;          
    double maximum_speed_A;          

    double pitch_push_down_cutoff;

    static FlightControllerParams get_f16_params() noexcept {
        FlightControllerParams f16_params;

        f16_params.kroll_p = 1.2;
        f16_params.kroll_i = 0.2;
        f16_params.kroll_d = 0.0;

        f16_params.kpitch_p = -3.4;
        f16_params.kpitch_i = -0.0;
        f16_params.kpitch_d = -0.5;

        f16_params.kthrottle_p = 0.03;
        f16_params.kthrottle_i = 0.06;
        f16_params.kthrottle_d = 500;

        f16_params.crash_height_threshold_B = c3u::feet_to_meters(4000.0);         // 4000 ft
        f16_params.severe_crash_height = c3u::feet_to_meters(2000.0);             // 2000 ft
        f16_params.crash_height_threshold_A = c3u::feet_to_meters(800.0);               // 800 ft
        f16_params.pi_decay_start = 11000.0;       
        f16_params.pitch_pi_decay_end = 20000.0; 
        f16_params.roll_pi_decay_end = 16000.0;    

        f16_params.minimum_speed_B = 0.18;
        f16_params.maximum_speed_A = 0.5;
        f16_params.pitch_push_down_cutoff = -1.0;

        return f16_params;
    }

    static FlightControllerParams get_f18_params() noexcept {
        FlightControllerParams f18_params;

        f18_params.kroll_p = 1.2;
        f18_params.kroll_i = 0.2;
        f18_params.kroll_d = 0.0;
        f18_params.kpitch_p = -3.4;
        f18_params.kpitch_i = -0.0;
        f18_params.kpitch_d = -0.5;

        f18_params.kthrottle_p = 0.03;
        f18_params.kthrottle_i = 0.06;
        f18_params.kthrottle_d = 500;

        f18_params.crash_height_threshold_B = c3u::feet_to_meters(4000.0); 
        f18_params.severe_crash_height = c3u::feet_to_meters(2000.0); 
        f18_params.crash_height_threshold_A = c3u::feet_to_meters(800.0);    
        f18_params.pi_decay_start = 11000.0;       
        f18_params.pitch_pi_decay_end = 20000.0; 
        f18_params.roll_pi_decay_end = 16000.0;    

        f18_params.minimum_speed_B = 0.18;
        f18_params.maximum_speed_A = 0.5;
        f18_params.pitch_push_down_cutoff = -1.0;

        return f18_params;
    }

    static FlightControllerParams get_f15_params() noexcept {
        FlightControllerParams f15_params;

        f15_params.kroll_p = 1.2;
        f15_params.kroll_i = 1.4;
        f15_params.kroll_d = 0.3;
        f15_params.kpitch_p = -1.5;
        f15_params.kpitch_i = -0.0;
        f15_params.kpitch_d = -0.5;

        f15_params.kthrottle_p = 0.1;
        f15_params.kthrottle_i = 0.1;
        f15_params.kthrottle_d = 500;

        f15_params.crash_height_threshold_B = c3u::feet_to_meters(4000.0); 
        f15_params.severe_crash_height = c3u::feet_to_meters(2000.0); 
        f15_params.crash_height_threshold_A = c3u::feet_to_meters(800.0);    
        f15_params.pi_decay_start = 11000.0;       
        f15_params.pitch_pi_decay_end = 20000.0; 
        f15_params.roll_pi_decay_end = 16000.0;    

        f15_params.minimum_speed_B = 0.18;
        f15_params.maximum_speed_A = 0.5;
        f15_params.pitch_push_down_cutoff = -1.0;

        return f15_params;
    }


    static FlightControllerParams get_f22_params() noexcept {
        FlightControllerParams f22_params;

        f22_params.kroll_p = 3.8;
        f22_params.kroll_i = 2.0;
        f22_params.kroll_d = 0.2;
        f22_params.kpitch_p = -3.0;
        f22_params.kpitch_i = -0.0;
        f22_params.kpitch_d = -0.0;

        f22_params.kthrottle_p = 0.03;
        f22_params.kthrottle_i = 0.06;
        f22_params.kthrottle_d = 500;

        f22_params.crash_height_threshold_B = c3u::feet_to_meters(4000.0); 
        f22_params.severe_crash_height = c3u::feet_to_meters(2000.0); 
        f22_params.crash_height_threshold_A = c3u::feet_to_meters(800.0);    
        f22_params.pi_decay_start = 7000.0;       
        f22_params.pitch_pi_decay_end = 12000.0; 
        f22_params.roll_pi_decay_end = 16000.0;    

        f22_params.minimum_speed_B = 0.18;
        f22_params.maximum_speed_A = 0.5;
        f22_params.pitch_push_down_cutoff = 0.5;

        return f22_params;
    }

};

class FlightControllerParamsManager {
private:
    static FlightControllerParamsManager* instance_;
    std::map<std::string, FlightControllerParams> params_map_;

    FlightControllerParamsManager() noexcept;

public:
    FlightControllerParamsManager(const FlightControllerParamsManager&) = delete;
    FlightControllerParamsManager& operator=(const FlightControllerParamsManager&) = delete;
    static FlightControllerParamsManager& getInstance() noexcept;
    const FlightControllerParams& getParams(const std::string& aircraft_key) const noexcept;
};

}  // namespace bvr_sim
