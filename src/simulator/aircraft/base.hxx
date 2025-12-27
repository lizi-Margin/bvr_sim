#pragma once

#include "../simulator.hxx"
#include "simulator/sense/base.hxx"
#include "simulator/pylon_manager.hxx"
#include "rubbish_can/check.hxx"
#include <string>
#include <array>
#include <vector>
#include <map>
#include <memory>

namespace bvr_sim {

class Missile;
class SensorBase;
class PylonManager;

class Aircraft : public SimulatedObject {
public:
    std::string aircraft_model;

    double bloods;
    bool sensed;

    std::vector<std::shared_ptr<Aircraft>> enemies_lock;

    std::vector<std::shared_ptr<Missile>> launched_missiles;
    std::vector<std::shared_ptr<Missile>> under_missiles;

    std::shared_ptr<SensorBase> radar;
    std::shared_ptr<SensorBase> rws;
    std::shared_ptr<SensorBase> mws;
    std::shared_ptr<SensorBase> sa_datalink;

    PylonManager pylon_manager;

protected:
    std::map<std::string, std::shared_ptr<SensorBase>> sensors;

public:
    Aircraft(
        const std::string& uid_,
        const std::string& model,
        TeamColor color_,
        const std::array<double, 3>& position_,
        const std::array<double, 3>& velocity_,
        double dt_ = 0.1
    ) noexcept;

    virtual ~Aircraft() noexcept = default;

    virtual bool can_shoot() const noexcept;

    virtual bool can_shoot_enm(const std::shared_ptr<SimulatedObject>& enemy) const noexcept;

    virtual bool shoot(
        const std::string& missile_spec,
        const std::string& target_uid
    ) noexcept;

    void add_sensor(const std::string& name, const std::shared_ptr<SensorBase>& sensor);
    void update_sensors() noexcept;

    virtual double get_roll() const noexcept;
    virtual double get_pitch() const noexcept;

    virtual void step() override;

    virtual void hit(double damage = -1.0) noexcept;

    std::string log() noexcept override;

    const std::map<std::string, std::shared_ptr<SensorBase>>& get_sensors() const noexcept { return sensors; }


    virtual void write_register() noexcept override;

    virtual void clean_up() noexcept override {
        SimulatedObject::clean_up();
        enemies_lock.clear();
        launched_missiles.clear();
        under_missiles.clear();
        for (auto& [name, sensor] : sensors) {
            check(sensor, "sensor");
            sensor->clean_up();
        }
        sensors.clear();
        sa_datalink = nullptr;
        radar = nullptr;
        rws = nullptr;
        mws = nullptr;
    }

protected:
    void maintain_missile_lists() noexcept;


    bool is_compass_action(const std::map<std::string, double>& action) const noexcept;

    bool is_physics_action(const std::map<std::string, double>& action) const noexcept;

    double normalize_angle(double angle) const noexcept;
};

}
