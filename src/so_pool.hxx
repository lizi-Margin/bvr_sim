#pragma once

#include "simulator/simulator.hxx"
#include <string>
#include <map>
#include <vector>
#include <memory>
#include <shared_mutex>
#include <optional>

namespace bvr_sim {

class SOPool {
public:
    static SOPool& instance();

    SOPool(const SOPool&) = delete;
    SOPool& operator=(const SOPool&) = delete;

    void add(std::shared_ptr<SimulatedObject> obj);
    void trash_out(const std::string& uid);
    void clear();

protected:
    void check_and_fix();
    // std::vector<std::shared_ptr<SimulatedObject>> _get_by_color(TeamColor color) const;

public: // const methods
    std::shared_ptr<SimulatedObject> get(const std::string& uid) const;
    bool has(const std::string& uid) const;

    std::vector<std::shared_ptr<SimulatedObject>> get_all() const;
    std::vector<std::shared_ptr<SimulatedObject>> get_by_type(SOT type) const;
    static std::vector<std::shared_ptr<SimulatedObject>> get_by_type(const std::map<std::string, std::shared_ptr<SimulatedObject>>& objects, SOT type);
    static std::vector<std::shared_ptr<SimulatedObject>> get_by_type(const std::vector<std::shared_ptr<SimulatedObject>>& objects, SOT type);
    std::vector<std::shared_ptr<SimulatedObject>> get_by_color(TeamColor color) const;
    static std::vector<std::shared_ptr<SimulatedObject>> get_by_color(const std::map<std::string, std::shared_ptr<SimulatedObject>>& objects, TeamColor color);
    static std::vector<std::shared_ptr<SimulatedObject>> get_by_color(const std::vector<std::shared_ptr<SimulatedObject>>& objects, TeamColor color);

    size_t size() const;


public:
    bool in_trash_bin(const std::string& uid) const;
    std::vector<std::shared_ptr<SimulatedObject>> get_all_ever_existed() const;
    // std::shared_ptr<SimulatedObject> get_from_trash_bin(const std::string& uid) const;

private:
    SOPool() = default;

    std::map<std::string, std::shared_ptr<SimulatedObject>> objects_;
    std::map<std::string, std::shared_ptr<SimulatedObject>> trashed_objects_;
    mutable std::shared_mutex mutex_;
};

}
