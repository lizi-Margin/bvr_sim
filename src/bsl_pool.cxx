#include "bsl_pool.hxx"
#include "rubbish_can/SL.hxx"
#include "rubbish_can/check.hxx"
#include "so_pool.hxx"
#include <iostream>
#include <algorithm>

namespace bvr_sim {

BaselinePool& BaselinePool::instance() {
    static BaselinePool pool;
    return pool;
}

void BaselinePool::add(std::shared_ptr<Aircraft> unit, std::shared_ptr<BaseOpponent3D> bsl) {
    if (!bsl || !unit) {
        return;
    }
    std::unique_lock lock(mutex_);
    for (const auto& [u, b] : baselines) {
        if (u->uid == unit->uid) {
            SL::get().printf("BaselinePool::add: unit %s already has a baseline", unit->uid.c_str());
            return;
        }
    }
    baselines.push_back({unit, bsl});
}

void BaselinePool::remove(const std::string& uid) {
    std::unique_lock lock(mutex_);
    _remove(uid);
}

void BaselinePool::_remove(const std::string& uid) {
    baselines.erase(std::remove_if(baselines.begin(), baselines.end(),
                    [&uid](const auto& pair) { return pair.first->uid == uid; }),
                    baselines.end());
}

void BaselinePool::clear() {
    std::unique_lock lock(mutex_);
    baselines.clear();
}

bool BaselinePool::has(const std::string& uid) const {
    std::shared_lock lock(mutex_);
    return std::any_of(baselines.begin(), baselines.end(),
                        [&uid](const auto& pair) { return pair.first->uid == uid; });
}

void BaselinePool::step() {
    std::unique_lock lock(mutex_);
    baselines.erase(std::remove_if(baselines.begin(), baselines.end(),
                    [](const auto& pair) { return !pair.first->is_alive; }),
                    baselines.end());

    
    baselines.erase(std::remove_if(baselines.begin(), baselines.end(),
                    [](const auto& pair) { return !SOPool::instance().has(pair.first->uid); }),
                    baselines.end());
    
    for (const auto& [unit, bsl] : baselines) {
        bsl->take_action(unit, unit->enemies, unit->partners, unit->under_missiles);
    }
}


size_t BaselinePool::size() const {
    std::shared_lock lock(mutex_);
    return baselines.size();
}

std::optional<json::JSON> BaselinePool::get_action_cache(const std::string& uid) const {
    std::shared_lock lock(mutex_);
    auto it = std::find_if(baselines.begin(), baselines.end(),
                            [&uid](const auto& pair) { return pair.first->uid == uid; });
    if (it == baselines.end()) {
        SL::get().printf("BaselinePool::get_action_cache: unit %s not found", uid.c_str());
        // std::printf("BaselinePool::get_action_cache: unit %s not found", uid.c_str());
        return std::nullopt;
    }
    auto res =  it->second->get_action_cache();
    return res;
}


}