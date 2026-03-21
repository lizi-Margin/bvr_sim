#pragma once

#include "simulator/aircraft/base.hxx"
#include "baseline_opponents/base.hxx"
#include <string>
#include <map>
#include <vector>
#include <memory>
#include <shared_mutex>
#include <optional>

namespace bvr_sim {

class BaselinePool {
public:
    static BaselinePool& instance();

    BaselinePool(const BaselinePool&) = delete;
    BaselinePool& operator=(const BaselinePool&) = delete;

    void add(std::shared_ptr<Aircraft> unit, std::shared_ptr<BaseOpponent3D> bsl);
    void remove(const std::string& uid);
    void clear();
    void step();

public: // const methods
    bool has(const std::string& uid) const;
    size_t size() const;
    std::optional<json::JSON> get_action_cache(const std::string& uid) const;

private:
    BaselinePool() = default;
    void _remove(const std::string& uid);

    std::vector<std::pair<std::shared_ptr<Aircraft>, std::shared_ptr<BaseOpponent3D>>> baselines;
    mutable std::shared_mutex mutex_;
};

}
