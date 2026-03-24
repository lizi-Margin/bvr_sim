#include "missile_params.hxx"
#include "c3utils/c3utils.hxx"
#include <cmath>
#include <vector>

namespace bvr_sim {

using c3utils::deg2rad;
using c3utils::nm_to_meters;
using c3utils::feet_to_meters;

MissileParams MissileParams::get_missile_params(const std::string& missile_model) {
    if (missile_model == "AIM-120C7" || missile_model == "AIM-120C" ||
        missile_model == "AIM-120C5" || missile_model == "AIM-120") {

        MissileParams params;

        // ===== 物理参数（从aim120c.hxx的default_missile_parameter，第27-37行）=====
        // default_missile_parameter = {
        //     16325.0,  // thrust
        //     300.0,    // t_max
        //     8.0,      // t_thrust
        //     3.65,     // Length
        //     0.178,    // Diameter
        //     161.48,   // m0
        //     6.41,     // dm
        //     3.0,      // K
        //     100.0     // nyz_max
        // };
        params.m0 = 161.48;             // kg (default_missile_parameter.m0)
        params.dm = 6.41;               // kg/s (default_missile_parameter.dm)
        params.thrust = 16325.0;        // N (default_missile_parameter.thrust)
        params.t_max = 300.0;           // s (default_missile_parameter.t_max)
        params.t_thrust = 8.0;          // s (default_missile_parameter.t_thrust)
        params.length = 3.65;           // m (default_missile_parameter.Length)
        params.diameter = 0.178;        // m (default_missile_parameter.Diameter)
        params.nyz_max = 100.0;         // g (default_missile_parameter.nyz_max)
        params.K = 3.0;                 // 比例导航系数 (default_missile_parameter.K)
        params.g = 9.81;                // m/s^2

        // ===== 空气动力学参数（来自aim120c_adv_sim.py）=====
        // Mach表：26个点（0.0 到 5.0）
        // Cx0表：简化为仅Mach依赖，不含迎角和波阻补偿
        std::vector<double> mach_points = {
            0.0,  0.2,    0.4,     0.6,    0.8,     1.0,    1.2,    1.4,
            1.6,  1.8,    2.0,     2.2,    2.4,     2.6,    2.8,    3.0,
            3.2,  3.4,    3.6,     3.8,    4.0,     4.2,    4.4,    4.6,
            4.8,  5.0
        };
        std::vector<double> cx_values = {
            0.468, 0.468,  0.468,   0.468,  0.479,  0.751,  0.88,   0.8572,
            0.8132, 0.7645, 0.7205, 0.6808, 0.6447, 0.6119, 0.582,  0.5545,
            0.5292, 0.5057, 0.4838, 0.4633, 0.4439, 0.4256, 0.4083, 0.3921,
            0.377,  0.364
        };
        params.cx_total_table = std::make_shared<const InterpTable>(mach_points, cx_values);

        params.S_ref = 0.0248719;                    // m^2 (参考面积，来自aim120c_adv_sim.py)
        params.Rc = feet_to_meters(500.0);           // 转换feet到meter: 500 feet
        params.mach_min = 0.8;                       // 最小Mach

        // ===== 导引参数（从aim120c.cxx第54-58行的CTOR初始化）=====
        // _search_fov(deg2rad(20.0)),
        // _search_range(nm_to_meters(15.0)),
        // _search_start_range(nm_to_meters(10.0)),
        // _search_started(false),
        // _track_gimbal_limit(deg2rad(90.0)),
        params.search_fov = deg2rad(20.0);                  // 搜索FOV
        params.search_range = nm_to_meters(15.0);           // 搜索范围
        params.search_start_range = nm_to_meters(10.0);     // 搜索起始距离
        params.track_gimbal_limit = deg2rad(90.0);          // 跟踪万向节限制

        // ===== 状态机参数 =====
        params.enable_search = true;
        params.enable_track = true;
        params.enable_loft = false;                  // MModelA简化版不支持爬升机动
        params.loss_time_threshold = 1.0;            // 信号丢失1秒后切换回搜索（aim120c.cxx第221行）

        return params;
    }

    // 未知导弹型号，抛出异常
    throw std::runtime_error("Unknown missile model: " + missile_model);
}

} // namespace bvr_sim
