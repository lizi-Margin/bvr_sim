#include "test_main.hxx"
#include "simulator/param_store.hxx"
#include "support/interp_table.hxx"
#include <memory>
#include <cmath>

TEST(ParamStore, SetAndGetDouble) {
    bvr_sim::ParamStore ps;
    ps.set_double("mass", 161.48);
    auto v = ps.get_double("mass");
    ASSERT(v.has_value());
    ASSERT_NEAR(v.value(), 161.48, 1e-9);
    ASSERT_NEAR(ps.get_double_("mass"), 161.48, 1e-9);
}

TEST(ParamStore, SetAndGetString) {
    bvr_sim::ParamStore ps;
    ps.set_string("model", "AIM-120C");
    auto v = ps.get_string("model");
    ASSERT(v.has_value());
    ASSERT(v.value() == "AIM-120C");
    ASSERT(ps.get_string_("model") == "AIM-120C");
}

TEST(ParamStore, SetAndGetBool) {
    bvr_sim::ParamStore ps;
    ps.set_bool("enable_loft", true);
    auto v = ps.get_bool("enable_loft");
    ASSERT(v.has_value());
    ASSERT(v.value() == true);
    ASSERT(ps.get_bool_("enable_loft") == true);
}

TEST(ParamStore, MissingKeyReturnsNullopt) {
    bvr_sim::ParamStore ps;
    ASSERT(!ps.get_double("nonexistent").has_value());
    ASSERT(!ps.get_bool("nonexistent").has_value());
    ASSERT(!ps.get_string("nonexistent").has_value());
    ASSERT(!ps.get_interp_table("nonexistent").has_value());
}

TEST(ParamStore, TypeConflictThrows) {
    bvr_sim::ParamStore ps;
    ps.set_double("key", 1.0);
    bool threw = false;
    try { ps.set_string("key", "oops"); } catch (const std::exception&) { threw = true; }
    ASSERT(threw);
}

TEST(ParamStore, HasKey) {
    bvr_sim::ParamStore ps;
    ASSERT(!ps.has_key("x"));
    ps.set_double("x", 1.0);
    ASSERT(ps.has_key("x"));
    ASSERT(ps.get_key_type("x") == bvr_sim::ParamStore::ValueType::Double);
}

TEST(ParamStore, JsonRoundtripDoublesBoolsAndStrings) {
    bvr_sim::ParamStore ps;
    ps.set_double("m0", 161.48);
    ps.set_double("g", 9.81);
    ps.set_bool("enable_search", true);
    ps.set_string("model", "AIM-120C");

    std::string json_str = ps.to_string();
    auto ps2 = bvr_sim::ParamStore::from_string(json_str);

    ASSERT_NEAR(ps2.get_double("m0").value(), 161.48, 1e-9);
    ASSERT_NEAR(ps2.get_double("g").value(), 9.81, 1e-9);
    ASSERT(ps2.get_bool("enable_search").value() == true);
    ASSERT(ps2.get_string("model").value() == "AIM-120C");
}

TEST(ParamStore, JsonRoundtripInterpTable) {
    bvr_sim::ParamStore ps;
    ps.set_interp_table("cx", std::make_shared<InterpTable>(
        std::vector<double>{0.5, 1.0, 2.0},
        std::vector<double>{0.3, 0.6, 0.4}
    ));

    std::string json_str = ps.to_string();
    auto ps2 = bvr_sim::ParamStore::from_string(json_str);

    auto tbl = ps2.get_interp_table("cx");
    ASSERT(tbl.has_value());
    ASSERT_NEAR((*tbl)->interpolate(1.0), 0.6, 1e-9);
    ASSERT_NEAR(ps2.get_interp_table_("cx")->interpolate(1.0), 0.6, 1e-9);
}

TEST(ParamStore, JsonRoundtripIntegerValuesInJson) {
    // Integer-valued JSON numbers (no decimal point) must not abort
    std::string json_str = R"({"doubles": {"t_thrust": 8, "K": 3}, "strings": {}, "tables": {}})";
    auto ps = bvr_sim::ParamStore::from_string(json_str);
    ASSERT_NEAR(ps.get_double("t_thrust").value(), 8.0, 1e-9);
    ASSERT_NEAR(ps.get_double("K").value(), 3.0, 1e-9);
}

TEST(ParamStore, SetInterpTableNonNullWorks) {
    // Note: nullptr table would trigger check() -> abort(). Cannot test in-process.
    bvr_sim::ParamStore ps;
    ps.set_interp_table("cx", std::make_shared<InterpTable>(
        std::vector<double>{0.5, 1.0}, std::vector<double>{0.3, 0.6}
    ));
    ASSERT(ps.has_key("cx"));
    ASSERT(ps.get_key_type("cx") == bvr_sim::ParamStore::ValueType::InterpTable);
    ASSERT(ps.get_interp_table("cx").has_value());
    ASSERT(ps.get_interp_table_("cx") != nullptr);
}

TEST(ParamStore, KeyTypeForAllTypes) {
    bvr_sim::ParamStore ps;
    ps.set_double("d", 1.0);
    ps.set_bool("b", true);
    ps.set_string("s", "val");
    ps.set_interp_table("t", std::make_shared<InterpTable>(
        std::vector<double>{0.5, 1.0}, std::vector<double>{0.3, 0.6}
    ));
    ASSERT(ps.get_key_type("d") == bvr_sim::ParamStore::ValueType::Double);
    ASSERT(ps.get_key_type("b") == bvr_sim::ParamStore::ValueType::Bool);
    ASSERT(ps.get_key_type("s") == bvr_sim::ParamStore::ValueType::String);
    ASSERT(ps.get_key_type("t") == bvr_sim::ParamStore::ValueType::InterpTable);
    ASSERT(ps.get_key_type("nonexistent") == bvr_sim::ParamStore::ValueType::None);
}
