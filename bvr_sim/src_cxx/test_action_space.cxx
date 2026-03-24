#include "test_main.hxx"
#include "rl/action_space.hxx"
#include "simulator/register.hxx"

TEST(ActionSpace, ConstructFromRegisterWithValidAction) {
    bvr_sim::Register reg;
    reg.set("delta_heading", json::JSON(0.1));
    reg.set("delta_altitude", json::JSON(0.2));
    reg.set("delta_speed", json::JSON(0.3));
    reg.set("fire", json::JSON());

    bvr_sim::ActionSpace action(reg);

    ASSERT_NEAR(action.delta_heading(), 0.1, 1e-9);
    ASSERT_NEAR(action.delta_altitude(), 0.2, 1e-9);
    ASSERT_NEAR(action.delta_speed(), 0.3, 1e-9);
}

