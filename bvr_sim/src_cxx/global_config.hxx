#pragma once


namespace bvr_sim {

struct GlobalConfig {
    GlobalConfig() = delete;

    static double dt;
    static double sim_time;
};

#define cfg GlobalConfig

}