#include "game_dx11_internal.hxx"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <mutex>
#include <sstream>
#include <string>

namespace bvr_sim {

#ifdef _WIN32

namespace {

Float3 make_float3(float x, float y, float z) {
    Float3 v;
    v.x = x;
    v.y = y;
    v.z = z;
    return v;
}

Float3 add(const Float3& a, const Float3& b) {
    return make_float3(a.x + b.x, a.y + b.y, a.z + b.z);
}

Float3 scale(const Float3& v, float s) {
    return make_float3(v.x * s, v.y * s, v.z * s);
}

float normalize_mouse_axis(int value, int extent_minus_one) {
    if (extent_minus_one <= 0) {
        return 0.0f;
    }
    const float t = static_cast<float>(value) / static_cast<float>(extent_minus_one);
    const float normalized = (t * 2.0f) - 1.0f;
    return std::clamp(normalized, -1.0f, 1.0f);
}

void cycle_follow_target(ViewerInputState& input) {
    const int object_count = static_cast<int>(input.snapshot_uids.size());
    if (object_count <= 0) {
        input.focus_cycle_index = -1;
    } else {
        const int slot_count = object_count + 1; // object slots + one free slot
        int next_index = input.focus_cycle_index + 1;
        if (next_index >= slot_count) {
            next_index = -1;
        }
        input.focus_cycle_index = next_index;
    }

    if (input.focus_cycle_index < 0 || input.focus_cycle_index >= object_count) {
        input.focus_uid.clear();
        input.camera_mode = ViewerInputState::CameraMode::Free;
    } else {
        input.focus_uid = input.snapshot_uids[static_cast<size_t>(input.focus_cycle_index)];
        input.camera_mode = ViewerInputState::CameraMode::FollowObject;
    }
}

void flush_desktop_composition() {
    GdiFlush();
    using DwmFlushFn = HRESULT(WINAPI*)();
    static DwmFlushFn dwm_flush = []() -> DwmFlushFn {
        HMODULE dwmapi = LoadLibraryA("dwmapi.dll");
        if (!dwmapi) {
            return nullptr;
        }
        return reinterpret_cast<DwmFlushFn>(GetProcAddress(dwmapi, "DwmFlush"));
    }();
    if (dwm_flush) {
        dwm_flush();
    }
}

HFONT get_hud_font() {
    static std::once_flag init_flag;
    static HFONT font = nullptr;
    std::call_once(init_flag, []() {
        font = CreateFontA(
            -18,
            0,
            0,
            0,
            FW_MEDIUM,
            FALSE,
            FALSE,
            FALSE,
            ANSI_CHARSET,
            OUT_TT_PRECIS,
            CLIP_DEFAULT_PRECIS,
            ANTIALIASED_QUALITY,
            FF_DONTCARE | DEFAULT_PITCH,
            "Consolas"
        );
    });
    return font;
}

LRESULT CALLBACK dx11_window_proc(HWND hwnd, UINT msg, WPARAM w_param, LPARAM l_param) {
    Win32Window* window = reinterpret_cast<Win32Window*>(GetWindowLongPtr(hwnd, GWLP_USERDATA));
    switch (msg) {
    case WM_NCCREATE: {
        CREATESTRUCT* create_struct = reinterpret_cast<CREATESTRUCT*>(l_param);
        SetWindowLongPtr(hwnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(create_struct->lpCreateParams));
        return TRUE;
    }
    case WM_CLOSE:
        DestroyWindow(hwnd);
        return 0;
    case WM_DESTROY:
        PostQuitMessage(0);
        return 0;
    case WM_LBUTTONDOWN:
        if (window) {
            window->input.dragging = true;
            window->input.last_mouse_x = GET_X_LPARAM(l_param);
            window->input.last_mouse_y = GET_Y_LPARAM(l_param);
            SetCapture(hwnd);
        }
        return 0;
    case WM_LBUTTONUP:
        if (window) {
            window->input.dragging = false;
            ReleaseCapture();
        }
        return 0;
    case WM_MOUSEMOVE:
        if (window) {
            const int mouse_x = GET_X_LPARAM(l_param);
            const int mouse_y = GET_Y_LPARAM(l_param);
            RECT rect = {};
            GetClientRect(hwnd, &rect);
            const int client_w = static_cast<int>(rect.right - rect.left);
            const int client_h = static_cast<int>(rect.bottom - rect.top);
            const int width = std::max(1, client_w);
            const int height = std::max(1, client_h);
            window->input.client_width = width;
            window->input.client_height = height;
            window->input.mouse_x = mouse_x;
            window->input.mouse_y = mouse_y;
            window->input.mouse_aim_x = normalize_mouse_axis(mouse_x, width - 1);
            window->input.mouse_aim_y = normalize_mouse_axis(mouse_y, height - 1);

            const bool control_focus_object =
                window->input.input_mode == ViewerInputState::InputMode::Control
                && !window->input.focus_uid.empty()
                && window->input.camera_mode == ViewerInputState::CameraMode::FollowObject;

            if (control_focus_object) {
                if (!window->input.mouse_has_reference) {
                    window->input.last_mouse_x = mouse_x;
                    window->input.last_mouse_y = mouse_y;
                    window->input.mouse_has_reference = true;
                    return 0;
                }
                const int dx = mouse_x - window->input.last_mouse_x;
                const int dy = mouse_y - window->input.last_mouse_y;
                window->input.last_mouse_x = mouse_x;
                window->input.last_mouse_y = mouse_y;
                window->input.camera_yaw -= static_cast<float>(dx) * 0.006f;
                window->input.camera_pitch += static_cast<float>(dy) * 0.0045f;
                window->input.camera_pitch = std::clamp(window->input.camera_pitch, -1.45f, 1.45f);
                return 0;
            }

            if (window->input.input_mode == ViewerInputState::InputMode::Follow
                && window->input.focus_uid.empty()) {
                return 0;
            }

            if (!window->input.dragging) {
                return 0;
            }

            const int dx = mouse_x - window->input.last_mouse_x;
            const int dy = mouse_y - window->input.last_mouse_y;
            window->input.last_mouse_x = mouse_x;
            window->input.last_mouse_y = mouse_y;
            window->input.camera_yaw -= static_cast<float>(dx) * 0.006f;
            window->input.camera_pitch += static_cast<float>(dy) * 0.0045f;
            window->input.camera_pitch = std::clamp(window->input.camera_pitch, -1.45f, 1.45f);
        }
        return 0;
    case WM_MOUSEWHEEL:
        if (window) {
            if (window->input.input_mode == ViewerInputState::InputMode::Follow
                && window->input.focus_uid.empty()) {
                return 0;
            }
            const int delta = GET_WHEEL_DELTA_WPARAM(w_param);
            window->input.camera_distance -= static_cast<float>(delta) * 6.4f;
            window->input.camera_distance = std::clamp(window->input.camera_distance, 1000.0f, 180000.0f);
        }
        return 0;
    case WM_KEYDOWN:
        if (!window) {
            break;
        }
        if (w_param == VK_F1) {
            const bool was_control_mode = window->input.input_mode == ViewerInputState::InputMode::Control;
            window->input.input_mode = ViewerInputState::InputMode::Control;
            if (was_control_mode) {
                cycle_follow_target(window->input);
            }
            return 0;
        }
        if (w_param == VK_F2) {
            const bool was_control_mode = window->input.input_mode == ViewerInputState::InputMode::Control;
            window->input.input_mode = ViewerInputState::InputMode::Follow;
            if (!was_control_mode) {
                cycle_follow_target(window->input);
            }
            return 0;
        }
        if (w_param == VK_F3) {
            window->input.shadows_enabled = !window->input.shadows_enabled;
            return 0;
        }
        if (w_param == VK_F4) {
            window->input.material_system_enabled = !window->input.material_system_enabled;
            return 0;
        }
        if (w_param == VK_F5) {
            window->input.camera_roll_locked = !window->input.camera_roll_locked;
            return 0;
        }
        if (w_param == VK_OEM_PLUS || w_param == VK_ADD) {
            window->input.camera_fov_y = std::max(20.0f, window->input.camera_fov_y - 2.0f);
            return 0;
        }
        if (w_param == VK_OEM_MINUS || w_param == VK_SUBTRACT) {
            window->input.camera_fov_y = std::min(110.0f, window->input.camera_fov_y + 2.0f);
            return 0;
        }
        if (window->input.input_mode == ViewerInputState::InputMode::Follow
            && window->input.focus_uid.empty()) {
            return 0;
        }
        if (w_param == 'W') window->input.move_forward = true;
        if (w_param == 'S') window->input.move_backward = true;
        if (w_param == 'A') window->input.move_left = true;
        if (w_param == 'D') window->input.move_right = true;
        if (w_param == 'Q') window->input.move_down = true;
        if (w_param == 'E') window->input.move_up = true;
        return 0;
    case WM_KEYUP:
        if (!window) {
            break;
        }
        if (w_param == 'W') window->input.move_forward = false;
        if (w_param == 'S') window->input.move_backward = false;
        if (w_param == 'A') window->input.move_left = false;
        if (w_param == 'D') window->input.move_right = false;
        if (w_param == 'Q') window->input.move_down = false;
        if (w_param == 'E') window->input.move_up = false;
        return 0;
    default:
        break;
    }
    return DefWindowProc(hwnd, msg, w_param, l_param);
}

} // namespace

void update_camera(ViewerInputState& input, float dt_seconds) {
    (void)dt_seconds;
    if (input.camera_mode == ViewerInputState::CameraMode::FollowObject
        || (input.input_mode == ViewerInputState::InputMode::Follow && input.focus_uid.empty())
        || (!input.move_forward
            && !input.move_backward
            && !input.move_left
            && !input.move_right
            && !input.move_up
            && !input.move_down)) {
        return;
    }

    const Float3 forward = make_float3(std::cos(input.camera_yaw), 0.0f, std::sin(input.camera_yaw));
    const Float3 right = make_float3(-forward.z, 0.0f, forward.x);
    Float3 move = make_float3(0.0f, 0.0f, 0.0f);

    if (input.move_forward) move = add(move, scale(forward, -1.0f));
    if (input.move_backward) move = add(move, scale(forward, 1.0f));
    if (input.move_left) move = add(move, scale(right, -1.0f));
    if (input.move_right) move = add(move, right);
    if (input.move_up) move.y += 1.0f;
    if (input.move_down) move.y -= 1.0f;

    const float move_length = std::sqrt(move.x * move.x + move.y * move.y + move.z * move.z);
    if (move_length <= 1e-6f) {
        return;
    }

    const float inv_length = 1.0f / move_length;
    move = scale(move, inv_length);

    const float move_speed = std::max(120.0f, input.camera_distance * 0.015f);
    input.camera_target = add(input.camera_target, scale(move, move_speed));
}

bool create_window(Win32Window& window, std::string& error) {
    window.instance = GetModuleHandle(nullptr);
    const char* class_name = "BvrSimGameModeWindow";

    WNDCLASS wc = {};
    wc.lpfnWndProc = dx11_window_proc;
    wc.hInstance = window.instance;
    wc.lpszClassName = class_name;
    wc.hCursor = LoadCursor(nullptr, IDC_ARROW);

    if (!RegisterClass(&wc) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS) {
        error = "RegisterClass failed";
        return false;
    }

    window.hwnd = CreateWindowEx(
        0,
        class_name,
        "BVR Sim DX11 Game Mode",
        WS_OVERLAPPEDWINDOW | WS_VISIBLE,
        CW_USEDEFAULT,
        CW_USEDEFAULT,
        1440,
        900,
        nullptr,
        nullptr,
        window.instance,
        &window
    );
    if (!window.hwnd) {
        error = "CreateWindowEx failed";
        return false;
    }

    ShowWindow(window.hwnd, SW_SHOW);
    UpdateWindow(window.hwnd);
    return true;
}

void destroy_window(Win32Window& window) {
    if (window.hwnd) {
        DestroyWindow(window.hwnd);
        window.hwnd = nullptr;
    }
}

void draw_hud_text(HWND hwnd, const ViewerInputState& input, double sim_time, long object_count, const RenderFrameStats& stats) {
    HDC dc = GetDC(hwnd);
    if (!dc) {
        return;
    }

    RECT rect = {};
    GetClientRect(hwnd, &rect);
    SetBkMode(dc, TRANSPARENT);
    SetTextColor(dc, RGB(230, 240, 248));

    HFONT font = get_hud_font();
    HFONT old_font = font ? static_cast<HFONT>(SelectObject(dc, font)) : nullptr;

    auto draw_line = [&](int x, int y, const std::string& text) {
        TextOutA(dc, x, y, text.c_str(), static_cast<int>(text.size()));
    };

    std::ostringstream line1;
    line1 << std::fixed << std::setprecision(2)
          << "SimTime " << sim_time
          << "  Objects " << object_count
          << "  Draws " << stats.draw_calls
          << "  Vertices " << stats.vertex_count;
    draw_line(16, 16, line1.str());

    std::ostringstream line2;
    const char* mode_text = input.input_mode == ViewerInputState::InputMode::Control ? "control" : "follow";
    const char* focus_text = input.focus_uid.empty() ? "free" : "object";
    line2 << std::fixed << std::setprecision(1)
          << "Camera Target (" << input.camera_target.x << ", " << input.camera_target.y << ", " << input.camera_target.z << ")"
          << "  FOV " << input.camera_fov_y
          << "  Dist " << input.camera_distance
          << "  Mode " << mode_text
          << "  Focus " << focus_text;
    draw_line(16, 40, line2.str());

    std::ostringstream line3;
    line3 << "Shadows " << (input.shadows_enabled ? "on" : "off")
          << "  Materials " << (input.material_system_enabled ? "full" : "simple")
          << "  RollLock " << (input.camera_roll_locked ? "on" : "off");
    draw_line(16, 64, line3.str());

    draw_line(16, rect.bottom - 56, "Move: W A S D  Vertical: Q/E  Look: drag mouse  Zoom: wheel");
    draw_line(16, rect.bottom - 34, "View: +/- FOV  F1 control/next  F2 follow/next  F3 shadows  F4 materials  F5 roll lock");

    if (font && old_font) {
        SelectObject(dc, old_font);
    }
    flush_desktop_composition();
    ReleaseDC(hwnd, dc);
}

#endif

} // namespace bvr_sim



