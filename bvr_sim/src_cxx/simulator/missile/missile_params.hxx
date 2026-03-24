#pragma once

#include <memory>
#include <string>
#include "rubbish_can/interp_table.hxx"

namespace bvr_sim {

/// Generic missile parameter container for multi-model missile framework.
/// Replaces hardcoded MissileParameter in AIM120C.
/// Factory method get_missile_params() loads params from hardcoded tables or future config.
struct MissileParams {
    // ===== 物理参数 =====
    double m0;              // 初始质量 (kg)
    double dm;              // 单位时间质量流率 (kg/s)
    double thrust;          // 推力 (N)
    double t_max;           // 推力最大时间 (s)
    double t_thrust;        // 实际推力工作时间 (s)
    double length;          // 导弹长度 (m)
    double diameter;        // 导弹直径 (m)
    double nyz_max;         // 最大法向过载 (g)
    double g;               // 重力加速度 (m/s^2)

    // ===== 空气动力学参数 =====
    std::shared_ptr<const InterpTable> cx_total_table;  // Mach -> Cx_total (无迎角补偿)
    double S_ref;           // 参考面积 (m^2)
    double Rc;              // 最小爬升半径 (m, SI单位)
    double mach_min;        // 最小Mach数

    // ===== 导引参数 =====
    double K;               // 比例导航系数或导引增益
    double search_fov;      // 搜索视场角 (rad, 已转换)
    double search_range;    // 搜索范围 (m, 已转换)
    double search_start_range;  // 开始搜索距离阈值 (m, 已转换)
    double track_gimbal_limit;  // 跟踪万向节限制 (rad, 已转换)

    // ===== 状态机参数 =====
    bool enable_search;     // 启用搜索阶段
    bool enable_track;      // 启用跟踪阶段
    bool enable_loft;       // 启用爬升机动
    double loss_time_threshold;  // 信号丢失时长阈值 (s)

    // ===== 静态工厂方法 =====
    static MissileParams get_missile_params(const std::string& missile_model);
};

} // namespace bvr_sim
