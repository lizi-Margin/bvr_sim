#include "test_main.hxx"
#include "simulator/missile/fdm/generic_missile_fdm.hxx"
#include "simulator/param_store.hxx"

static bvr_sim::ParamStore make_test_params() {
    std::string json_str = R"({
        "doubles": {
            "m0": 161.48, "dm": 6.41, "thrust": 16325.0,
            "t_thrust": 8.0, "S_ref": 0.0248719, "mach_min": 0.8,
            "g": 9.81
        },
        "tables": {
            "cx_total_table": {
                "x": [0.5, 1.0, 2.0, 3.0],
                "y": [0.47, 0.75, 0.72, 0.55]
            },
            "n_available_table": {
                "x": [0.0, 5.0],
                "y": [30.0, 30.0]
            },
            "n_cmd_rate_limit_table": {
                "x": [0.0, 5.0],
                "y": [120.0, 120.0]
            }
        }
    })";
    return bvr_sim::ParamStore::from_string(json_str);
}

TEST(GenericMissileFDM, ResetSetsInitialState) {
    auto params = make_test_params();
    bvr_sim::GenericMissileFDM fdm(params, 0.1);

    std::map<std::string, std::any> init;
    init["position"] = std::array<double,3>{0.0, 0.0, 5000.0};
    init["velocity"] = std::array<double,3>{300.0, 0.0, 0.0};
    init["pitch"] = double(0.0);
    init["yaw"]   = double(0.0);
    init["roll"]  = double(0.0);
    fdm.reset(init);

    auto pos = fdm.get_position();
    ASSERT_NEAR(pos[2], 5000.0, 1e-6);
    ASSERT(fdm.get_speed() > 0.0);
}

TEST(GenericMissileFDM, StepAdvancesPosition) {
    auto params = make_test_params();
    bvr_sim::GenericMissileFDM fdm(params, 0.1);

    std::map<std::string, std::any> init;
    init["position"] = std::array<double,3>{0.0, 0.0, 5000.0};
    init["velocity"] = std::array<double,3>{300.0, 0.0, 0.0};
    init["pitch"] = double(0.0);
    init["yaw"]   = double(0.0);
    init["roll"]  = double(0.0);
    fdm.reset(init);

    auto pos_before = fdm.get_position();
    fdm.step({{"ny", 0.0}, {"nz", 0.0}});
    auto pos_after = fdm.get_position();

    ASSERT(pos_after[0] > pos_before[0]);
}

TEST(GenericMissileFDM, PropulsionBurnsMass) {
    auto params = make_test_params();
    bvr_sim::GenericMissileFDM fdm(params, 0.1);

    std::map<std::string, std::any> init;
    init["position"] = std::array<double,3>{0.0, 0.0, 5000.0};
    init["velocity"] = std::array<double,3>{300.0, 0.0, 0.0};
    init["pitch"] = double(0.0);
    init["yaw"]   = double(0.0);
    init["roll"]  = double(0.0);
    fdm.reset(init);

    ASSERT(fdm.is_thrusting());
    double mass_before = fdm.get_current_mass();
    fdm.step({{"ny", 0.0}, {"nz", 0.0}});
    ASSERT(fdm.get_current_mass() < mass_before);
}

TEST(GenericMissileFDM, MassConstantAfterBurnout) {
    auto params = make_test_params();
    bvr_sim::GenericMissileFDM fdm(params, 0.1);

    std::map<std::string, std::any> init;
    init["position"] = std::array<double,3>{0.0, 0.0, 5000.0};
    init["velocity"] = std::array<double,3>{300.0, 0.0, 0.0};
    init["pitch"] = double(0.0);
    init["yaw"]   = double(0.0);
    init["roll"]  = double(0.0);
    fdm.reset(init);

    // Step past t_thrust (8.0s at dt=0.1 = 80 steps)
    for (int i = 0; i < 85; ++i)
        fdm.step({{"ny", 0.0}, {"nz", 0.0}});

    ASSERT(!fdm.is_thrusting());
    double mass1 = fdm.get_current_mass();
    fdm.step({{"ny", 0.0}, {"nz", 0.0}});
    ASSERT_NEAR(fdm.get_current_mass(), mass1, 1e-9);
}
