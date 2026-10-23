#pragma once
// Optional presentation-only audio. Only immutable GameFrame enters this class.
class AudioPresenter {
    struct Voice {
        wi::audio::Sound sound;
        wi::audio::SoundInstance instance;
    };
    std::map<std::string, Voice> voices;
    std::set<std::pair<uint64_t, std::string>> played;
    uint64_t previous_tick = 0;
    double search_time = -10, warning_time = -10;
    bool enabled = false;

  public:
    std::map<std::string, uint64_t> counts;
    std::map<std::string, bool> available;
    void configure(const std::map<std::string, std::string> &paths, bool on) {
        stop();
        enabled = on;
        for (auto &[id, file] : paths) {
            auto &v = voices[id];
            if (!std::filesystem::exists(file))
                throw std::runtime_error("Missing registered audio: " + file);
            if (id == "engine")
                v.instance.SetLooped(true);
            available[id] = wi::audio::CreateSound(file, &v.sound) &&
                            wi::audio::CreateSoundInstance(&v.sound, &v.instance);
        }
        if (enabled && available["engine"]) {
            wi::audio::SetVolume(0, &voices["engine"].instance);
            wi::audio::Play(&voices["engine"].instance);
        }
    }
    void play(const std::string &id, float volume = .25f) {
        if (enabled && available[id]) {
            auto &instance = voices[id].instance;
            wi::audio::Stop(&instance);
            wi::audio::SetVolume(volume, &instance);
            wi::audio::Play(&instance);
            counts[id]++;
        }
    }
    void update(const bvr_sim::GameFrame &frame, bool hangar) {
        if (frame.tick < previous_tick) {
            played.clear();
            search_time = warning_time = -10;
        }
        previous_tick = frame.tick;
        if (enabled && available["engine"]) {
            float thrust = 0;
            for (auto &e : frame.entities)
                if (e.uid == "player" && e.alive)
                    thrust = float(e.throttle);
            wi::audio::SetVolume(hangar || frame.paused ? 0 : .08f + .2f * thrust,
                                 &voices["engine"].instance);
        }
        if (hangar || frame.paused)
            return;
        if (frame.rwr_mode != "quiet" &&
            frame.sim_time - warning_time > (frame.rwr_mode == "missile" ? .4 : 1.2)) {
            play("rwr");
            warning_time = frame.sim_time;
        }
        if (frame.radar_mode == "RWS" && frame.sim_time - search_time > 2) {
            play("search", .1f);
            search_time = frame.sim_time;
        }
        for (const auto &event : frame.events)
            if (played.insert({event.tick, event.kind + event.actor + event.weapon}).second) {
                if (event.kind == "target_locked")
                    play("lock");
                else if (event.kind == "missile_launched" || event.kind == "bomb_released")
                    play("launch");
                else if (event.kind == "missile_hit" || event.kind == "bomb_impact")
                    play("explosion", .35f);
                else if (event.kind == "mission_succeeded" || event.kind == "mission_failed")
                    play("result");
            }
    }
    void stop() {
        for (auto &[id, v] : voices)
            if (v.instance.IsValid())
                wi::audio::Stop(&v.instance);
        voices.clear();
    }
    ~AudioPresenter() { stop(); }
};
