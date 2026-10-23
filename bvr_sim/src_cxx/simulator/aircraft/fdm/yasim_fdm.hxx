#pragma once
#include "ac_fdm.hxx"
#include <memory>
namespace bvr_sim {
// Upstream YASim solver + rigid-body integrator, hosted in process.
// Public coordinates: NWU metres/radians. Native coordinates: ECEF metres.
class YASimFDM final : public AircraftFDM {
    struct Impl;
    std::unique_ptr<Impl> impl;
    void read_state();
public:
    explicit YASimFDM(double dt, const std::string& xml_path);
    ~YASimFDM() override;
    void reset(const std::map<std::string, std::any>& state) override;
    void step(const ActionSpace& action) override;
    double property(const std::string& name) const;
    void set_property(const std::string& name, double value);
    std::map<std::string,double> visual_properties() const;
};
}
