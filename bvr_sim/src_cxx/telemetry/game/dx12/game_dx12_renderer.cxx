#include "../game_renderer.hxx"

#include <cassert>
#include <memory>

namespace bvr_sim {

namespace {

class DX12Renderer : public IRenderer {
public:
    bool initialize(std::string&) override { assert(false && "DX12 not implemented"); return false; }
    void destroy() override { assert(false && "DX12 not implemented"); }
    bool process_messages() override { assert(false && "DX12 not implemented"); return false; }
    void apply_camera_state(const RendererCameraState&) override { assert(false && "DX12 not implemented"); }
    RendererCameraState get_camera_state() const override { assert(false && "DX12 not implemented"); return {}; }
    void update_input(const WorldSnapshot*, float) override { assert(false && "DX12 not implemented"); }
    bool render_frame(const RendererFrameInput&, RendererFrameStats&) override { assert(false && "DX12 not implemented"); return false; }
    bool is_window_closed() const override { assert(false && "DX12 not implemented"); return true; }
    bool get_shadows_enabled() const override { assert(false && "DX12 not implemented"); return false; }
    bool get_material_system_enabled() const override { assert(false && "DX12 not implemented"); return false; }
    void set_command_submitter(std::function<void(const TelemetryCommand&)>) override { assert(false && "DX12 not implemented"); }
};

} // namespace

std::unique_ptr<IRenderer> create_dx12_renderer() {
    return std::make_unique<DX12Renderer>();
}

} // namespace bvr_sim
