#include <iostream>
#include <string>
#include "simulator/pylon_manager.hxx"
#include "test_main.hxx"

// Test PylonManager::weapon_matches with exact match only
TEST(PylonManager, weapon_matches_ExactMatch) {
    bvr_sim::PylonManager pm;

    // Exact match should pass
    ASSERT(pm.weapon_matches("AIM-120C", "AIM-120C"));
    ASSERT(pm.weapon_matches("AIM-120C-MModelA", "AIM-120C-MModelA"));
    ASSERT(pm.weapon_matches("AIM-120C-MModelA-Poor", "AIM-120C-MModelA-Poor"));
    ASSERT(pm.weapon_matches("AIM-9M", "AIM-9M"));
}

TEST(PylonManager, weapon_matches_PrefixMatch_Fail) {
    bvr_sim::PylonManager pm;

    // Prefix match should fail with exact match only
    ASSERT(pm.weapon_matches("AIM-120C-MModelA", "AIM-120C"));
    ASSERT(pm.weapon_matches("AIM-120C-MModelA-Poor", "AIM-120C"));
    ASSERT(pm.weapon_matches("AIM-120C7", "AIM-120C"));
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
}

TEST(PylonManager, weapon_matches_LargerQuery) {
    bvr_sim::PylonManager pm;
    ASSERT(!pm.weapon_matches("AIM-120C", "AIM-120C-MModelA"));
}

