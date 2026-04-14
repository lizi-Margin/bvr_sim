#include <iostream>
#include <string>
#include "simulator/pylon_manager.hxx"
#include "rubbish_can/SL.hxx"
#include "test_main.hxx"

// Test PylonManager::weapon_matches with exact match only
TEST(PylonManager, weapon_matches_ExactMatch) {
    bvr_sim::PylonManager pm;

    // Exact match should pass
    ASSERT(pm.weapon_matches("AIM-120C", "AIM-120C"));
    ASSERT(pm.weapon_matches("AIM-120C-MModelA", "AIM-120C-MModelA"));
    ASSERT(pm.weapon_matches("AIM-120C-MModelA-Poor", "AIM-120C-MModelA-Poor"));
    ASSERT(pm.weapon_matches("AIM-9M", "AIM-9M"));
    ASSERT(pm.weapon_matches_exact("AIM-120C", "AIM-120C"));
    ASSERT(pm.weapon_matches_exact("AIM-120C-MModelA", "AIM-120C-MModelA"));
    ASSERT(pm.weapon_matches_exact("AIM-120C-MModelA-Poor", "AIM-120C-MModelA-Poor"));
    ASSERT(pm.weapon_matches_exact("AIM-9M", "AIM-9M"));
}

TEST(PylonManager, weapon_matches_PrefixMatch_Fail) {
    bvr_sim::PylonManager pm;

    // Prefix match should pass for prefix matching
    ASSERT(pm.weapon_matches("AIM-120C-MModelA", "AIM-120C"));
    ASSERT(pm.weapon_matches("AIM-120C-MModelA-Poor", "AIM-120C"));
    ASSERT(pm.weapon_matches("AIM-120C7", "AIM-120C"));
    ASSERT(!pm.weapon_matches_exact("AIM-120C-MModelA", "AIM-120C"));
    ASSERT(!pm.weapon_matches_exact("AIM-120C-MModelA-Poor", "AIM-120C"));
    ASSERT(!pm.weapon_matches_exact("AIM-120C7", "AIM-120C"));
}

TEST(PylonManager, weapon_matches_DifferentWeapon) {
    bvr_sim::PylonManager pm;

    // Different weapons should not match
    ASSERT(!pm.weapon_matches("AIM-9M", "AIM-120C"));
    ASSERT(!pm.weapon_matches("AIM-120C", "AIM-9M"));
}

TEST(PylonManager, weapon_matches_Empty) {
    bvr_sim::PylonManager pm;

    ASSERT(pm.weapon_matches("AIM-120C", ""));
    ASSERT(pm.weapon_matches("AIM-120", ""));
    ASSERT(pm.weapon_matches("AIM", ""));
    ASSERT(pm.weapon_matches("GBU-57", ""));
    ASSERT(pm.weapon_matches("GBU", ""));
    ASSERT(pm.weapon_matches_exact("AIM-120C", ""));
    ASSERT(pm.weapon_matches_exact("GBU-57", ""));
}

TEST(PylonManager, weapon_matches_LargerQuery) {
    bvr_sim::PylonManager pm;
    ASSERT(!pm.weapon_matches("AIM-120C", "AIM-120C-MModelA"));
    ASSERT(!pm.weapon_matches_exact("AIM-120C", "AIM-120C-MModelA"));
}

TEST(PylonManager, weapon_count_exact) {
    bvr_sim::PylonManager pm;
    SL::init_instance("test_pylon_manager.log", false);
    pm.add_weapon("p1", "AIM-120C");
    pm.add_weapon("p2", "AIM-120C7");
    pm.add_weapon("p3", "AIM-120C");
    pm.add_weapon("p4", "AIM-9M");
    pm.freeze();

    ASSERT_EQ(pm.num_left_weapons(""), 4);
    ASSERT_EQ(pm.num_left_weapons("AIM-120C"), 3);
    ASSERT_EQ(pm.num_left_weapons_exact(""), 4);
    ASSERT_EQ(pm.num_left_weapons_exact("AIM-120C"), 2);
    ASSERT_EQ(pm.num_left_weapons_exact("AIM-120C7"), 1);
    ASSERT_EQ(pm.num_frozen_weapons("AIM-120C"), 3);
    ASSERT_EQ(pm.num_frozen_weapons_exact("AIM-120C"), 2);
    ASSERT_EQ(pm.num_frozen_weapons_exact("AIM-120C7"), 1);
}
