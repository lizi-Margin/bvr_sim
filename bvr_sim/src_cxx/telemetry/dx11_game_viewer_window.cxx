#include "dx11_game_viewer_internal.hxx"

#include <algorithm>
#include <cmath>
#include <iomanip>
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
        if (window && window->input.dragging) {
            const int mouse_x = GET_X_LPARAM(l_param);
            const int mouse_y = GET_Y_LPARAM(l_param);
            const int dx = mouse_x - window->input.last_mouse_x;
            const int dy = mouse_y - window->input.last_mouse_y;
            window->input.last_mouse_x = mouse_x;
            window->input.last_mouse_y = mouse_y;
            window->input.camera_yaw += static_cast<float>(dx) * 0.006f;
            window->input.camera_pitch += static_cast<float>(dy) * 0.0045f;
            window->input.camera_pitch = std::clamp(window->input.camera_pitch, 0.12f, 1.45f);
        }
        return 0;
    case WM_MOUSEWHEEL:
        if (window) {
            const int delta = GET_WHEEL_DELTA_WPARAM(w_param);
            window->input.camera_distance -= static_cast<float>(delta) * 6.4f;
            window->input.camera_distance = std::clamp(window->input.camera_distance, 3000.0f, 180000.0f);
        }
        return 0;
    case WM_KEYDOWN:
        if (!window) {
            break;
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
    const Float3 forward = make_float3(std::cos(input.camera_yaw), 0.0f, std::sin(input.camera_yaw));
    const Float3 right = make_float3(-forward.z, 0.0f, forward.x);
    const float move_speed = std::max(1200.0f, input.camera_distance * 0.40f) * dt_seconds;

    if (input.move_forward) input.camera_target = add(input.camera_target, scale(forward, move_speed));
    if (input.move_backward) input.camera_target = add(input.camera_target, scale(forward, -move_speed));
    if (input.move_left) input.camera_target = add(input.camera_target, scale(right, -move_speed));
    if (input.move_right) input.camera_target = add(input.camera_target, scale(right, move_speed));
    if (input.move_up) input.camera_target.y += move_speed;
    if (input.move_down) input.camera_target.y -= move_speed;
}

bool create_window(Win32Window& window, std::string& error) {
    window.instance = GetModuleHandle(nullptr);
    const char* class_name = "BvrSimDX11GameViewerWindow";

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
        "BVR Sim DX11 Game Viewer",
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

    HFONT font = CreateFontA(
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
    line2 << std::fixed << std::setprecision(1)
          << "Camera Target (" << input.camera_target.x << ", " << input.camera_target.y << ", " << input.camera_target.z << ")"
          << "  Dist " << input.camera_distance;
    draw_line(16, 40, line2.str());

    draw_line(16, rect.bottom - 34, "Move: W A S D  Vertical: Q/E  Look: drag mouse  Zoom: wheel");

    if (font && old_font) {
        SelectObject(dc, old_font);
    }
    if (font) {
        DeleteObject(font);
    }
    ReleaseDC(hwnd, dc);
}

#endif

} // namespace bvr_sim
