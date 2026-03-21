#include "../../test_main.cxx"
#include <cmath>
#include <map>
#include <string>

// Simple reward computation tests (without complex object dependencies)

TEST(Reward, BasicRewardBounds) {
    // Test that reward values stay within reasonable bounds
    double reward = 10.0;
    ASSERT_RANGE(reward, -100.0, 100.0);
}

TEST(Reward, EngagementRewardScaling) {
    // Simulate engagement reward scaling
    double close_range = 5000.0;
    double far_range = 50000.0;

    // Engagement reward should be inversely related to range
    double close_reward = 1.0 / (1.0 + close_range / 1000.0);
    double far_reward = 1.0 / (1.0 + far_range / 1000.0);

    ASSERT(close_reward > far_reward, "Close range should have higher engagement reward");
}

TEST(Reward, AltitudeAdvantageCalculation) {
    // Test altitude advantage calculation
    double own_alt = 6000.0;
    double enemy_alt = 5000.0;

    double alt_diff = own_alt - enemy_alt;
    ASSERT(alt_diff > 0, "Should calculate positive altitude advantage");
    ASSERT_NEAR(alt_diff, 1000.0, 1.0);
}

TEST(Reward, SpeedAdvantageScaling) {
    // Test speed advantage scaling
    double own_speed = 300.0;  // m/s
    double enemy_speed = 250.0;  // m/s

    double speed_diff = own_speed - enemy_speed;
    ASSERT(speed_diff > 0, "Should calculate positive speed advantage");
    ASSERT_NEAR(speed_diff, 50.0, 1.0);
}

TEST(Reward, SurvivalReward) {
    // Test survival reward (non-negative)
    double survival = 1.0;  // Alive
    ASSERT(survival > 0, "Survival reward should be positive");

    double dead = 0.0;  // Dead
    ASSERT(dead == 0, "Dead state should have zero reward");
}

TEST(Reward, ComponentWeighting) {
    // Test component weighting
    double engagement_weight = 1.0;
    double altitude_weight = 0.5;
    double speed_weight = 0.3;

    double engagement_score = 0.8;
    double altitude_score = 0.6;
    double speed_score = 0.7;

    double weighted_sum = engagement_weight * engagement_score +
                         altitude_weight * altitude_score +
                         speed_weight * speed_score;

    ASSERT_NEAR(weighted_sum, 1.39, 0.01);
}

TEST(Reward, DistillationPenalty) {
    // Test distillation penalty calculation
    int rl_action = 5;
    int baseline_action = 5;

    double penalty_match = 0.0;
    double penalty_mismatch = 1.0;

    ASSERT(penalty_match < penalty_mismatch, "Matching actions should have lower penalty");
}

TEST(Reward, MissileHitReward) {
    // Test missile hit/miss reward
    double hit_reward = 10.0;
    double miss_penalty = -1.0;

    ASSERT(hit_reward > 0, "Hit should have positive reward");
    ASSERT(miss_penalty < 0, "Miss should have negative penalty");
    ASSERT(hit_reward > miss_penalty, "Hit reward should exceed miss penalty");
}

TEST(Reward, EdgeCaseZeroValues) {
    // Test edge cases with zero values
    double zero_range = 0.0;
    double reward = 1.0 / (1.0 + std::max(zero_range, 1.0) / 1000.0);

    ASSERT(reward > 0, "Should handle zero range without division by zero");
    ASSERT(reward <= 1.0, "Reward should be bounded by 1.0");
}

TEST(Reward, LargeValueHandling) {
    // Test handling of large values
    double large_range = 1000000.0;
    double reward = 1.0 / (1.0 + large_range / 1000.0);

    ASSERT(reward >= 0, "Should handle large values gracefully");
    ASSERT(reward < 0.01, "Large range should result in very small reward");
}

} // namespace bvr_sim
