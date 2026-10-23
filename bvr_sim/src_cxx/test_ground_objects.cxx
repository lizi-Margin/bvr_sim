#include "test_main.hxx"
#include "simulator/environment.hxx"
#include "simulator/bomb/mk82.hxx"
#include "simulator/ground/vehicle.hxx"
#include "simulator/ground/ground_static_target.hxx"
#include "simulator/ground/aa.hxx"
#include "simulator/missile/base.hxx"
#include "so_pool.hxx"
#include "support/SL.hxx"

using namespace bvr_sim;
namespace {
struct CoreFixture {
    CoreFixture() {
        SL::init_instance("core-object-tests.log", false);
        SOPool::instance().clear();
    }
    ~CoreFixture() {
        SOPool::instance().clear();
        SL::shutdown();
    }
};
std::shared_ptr<Terrain> flat_environment() {
    auto t = std::make_shared<Terrain>();
    t->origin_north = -1000;
    t->origin_west = -1000;
    t->spacing = 2000;
    return t;
}
struct Launcher : SimulatedObject {
    Launcher(std::array<double, 3> p, std::array<double, 3> v)
        : SimulatedObject("launcher", TeamColor::Blue, p, v, .02, SOT::Aircraft) {}
    void step() override {}
    std::string log() noexcept override { return {}; }
};
ContactSurface rectangle(std::string id, double n0, double n1, double w0, double w1, double z) {
    ContactSurface s;
    s.id = id;
    s.vertices = {{n0, w0, z}, {n1, w0, z}, {n0, w1, z}, {n1, w1, z}};
    s.indices = {0, 1, 2, 1, 3, 2};
    s.prepare();
    return s;
}
} // namespace
TEST(CoreLifecycle, GroundLauncherResetReleasesMissileOwnershipCycle) {
    CoreFixture fixture;
    struct TestMissile : Missile {
        TestMissile(std::shared_ptr<SimulatedObject> parent)
            : Missile("test_missile", "test", TeamColor::Red, parent, nullptr, nullptr, .02) {}
        void step() override {}
    };
    std::weak_ptr<AA> weak_launcher;
    std::weak_ptr<Missile> weak_missile;
    {
        auto launcher=std::make_shared<AA>("launcher","test",TeamColor::Red,std::array<double,3>{0,0,0},.02,2);
        auto missile=std::make_shared<TestMissile>(launcher);
        launcher->shoot(missile);
        SOPool::instance().add(launcher);SOPool::instance().add(missile);
        weak_launcher=launcher;weak_missile=missile;
    }
    ASSERT(!weak_launcher.expired());ASSERT(!weak_missile.expired());
    SOPool::instance().clear();
    ASSERT(weak_launcher.expired());ASSERT(weak_missile.expired());
}
TEST(CoreBomb, PredictReleaseImpactDamageAndReclamationWithoutGameSession) {
    CoreFixture fixture;
    SOPool::instance().clear();
    auto terrain = flat_environment();
    Launcher launcher({0, 0, 1000}, {230, 0, 0});
    auto predicted = predict_ballistic_impact(launcher.position, launcher.velocity, *terrain, .02);
    ASSERT(predicted.has_value());
    auto target = std::make_shared<GroundStaticTarget>("target", TeamColor::Red, *predicted, .02);
    auto bomb = std::make_shared<Mk82Bomb>("mk82", launcher, terrain, .02);
    SOPool::instance().add(target);
    SOPool::instance().add(bomb);
    for (int i = 0; i < 6000 && bomb->is_alive; ++i)
        bomb->tick();
    ASSERT(bomb->impacted);
    ASSERT(!bomb->is_alive);
    ASSERT(!target->is_alive);
    ASSERT(std::hypot(bomb->position[0] - (*predicted)[0], bomb->position[1] - (*predicted)[1]) < 5);
    auto position = bomb->position;
    for (int i = 0; i < 21; ++i)
        bomb->tick();
    ASSERT(bomb->trashed());
    ASSERT(bomb->position == position);
    SOPool::instance().trash_out(bomb->uid);
    ASSERT(!SOPool::instance().get(bomb->uid));
    SOPool::instance().clear();
}
TEST(CoreSurface, BridgeAboveWaterIsIndependentOfRiverbed) {
    CoreFixture fixture;
    auto t = flat_environment();
    t->water_regions.push_back({"river", {{-50, -100}, {50, -100}, {50, 100}, {-50, 100}}});
    t->contact_surfaces.push_back(rectangle("bridge", -60, 60, -5, 5, 10));
    t->prepare_surfaces();
    ASSERT_NEAR(t->height(0, 0), 0, 1e-9);
    ASSERT_NEAR(t->collision_height(0, 0), 10, 1e-9);
    auto deck = t->contact(0, 0, 0, 10);
    ASSERT(deck.supported);
    ASSERT(!deck.water);
    ASSERT_NEAR(deck.height, 10, 1e-9);
    auto underneath = t->contact(0, 0, 0, 0);
    ASSERT(underneath.water);
    ASSERT_NEAR(underneath.height, 0, 1e-9);
    Launcher launcher({0, 0, 100}, {0, 0, -5});
    Mk82Bomb bomb("bridge_hit", launcher, t, .02);
    for (int i = 0; i < 5000 && bomb.is_alive; ++i)
        bomb.tick();
    ASSERT(bomb.impacted);
    ASSERT_NEAR(bomb.position[2], 10, 1e-5);
}
TEST(CoreVehicle, RouteTurnParkResumeDamageResetDeterminism) {
    CoreFixture fixture;
    SOPool::instance().clear();
    auto t = flat_environment();
    auto run = [&]() {
        GroundVehicle car("car", "WillysJeep", TeamColor::Red, {0, 0, 0}, t);
        car.set_route({{{0, 0}, {60, 0}, {60, 50}}, 5, false});
        for (int i = 0; i < 400; ++i)
            car.tick();
        ASSERT(car.position[0] > 20);
        car.set_parking(true);
        auto begin = car.position;
        for (int i = 0; i < 150; ++i)
            car.tick();
        ASSERT(car.get_speed() < .01);
        auto parked = car.position;
        for (int i = 0; i < 100; ++i)
            car.tick();
        ASSERT(car.position == parked);
        ASSERT(parked[0] >= begin[0]);
        car.set_parking(false);
        for (int i = 0; i < 1800; ++i)
            car.tick();
        ASSERT(car.position[1] > 35);
        ASSERT(car.motion == "arrived");
        ASSERT_NEAR(car.position[2], 0, 1e-9);
        auto result = car.position;
        car.hit(30);
        ASSERT_NEAR(car.health(), 70, 1e-9);
        car.hit();
        for (int i = 0; i < 21; ++i)
            car.tick();
        ASSERT(!car.is_alive);
        ASSERT(car.trashed());
        car.reset();
        ASSERT(car.is_alive);
        ASSERT_NEAR(car.health(), 100, 1e-9);
        ASSERT_NEAR(car.position[0], 0, 1e-9);
        return result;
    };
    auto a = run(), b = run();
    ASSERT(a == b);
    SOPool::instance().clear();
}
TEST(CoreVehicle, RejectsWaterObstacleAndSteepTerrain) {
    CoreFixture fixture;
    auto t = flat_environment();
    t->water_regions.push_back({"water", {{15, -50}, {40, -50}, {40, 50}, {15, 50}}});
    GroundVehicle car("car", "WillysJeep", TeamColor::Red, {0, 0, 0}, t);
    car.set_route({{{50, 0}}, 5, false});
    for (int i = 0; i < 500; ++i)
        car.tick();
    ASSERT(car.blocked_reason == "water");
    ASSERT(car.position[0] < 15);
    t->water_regions.clear();
    t->obstacles.push_back({"wall", {20, 0, 2}, {2, 10, 2}, 0});
    car.reset();
    car.set_route({{{50, 0}}, 5, false});
    for (int i = 0; i < 500; ++i)
        car.tick();
    ASSERT(car.blocked_reason == "obstacle");
    ASSERT(car.position[0] < 17);
    t->obstacles.clear();
    t->origin_north = 0;
    t->origin_west = -100;
    t->spacing = 100;
    t->heights = {0, 100, 0, 100};
    car.reset();
    car.set_route({{{50, 0}}, 5, false});
    for (int i = 0; i < 100; ++i)
        car.tick();
    ASSERT(car.blocked_reason == "slope");
}

TEST(CoreVehicle, DrivesOverElevatedBridgeWithoutEnteringRiverbed) {
    CoreFixture fixture;
    auto t = flat_environment();
    t->water_regions.push_back({"river", {{-10, -50}, {10, -50}, {10, 50}, {-10, 50}}});
    auto s = rectangle("bridge_with_ramps", -30, 30, -5, 5, 0);
    s.vertices = {{-30, -5, 0}, {-30, 5, 0}, {-10, -5, 3}, {-10, 5, 3},
                  {10, -5, 3},  {10, 5, 3},  {30, -5, 0},  {30, 5, 0}};
    s.indices = {0, 2, 1, 1, 2, 3, 2, 4, 3, 3, 4, 5, 4, 6, 5, 5, 6, 7};
    t->contact_surfaces.push_back(s);
    t->prepare_surfaces();
    GroundVehicle car("crossing", "WillysJeep", TeamColor::Red, {-50, 0, 0}, t);
    car.set_route({{{50, 0}}, 4, false});
    double highest = 0;
    for (int i = 0; i < 2000; ++i) {
        car.tick();
        highest = std::max(highest, car.position[2]);
        ASSERT(car.blocked_reason.empty());
    }
    ASSERT(car.position[0] > 48);
    ASSERT_NEAR(highest, 3, 1e-6);
    ASSERT_NEAR(car.position[2], 0, 1e-6);
}
