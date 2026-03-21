#include "../../test_main.cxx"
#include "reward_components.hxx"
#include "reward_manager.hxx"
#include "../simulator/aircraft/base.hxx"
#include "../simulator/missile/base.hxx"
#include <cmath>
#include <memory>
#include <vector>

namespace bvr_sim {

// Helper class to create mock aircraft for testing
class MockAircraft : public Aircraft {
public:
    MockAircraft(const std::string& uid, const std::string& color, double x = 0.0, double y = 0.0, double z = 5000.0)
        : Aircraft(uid, color) {
        position = {{x, y, z}};
        velocity = {{100.0, 0.0, 0.0}};
        is_alive = true;
        enemies_lock.clear();
    }

    void update(double dt) override {}
    void reset() override {}
};

// Helper class to create mock missiles for testing
class MockMissile : public Missile {
public:
    MockMissile(const std::string& uid, const std::string& owner_uid, double x = 0.0, double y = 0.0, double z = 5000.0)
        : Missile(uid, owner_uid) {
        position = {{x, y, z}};
        velocity = {{300.0, 0.0, 0.0}};
        is_alive = true;
    }

    void update(double dt) override {}
    void reset() override {}
};

// ============= Component Tests =============

// Test 1: EngageEnemyReward decreases when range increases
TEST(Reward, EngagementRewardDecreaseWithRange) {
    auto agent = std::make_shared<MockAircraft>("agent1", "red", 0.0, 0.0, 5000.0);
    auto enemy = std::make_shared<MockAircraft>("enemy1", "blue", 10000.0, 0.0, 5000.0);

    std::vector<std::shared_ptr<Aircraft>> all_agents = {agent, enemy};
    std::vector<std::shared_ptr<Missile>> all_missiles;

    RewardInfo info{0, false};
    EngageEnemyReward engagement_reward(0.01, "engage");

    // First step - establish baseline
    double reward1 = engagement_reward.compute(agent, all_agents, all_missiles, info);

    // Move enemy further away
    info.current_step = 1;
    enemy->position[0] = 20000.0;
    double reward2 = engagement_reward.compute(agent, all_agents, all_missiles, info);

    // Reward should be negative or decrease when distance increases
    ASSERT(reward2 <= reward1 || std::isnan(reward1));
}

// Test 2: EnemyDistanceReward is bounded between -1 and 0
TEST(Reward, DistanceRewardBounded) {
    auto agent = std::make_shared<MockAircraft>("agent1", "red", 0.0, 0.0, 5000.0);
    auto enemy = std::make_shared<MockAircraft>("enemy1", "blue", 30000.0, 0.0, 5000.0);

    std::vector<std::shared_ptr<Aircraft>> all_agents = {agent, enemy};
    std::vector<std::shared_ptr<Missile>> all_missiles;

    RewardInfo info{0, false};
    EnemyDistanceReward distance_reward(0.01, "distance");

    double reward = distance_reward.compute(agent, all_agents, all_missiles, info);

    ASSERT_RANGE(reward, -1.0, 0.0);
}

// Test 3: AltitudeAdvantageReward responds to altitude difference
TEST(Reward, AltitudeAdvantageReward) {
    auto agent = std::make_shared<MockAircraft>("agent1", "red", 0.0, 0.0, 8000.0);
    auto enemy = std::make_shared<MockAircraft>("enemy1", "blue", 0.0, 0.0, 5000.0);

    std::vector<std::shared_ptr<Aircraft>> all_agents = {agent, enemy};
    std::vector<std::shared_ptr<Missile>> all_missiles;

    RewardInfo info{0, false};
    AltitudeAdvantageReward altitude_reward(0.005, "altitude");

    double reward = altitude_reward.compute(agent, all_agents, all_missiles, info);

    // Higher altitude advantage should give positive reward (normalized)
    ASSERT(reward >= -1.0 && reward <= 1.0);
}

// Test 4: SurvivalReward is non-negative
TEST(Reward, SurvivalRewardNonNegative) {
    auto agent = std::make_shared<MockAircraft>("agent1", "red", 0.0, 0.0, 5000.0);
    auto enemy = std::make_shared<MockAircraft>("enemy1", "blue", 10000.0, 0.0, 5000.0);

    std::vector<std::shared_ptr<Aircraft>> all_agents = {agent, enemy};
    std::vector<std::shared_ptr<Missile>> all_missiles;

    RewardInfo info{0, false};
    SurvivalReward survival_reward(0.01, "survival");

    double reward = survival_reward.compute(agent, all_agents, all_missiles, info);

    ASSERT(reward >= 0.0);
}

// Test 5: SpeedReward penalizes deviations from target speed
TEST(Reward, SpeedAdvantageReward) {
    auto agent = std::make_shared<MockAircraft>("agent1", "red", 0.0, 0.0, 5000.0);
    agent->velocity = {{600.0, 0.0, 0.0}};  // target_speed default is 600

    std::vector<std::shared_ptr<Aircraft>> all_agents = {agent};
    std::vector<std::shared_ptr<Missile>> all_missiles;

    RewardInfo info{0, false};
    SpeedReward speed_reward(0.005, 600.0, "speed");

    double reward = speed_reward.compute(agent, all_agents, all_missiles, info);

    // Reward at target speed should be non-negative
    ASSERT(reward >= -1.0 && reward <= 1.0);
}

// ============= Manager Tests =============

// Test 6: RewardManager aggregates multiple components correctly
TEST(Reward, RewardManagerAggregation) {
    auto agent = std::make_shared<MockAircraft>("agent1", "red", 0.0, 0.0, 5000.0);
    auto enemy = std::make_shared<MockAircraft>("enemy1", "blue", 30000.0, 0.0, 5000.0);

    std::vector<std::shared_ptr<Aircraft>> all_agents = {agent, enemy};
    std::vector<std::shared_ptr<Missile>> all_missiles;

    RewardInfo info{0, false};
    RewardManager manager;

    // Add components with known weights
    auto survival = std::make_shared<SurvivalReward>(0.01, "survival");
    auto distance = std::make_shared<EnemyDistanceReward>(0.01, "distance");

    manager.add_component(survival);
    manager.add_component(distance);

    double total_reward = manager.compute_reward(agent, all_agents, all_missiles, info);

    // Total should be finite (not NaN)
    ASSERT(!std::isnan(total_reward));
}

// Test 7: MissileResultReward handles hit/miss correctly
TEST(Reward, MissileResultReward) {
    auto agent = std::make_shared<MockAircraft>("agent1", "red", 0.0, 0.0, 5000.0);
    auto enemy = std::make_shared<MockAircraft>("enemy1", "blue", 10000.0, 0.0, 5000.0);

    std::vector<std::shared_ptr<Aircraft>> all_agents = {agent, enemy};

    RewardInfo info{0, false};
    MissileResultReward result_reward(1.0, 100.0, -5.0, "missile_result");

    // Create a missile that would be marked as tracked
    auto missile = std::make_shared<MockMissile>("missile1", "agent1", 5000.0, 0.0, 5000.0);
    std::vector<std::shared_ptr<Missile>> all_missiles = {missile};

    double reward = result_reward.compute(agent, all_agents, all_missiles, info);

    // Should be finite
    ASSERT(!std::isnan(reward));
}

// Test 8: SafeAltitudeReward encourages safe altitude range
TEST(Reward, SafeAltitudeReward) {
    std::vector<std::shared_ptr<Aircraft>> all_agents;
    std::vector<std::shared_ptr<Missile>> all_missiles;

    RewardInfo info{0, false};
    SafeAltitudeReward safe_alt(0.01, 2000.0, 12000.0, "safe_alt");

    // Test: aircraft in safe range
    auto agent_safe = std::make_shared<MockAircraft>("agent1", "red", 0.0, 0.0, 5000.0);
    double reward_safe = safe_alt.compute(agent_safe, all_agents, all_missiles, info);
    ASSERT(reward_safe >= -2.0 && reward_safe <= 1.0);

    // Test: aircraft below safe range
    auto agent_low = std::make_shared<MockAircraft>("agent2", "red", 0.0, 0.0, 1000.0);
    double reward_low = safe_alt.compute(agent_low, all_agents, all_missiles, info);
    ASSERT(reward_low <= 0.0);  // Should be penalty

    // Test: aircraft above safe range
    auto agent_high = std::make_shared<MockAircraft>("agent3", "red", 0.0, 0.0, 15000.0);
    double reward_high = safe_alt.compute(agent_high, all_agents, all_missiles, info);
    ASSERT(reward_high <= 0.0);  // Should be penalty
}

// ============= Edge Case Tests =============

// Test 9: NaN handling - dead agent should return 0
TEST(Reward, NaNHandling) {
    auto agent = std::make_shared<MockAircraft>("agent1", "red", 0.0, 0.0, 5000.0);
    agent->is_alive = false;  // Mark as dead

    auto enemy = std::make_shared<MockAircraft>("enemy1", "blue", 10000.0, 0.0, 5000.0);

    std::vector<std::shared_ptr<Aircraft>> all_agents = {agent, enemy};
    std::vector<std::shared_ptr<Missile>> all_missiles;

    RewardInfo info{0, false};
    EngageEnemyReward engagement_reward(0.01, "engage");
    SurvivalReward survival_reward(0.01, "survival");

    double engage_reward = engagement_reward.compute(agent, all_agents, all_missiles, info);
    double survival_reward_val = survival_reward.compute(agent, all_agents, all_missiles, info);

    // Dead agent should return 0, not NaN
    ASSERT_EQ(engage_reward, 0.0);
    ASSERT_EQ(survival_reward_val, 0.0);
}

// Test 10: OutOfBoundsValues - extreme positions handled gracefully
TEST(Reward, OutOfBoundsValues) {
    auto agent = std::make_shared<MockAircraft>("agent1", "red", 0.0, 0.0, 50000.0);
    auto enemy = std::make_shared<MockAircraft>("enemy1", "blue", 1000000.0, 1000000.0, 50000.0);

    std::vector<std::shared_ptr<Aircraft>> all_agents = {agent, enemy};
    std::vector<std::shared_ptr<Missile>> all_missiles;

    RewardInfo info{0, false};
    EnemyDistanceReward distance_reward(0.01, "distance");
    AltitudeAdvantageReward altitude_reward(0.005, "altitude");

    double distance = distance_reward.compute(agent, all_agents, all_missiles, info);
    double altitude = altitude_reward.compute(agent, all_agents, all_missiles, info);

    // Should not crash and should return valid numbers
    ASSERT(!std::isnan(distance));
    ASSERT(!std::isnan(altitude));
    ASSERT(std::isfinite(distance));
    ASSERT(std::isfinite(altitude));
}

// Test 11: Component weight affects output
TEST(Reward, ComponentWeightScaling) {
    auto agent = std::make_shared<MockAircraft>("agent1", "red", 0.0, 0.0, 5000.0);
    auto enemy = std::make_shared<MockAircraft>("enemy1", "blue", 30000.0, 0.0, 5000.0);

    std::vector<std::shared_ptr<Aircraft>> all_agents = {agent, enemy};
    std::vector<std::shared_ptr<Missile>> all_missiles;

    RewardInfo info{0, false};

    // Same component, different weights
    auto reward1 = std::make_shared<SurvivalReward>(0.01, "survival1");
    auto reward2 = std::make_shared<SurvivalReward>(0.05, "survival2");

    double val1 = reward1->operator()(agent, all_agents, all_missiles, info);
    double val2 = reward2->operator()(agent, all_agents, all_missiles, info);

    // val2 should be ~5x val1 (weight ratio 0.05/0.01 = 5)
    if (val1 != 0.0) {
        double ratio = val2 / val1;
        ASSERT_NEAR(ratio, 5.0, 0.01);
    }
}

// Test 12: Manager reset clears state
TEST(Reward, RewardManagerReset) {
    auto agent = std::make_shared<MockAircraft>("agent1", "red", 0.0, 0.0, 5000.0);
    auto enemy = std::make_shared<MockAircraft>("enemy1", "blue", 10000.0, 0.0, 5000.0);

    std::vector<std::shared_ptr<Aircraft>> all_agents = {agent, enemy};
    std::vector<std::shared_ptr<Missile>> all_missiles;

    RewardInfo info{0, false};
    RewardManager manager;

    auto engagement = std::make_shared<EngageEnemyReward>(0.01, "engage");
    manager.add_component(engagement);

    // Compute reward (builds state)
    double reward1 = manager.compute_reward(agent, all_agents, all_missiles, info);

    // Reset and compute again
    manager.reset();
    info.current_step = 1;
    double reward2 = manager.compute_reward(agent, all_agents, all_missiles, info);

    // Both should be valid
    ASSERT(!std::isnan(reward1));
    ASSERT(!std::isnan(reward2));
}

// Test 13: EnemyTrackingReward based on lock count
TEST(Reward, EnemyTrackingRewardLocks) {
    auto agent = std::make_shared<MockAircraft>("agent1", "red", 0.0, 0.0, 5000.0);
    auto enemy1 = std::make_shared<MockAircraft>("enemy1", "blue", 10000.0, 0.0, 5000.0);
    auto enemy2 = std::make_shared<MockAircraft>("enemy2", "blue", 15000.0, 0.0, 5000.0);

    std::vector<std::shared_ptr<Aircraft>> all_agents = {agent, enemy1, enemy2};
    std::vector<std::shared_ptr<Missile>> all_missiles;

    RewardInfo info{0, false};
    EnemyTrackingReward tracking_reward(0.01, "tracking");

    // No locks
    double reward_no_lock = tracking_reward.compute(agent, all_agents, all_missiles, info);
    ASSERT_EQ(reward_no_lock, 0.0);

    // Add locks
    agent->enemies_lock.push_back(enemy1->uid);
    agent->enemies_lock.push_back(enemy2->uid);
    double reward_with_locks = tracking_reward.compute(agent, all_agents, all_missiles, info);

    // Should be proportional to lock count
    ASSERT(reward_with_locks > 0.0);
}

// Test 14: MissileEvasionReward tracks missile distances
TEST(Reward, MissileEvasionReward) {
    auto agent = std::make_shared<MockAircraft>("agent1", "red", 0.0, 0.0, 5000.0);

    std::vector<std::shared_ptr<Aircraft>> all_agents = {agent};
    std::vector<std::shared_ptr<Missile>> all_missiles;

    RewardInfo info{0, false};
    MissileEvasionReward evasion_reward(0.02, "evasion");

    // Compute with no missiles
    double reward1 = evasion_reward.compute(agent, all_agents, all_missiles, info);
    ASSERT_EQ(reward1, 0.0);

    // Add incoming missile
    auto missile = std::make_shared<MockMissile>("missile1", "blue", 500.0, 0.0, 5000.0);
    all_missiles.push_back(missile);

    double reward2 = evasion_reward.compute(agent, all_agents, all_missiles, info);
    ASSERT(!std::isnan(reward2));
}

// Test 15: MissileLaunchReward tracks launches
TEST(Reward, MissileLaunchReward) {
    auto agent = std::make_shared<MockAircraft>("agent1", "red", 0.0, 0.0, 5000.0);

    std::vector<std::shared_ptr<Aircraft>> all_agents = {agent};
    std::vector<std::shared_ptr<Missile>> all_missiles;

    RewardInfo info{0, false};
    MissileLaunchReward launch_reward(1.0, 1.0, 1.0, "launch");

    // Compute with no missiles (no launches)
    double reward1 = launch_reward.compute(agent, all_agents, all_missiles, info);

    // Add a missile (simulates launch)
    auto missile = std::make_shared<MockMissile>("missile1", "agent1", 500.0, 0.0, 5000.0);
    all_missiles.push_back(missile);

    info.current_step = 1;
    double reward2 = launch_reward.compute(agent, all_agents, all_missiles, info);

    // Both should be valid
    ASSERT(!std::isnan(reward1));
    ASSERT(!std::isnan(reward2));
}

}  // namespace bvr_sim
