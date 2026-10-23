// No window or graphics-library dependency in the simulation-only build.
#include "game/game_mode.hxx"
#include "opengl_viewer.hxx"
namespace bvr_sim {
#define VIEWER_STUB(T)                                                                                       \
    T::T() : running_(false), stop_requested_(false), supported_(false) {}                                   \
    T::~T() = default;                                                                                       \
    void T::set_snapshot_provider(std::function<std::shared_ptr<const WorldSnapshot>()> p) {                 \
        snapshot_provider_ = std::move(p);                                                                   \
    }                                                                                                        \
    void T::set_command_submitter(std::function<void(const TelemetryCommand &)> p) {                         \
        command_submitter_ = std::move(p);                                                                   \
    }                                                                                                        \
    void T::start() { last_error_ = "Native viewers disabled at build time"; }                               \
    void T::stop() noexcept {}                                                                               \
    bool T::is_running() const noexcept { return false; }                                                    \
    bool T::is_supported() const noexcept { return false; }                                                  \
    json::JSON T::get_status() const {                                                                       \
        auto j = json::Object();                                                                             \
        j["supported"] = json::Boolean(false);                                                               \
        j["running"] = json::Boolean(false);                                                                 \
        j["backend"] = json::String("disabled");                                                             \
        j["last_error"] = json::String(last_error_);                                                         \
        return j;                                                                                            \
    }                                                                                                        \
    void T::submit_command(const TelemetryCommand &c) const {                                                \
        if (command_submitter_)                                                                              \
            command_submitter_(c);                                                                           \
    }
VIEWER_STUB(OpenGLViewer)
VIEWER_STUB(GameMode)
void GameMode::queue_viewer_command(const TelemetryCommand &) {}
#undef VIEWER_STUB
} // namespace bvr_sim
