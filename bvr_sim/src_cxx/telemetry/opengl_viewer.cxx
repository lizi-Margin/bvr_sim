#include "opengl_viewer.hxx"

#include "rubbish_can/SL.hxx"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstring>
#include <vector>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <GL/gl.h>
#pragma comment(lib, "opengl32.lib")
#endif

namespace bvr_sim {

OpenGLViewer::OpenGLViewer()
    : running_(false),
      stop_requested_(false),
      supported_(false) {
#ifdef _WIN32
    supported_ = true;
#else
    supported_ = false;
#endif
}

OpenGLViewer::~OpenGLViewer() {
    stop();
}

void OpenGLViewer::set_snapshot_provider(std::function<std::shared_ptr<const WorldSnapshot>()> provider) {
    snapshot_provider_ = std::move(provider);
}

void OpenGLViewer::set_command_submitter(std::function<void(const TelemetryCommand&)> submitter) {
    command_submitter_ = std::move(submitter);
}

void OpenGLViewer::start() {
    if (running_.load()) {
        return;
    }

    stop_requested_ = false;
    {
        std::lock_guard<std::mutex> lock(state_mutex_);
        last_error_.clear();
    }
    viewer_thread_ = std::thread(&OpenGLViewer::run_loop, this);
}

void OpenGLViewer::stop() noexcept {
    stop_requested_ = true;
    if (viewer_thread_.joinable()) {
        viewer_thread_.join();
    }
    running_ = false;
}

bool OpenGLViewer::is_running() const noexcept {
    return running_.load();
}

bool OpenGLViewer::is_supported() const noexcept {
    return supported_.load();
}

json::JSON OpenGLViewer::get_status() const {
    json::JSON status = json::JSON::Make(json::JSON::Class::Object);
    status["running"] = json::Boolean(is_running());
    status["supported"] = json::Boolean(is_supported());
#ifdef _WIN32
    status["platform"] = json::String("windows");
    status["backend"] = json::String("win32_wgl");
#else
    status["platform"] = json::String("linux_or_other");
    status["backend"] = json::String("stub");
#endif

    std::lock_guard<std::mutex> lock(state_mutex_);
    status["last_error"] = json::String(last_error_);
    status["focus_uid"] = json::String(focus_uid_);
    status["last_sim_time"] = json::Float(last_sim_time_);
    status["last_object_count"] = json::Integral(last_object_count_);
    return status;
}

void OpenGLViewer::submit_command(const TelemetryCommand& command) const {
    if (command_submitter_) {
        command_submitter_(command);
    }
}

#ifndef _WIN32

void OpenGLViewer::run_loop() noexcept {
    {
        std::lock_guard<std::mutex> lock(state_mutex_);
        last_error_ = "OpenGL viewer is currently implemented for Windows only";
        focus_uid_.clear();
        last_sim_time_ = 0.0;
        last_object_count_ = 0;
    }
    running_ = false;
}

#else

namespace {

constexpr float kPi = 3.14159265358979323846f;

struct ViewerState {
    HINSTANCE instance = nullptr;
    HWND hwnd = nullptr;
    HDC dc = nullptr;
    HGLRC rc = nullptr;
    OpenGLViewer* owner = nullptr;
    bool should_close = false;
    bool paused = false;
    bool follow_focus = false;
    float camera_yaw = 0.65f;
    float camera_pitch = 0.55f;
    float camera_distance = 22000.0f;
    float camera_fov_y = 50.0f;
    float camera_target_x = 0.0f;
    float camera_target_y = 0.0f;
    float camera_target_z = 0.0f;
    bool move_forward = false;
    bool move_backward = false;
    bool move_left = false;
    bool move_right = false;
    bool move_up = false;
    bool move_down = false;
    std::string selected_uid;
    std::string focus_uid;
};

ViewerState* get_viewer_state(HWND hwnd) {
    return reinterpret_cast<ViewerState*>(GetWindowLongPtr(hwnd, GWLP_USERDATA));
}

std::array<float, 3> team_color(const TelemetryObjectState& object) {
    if (object.team == "Blue") {
        return {0.34f, 0.73f, 1.0f};
    }
    if (object.team == "Red") {
        return {1.0f, 0.42f, 0.34f};
    }
    return {0.85f, 0.85f, 0.78f};
}

void perspective_gl(double fov_y_degrees, double aspect, double z_near, double z_far) {
    const double fH = std::tan(fov_y_degrees * kPi / 360.0) * z_near;
    const double fW = fH * aspect;
    glFrustum(-fW, fW, -fH, fH, z_near, z_far);
}

void normalize(float& x, float& y, float& z) {
    const float length = std::sqrt(x * x + y * y + z * z);
    if (length <= 1e-6f) {
        return;
    }
    x /= length;
    y /= length;
    z /= length;
}

void cross(
    float ax, float ay, float az,
    float bx, float by, float bz,
    float& rx, float& ry, float& rz) {
    rx = ay * bz - az * by;
    ry = az * bx - ax * bz;
    rz = ax * by - ay * bx;
}

void look_at_gl(
    float eye_x, float eye_y, float eye_z,
    float center_x, float center_y, float center_z,
    float up_x, float up_y, float up_z) {
    float fx = center_x - eye_x;
    float fy = center_y - eye_y;
    float fz = center_z - eye_z;
    normalize(fx, fy, fz);

    normalize(up_x, up_y, up_z);

    float sx = 0.0f;
    float sy = 0.0f;
    float sz = 0.0f;
    cross(fx, fy, fz, up_x, up_y, up_z, sx, sy, sz);
    normalize(sx, sy, sz);

    float ux = 0.0f;
    float uy = 0.0f;
    float uz = 0.0f;
    cross(sx, sy, sz, fx, fy, fz, ux, uy, uz);

    const GLfloat matrix[16] = {
        sx, ux, -fx, 0.0f,
        sy, uy, -fy, 0.0f,
        sz, uz, -fz, 0.0f,
        0.0f, 0.0f, 0.0f, 1.0f
    };
    glMultMatrixf(matrix);
    glTranslatef(-eye_x, -eye_y, -eye_z);
}

void draw_grid(float size, int half_count) {
    glColor3f(0.18f, 0.25f, 0.28f);
    glBegin(GL_LINES);
    for (int i = -half_count; i <= half_count; ++i) {
        const float value = size * static_cast<float>(i) / static_cast<float>(half_count);
        glVertex3f(value, 0.0f, -size);
        glVertex3f(value, 0.0f, size);
        glVertex3f(-size, 0.0f, value);
        glVertex3f(size, 0.0f, value);
    }
    glEnd();
}

void draw_box(float sx, float sy, float sz) {
    const float hx = sx * 0.5f;
    const float hy = sy * 0.5f;
    const float hz = sz * 0.5f;
    glBegin(GL_QUADS);
    glVertex3f(-hx, -hy, hz); glVertex3f(hx, -hy, hz); glVertex3f(hx, hy, hz); glVertex3f(-hx, hy, hz);
    glVertex3f(-hx, -hy, -hz); glVertex3f(-hx, hy, -hz); glVertex3f(hx, hy, -hz); glVertex3f(hx, -hy, -hz);
    glVertex3f(-hx, -hy, -hz); glVertex3f(-hx, -hy, hz); glVertex3f(-hx, hy, hz); glVertex3f(-hx, hy, -hz);
    glVertex3f(hx, -hy, -hz); glVertex3f(hx, hy, -hz); glVertex3f(hx, hy, hz); glVertex3f(hx, -hy, hz);
    glVertex3f(-hx, hy, -hz); glVertex3f(-hx, hy, hz); glVertex3f(hx, hy, hz); glVertex3f(hx, hy, -hz);
    glVertex3f(-hx, -hy, -hz); glVertex3f(hx, -hy, -hz); glVertex3f(hx, -hy, hz); glVertex3f(-hx, -hy, hz);
    glEnd();
}

void draw_aircraft() {
    glBegin(GL_TRIANGLES);
    glVertex3f(180.0f, 0.0f, 0.0f);
    glVertex3f(-120.0f, 40.0f, 90.0f);
    glVertex3f(-120.0f, 40.0f, -90.0f);

    glVertex3f(180.0f, 0.0f, 0.0f);
    glVertex3f(-120.0f, -40.0f, -90.0f);
    glVertex3f(-120.0f, -40.0f, 90.0f);
    glEnd();

    glBegin(GL_QUADS);
    glVertex3f(-10.0f, 0.0f, -260.0f);
    glVertex3f(70.0f, 0.0f, -30.0f);
    glVertex3f(-40.0f, 0.0f, 30.0f);
    glVertex3f(-110.0f, 0.0f, -180.0f);

    glVertex3f(-10.0f, 0.0f, 260.0f);
    glVertex3f(-110.0f, 0.0f, 180.0f);
    glVertex3f(-40.0f, 0.0f, -30.0f);
    glVertex3f(70.0f, 0.0f, 30.0f);
    glEnd();
}

void draw_missile() {
    draw_box(220.0f, 24.0f, 24.0f);
    glBegin(GL_TRIANGLES);
    glVertex3f(-20.0f, 0.0f, 0.0f);
    glVertex3f(-90.0f, 0.0f, 70.0f);
    glVertex3f(-90.0f, 0.0f, -70.0f);
    glEnd();
}

void draw_ground_unit() {
    draw_box(180.0f, 90.0f, 180.0f);
}

void draw_selection_ring(float radius, bool focused) {
    glColor3f(focused ? 0.35f : 0.84f, focused ? 0.82f : 0.95f, focused ? 1.0f : 0.58f);
    glBegin(GL_LINE_LOOP);
    for (int i = 0; i < 48; ++i) {
        const float a = static_cast<float>(i) / 48.0f * 2.0f * kPi;
        glVertex3f(std::cos(a) * radius, 0.0f, std::sin(a) * radius);
    }
    glEnd();
}

LRESULT CALLBACK viewer_window_proc(HWND hwnd, UINT msg, WPARAM w_param, LPARAM l_param) {
    ViewerState* state = get_viewer_state(hwnd);
    switch (msg) {
    case WM_CLOSE:
        if (state) {
            state->should_close = true;
        }
        DestroyWindow(hwnd);
        return 0;
    case WM_DESTROY:
        PostQuitMessage(0);
        return 0;
    case WM_KEYDOWN:
        if (!state || !state->owner) {
            break;
        }
        if (w_param == VK_ESCAPE) {
            state->should_close = true;
            DestroyWindow(hwnd);
            return 0;
        }
        if (w_param == VK_SPACE) {
            TelemetryCommand command;
            command.kind = state->paused ? TelemetryCommandKind::Resume : TelemetryCommandKind::Pause;
            state->owner->submit_command(command);
            state->paused = !state->paused;
            return 0;
        }
        if (w_param == 'N') {
            TelemetryCommand command;
            command.kind = TelemetryCommandKind::Step;
            command.payload = json::JSON::Make(json::JSON::Class::Object);
            command.payload["steps"] = json::Integral(1);
            state->owner->submit_command(command);
            return 0;
        }
        if (w_param == 'F') {
            state->follow_focus = !state->follow_focus;
            return 0;
        }
        if (w_param == VK_OEM_PLUS || w_param == VK_ADD) {
            state->camera_fov_y = std::max(20.0f, state->camera_fov_y - 2.0f);
            return 0;
        }
        if (w_param == VK_OEM_MINUS || w_param == VK_SUBTRACT) {
            state->camera_fov_y = std::min(110.0f, state->camera_fov_y + 2.0f);
            return 0;
        }
        if (w_param == VK_LEFT) {
            state->camera_yaw -= 0.08f;
            return 0;
        }
        if (w_param == VK_RIGHT) {
            state->camera_yaw += 0.08f;
            return 0;
        }
        if (w_param == VK_UP) {
            state->camera_pitch = std::max(0.12f, state->camera_pitch - 0.06f);
            return 0;
        }
        if (w_param == VK_DOWN) {
            state->camera_pitch = std::min(1.4f, state->camera_pitch + 0.06f);
            return 0;
        }
        if (w_param == 'W') {
            state->move_forward = true;
            return 0;
        }
        if (w_param == 'S') {
            state->move_backward = true;
            return 0;
        }
        if (w_param == 'A') {
            state->move_left = true;
            return 0;
        }
        if (w_param == 'D') {
            state->move_right = true;
            return 0;
        }
        if (w_param == 'Q') {
            state->move_down = true;
            return 0;
        }
        if (w_param == 'E') {
            state->move_up = true;
            return 0;
        }
        break;
    case WM_KEYUP:
        if (!state) {
            break;
        }
        if (w_param == 'W') {
            state->move_forward = false;
            return 0;
        }
        if (w_param == 'S') {
            state->move_backward = false;
            return 0;
        }
        if (w_param == 'A') {
            state->move_left = false;
            return 0;
        }
        if (w_param == 'D') {
            state->move_right = false;
            return 0;
        }
        if (w_param == 'Q') {
            state->move_down = false;
            return 0;
        }
        if (w_param == 'E') {
            state->move_up = false;
            return 0;
        }
        break;
    default:
        break;
    }
    return DefWindowProc(hwnd, msg, w_param, l_param);
}

bool create_gl_window(ViewerState& state, std::string& error) {
    state.instance = GetModuleHandle(nullptr);

    WNDCLASS wc = {};
    wc.style = CS_OWNDC;
    wc.lpfnWndProc = viewer_window_proc;
    wc.hInstance = state.instance;
    wc.lpszClassName = "BvrSimOpenGLViewerWindow";
    wc.hCursor = LoadCursor(nullptr, IDC_ARROW);

    if (!RegisterClass(&wc) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS) {
        error = "RegisterClass failed";
        return false;
    }

    state.hwnd = CreateWindowEx(
        0,
        wc.lpszClassName,
        "BVR Sim OpenGL Viewer",
        WS_OVERLAPPEDWINDOW | WS_VISIBLE,
        CW_USEDEFAULT,
        CW_USEDEFAULT,
        1280,
        820,
        nullptr,
        nullptr,
        state.instance,
        nullptr
    );
    if (!state.hwnd) {
        error = "CreateWindowEx failed";
        return false;
    }

    SetWindowLongPtr(state.hwnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(&state));

    state.dc = GetDC(state.hwnd);
    if (!state.dc) {
        error = "GetDC failed";
        return false;
    }

    PIXELFORMATDESCRIPTOR pfd = {};
    pfd.nSize = sizeof(PIXELFORMATDESCRIPTOR);
    pfd.nVersion = 1;
    pfd.dwFlags = PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER;
    pfd.iPixelType = PFD_TYPE_RGBA;
    pfd.cColorBits = 32;
    pfd.cDepthBits = 24;
    pfd.iLayerType = PFD_MAIN_PLANE;

    const int format = ChoosePixelFormat(state.dc, &pfd);
    if (format == 0 || !SetPixelFormat(state.dc, format, &pfd)) {
        error = "SetPixelFormat failed";
        return false;
    }

    state.rc = wglCreateContext(state.dc);
    if (!state.rc || !wglMakeCurrent(state.dc, state.rc)) {
        error = "wglCreateContext failed";
        return false;
    }

    ShowWindow(state.hwnd, SW_SHOW);
    UpdateWindow(state.hwnd);
    return true;
}

void destroy_gl_window(ViewerState& state) {
    if (state.rc) {
        wglMakeCurrent(nullptr, nullptr);
        wglDeleteContext(state.rc);
        state.rc = nullptr;
    }
    if (state.dc && state.hwnd) {
        ReleaseDC(state.hwnd, state.dc);
        state.dc = nullptr;
    }
    if (state.hwnd) {
        DestroyWindow(state.hwnd);
        state.hwnd = nullptr;
    }
}

void render_scene(ViewerState& view_state, const std::shared_ptr<const WorldSnapshot>& snapshot) {
    RECT rect{};
    GetClientRect(view_state.hwnd, &rect);
    const int width = std::max(1L, rect.right - rect.left);
    const int height = std::max(1L, rect.bottom - rect.top);

    glViewport(0, 0, width, height);
    glClearColor(0.04f, 0.07f, 0.11f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);

    glEnable(GL_DEPTH_TEST);
    glDisable(GL_CULL_FACE);
    glShadeModel(GL_SMOOTH);

    glMatrixMode(GL_PROJECTION);
    glLoadIdentity();
    perspective_gl(view_state.camera_fov_y, static_cast<double>(width) / static_cast<double>(height), 10.0, 400000.0);

    if (view_state.follow_focus && snapshot && !view_state.focus_uid.empty()) {
        for (const auto& object : snapshot->objects) {
            if (object.uid == view_state.focus_uid) {
                view_state.camera_target_x = static_cast<float>(object.position[0]);
                view_state.camera_target_y = static_cast<float>(object.position[2]);
                view_state.camera_target_z = static_cast<float>(object.position[1]);
                break;
            }
        }
    }

    const float target_x = view_state.camera_target_x;
    const float target_y = view_state.camera_target_y;
    const float target_z = view_state.camera_target_z;

    const float eye_x = target_x + std::cos(view_state.camera_yaw) * std::cos(view_state.camera_pitch) * view_state.camera_distance;
    const float eye_y = target_y + std::sin(view_state.camera_pitch) * view_state.camera_distance;
    const float eye_z = target_z + std::sin(view_state.camera_yaw) * std::cos(view_state.camera_pitch) * view_state.camera_distance;

    glMatrixMode(GL_MODELVIEW);
    glLoadIdentity();
    look_at_gl(eye_x, eye_y, eye_z, target_x, target_y, target_z, 0.0f, 1.0f, 0.0f);

    draw_grid(45000.0f, 18);

    if (snapshot) {
        for (const auto& object : snapshot->objects) {
            const auto color = team_color(object);
            glPushMatrix();
            glTranslatef(
                static_cast<float>(object.position[0]),
                static_cast<float>(object.position[2]),
                static_cast<float>(object.position[1]));

            const auto& orientation = object.orientation;
            glRotatef(static_cast<float>(orientation[2] * 57.2957795), 0.0f, 1.0f, 0.0f);
            glRotatef(static_cast<float>(orientation[1] * 57.2957795), 0.0f, 0.0f, 1.0f);
            glRotatef(static_cast<float>(orientation[0] * 57.2957795), 1.0f, 0.0f, 0.0f);

            const float alpha_scale = object.alive ? 1.0f : 0.35f;
            glColor3f(color[0] * alpha_scale, color[1] * alpha_scale, color[2] * alpha_scale);

            if (object.type.find("Aircraft") != std::string::npos) {
                draw_aircraft();
            } else if (object.type.find("Missile") != std::string::npos) {
                draw_missile();
            } else {
                draw_ground_unit();
            }

            const bool selected = !view_state.selected_uid.empty() && view_state.selected_uid == object.uid;
            const bool focused = !view_state.focus_uid.empty() && view_state.focus_uid == object.uid;
            if (selected || focused) {
                glTranslatef(0.0f, -static_cast<float>(object.position[2]) + 8.0f, 0.0f);
                draw_selection_ring(selected ? 260.0f : 340.0f, focused);
            }
            glPopMatrix();
        }
    }

    SwapBuffers(view_state.dc);
}

void update_camera_motion(ViewerState& view_state) {
    if (view_state.follow_focus
        || (!view_state.move_forward
            && !view_state.move_backward
            && !view_state.move_left
            && !view_state.move_right
            && !view_state.move_up
            && !view_state.move_down)) {
        return;
    }

    const float planar_yaw = view_state.camera_yaw;
    const float forward_x = std::cos(planar_yaw);
    const float forward_z = std::sin(planar_yaw);
    const float right_x = -forward_z;
    const float right_z = forward_x;

    float move_x = 0.0f;
    float move_y = 0.0f;
    float move_z = 0.0f;
    if (view_state.move_forward) {
        move_x -= forward_x;
        move_z -= forward_z;
    }
    if (view_state.move_backward) {
        move_x += forward_x;
        move_z += forward_z;
    }
    if (view_state.move_right) {
        move_x -= right_x;
        move_z -= right_z;
    }
    if (view_state.move_left) {
        move_x += right_x;
        move_z += right_z;
    }
    if (view_state.move_up) {
        move_y += 1.0f;
    }
    if (view_state.move_down) {
        move_y -= 1.0f;
    }

    const float length = std::sqrt(move_x * move_x + move_y * move_y + move_z * move_z);
    if (length <= 1e-6f) {
        return;
    }
    move_x /= length;
    move_y /= length;
    move_z /= length;

    const float speed = std::max(120.0f, view_state.camera_distance * 0.015f);
    view_state.camera_target_x += move_x * speed;
    view_state.camera_target_y += move_y * speed;
    view_state.camera_target_z += move_z * speed;
}

}

void OpenGLViewer::run_loop() noexcept {
    ViewerState view_state;
    view_state.owner = this;

    std::string error;
    if (!create_gl_window(view_state, error)) {
        std::lock_guard<std::mutex> lock(state_mutex_);
        last_error_ = error;
        running_ = false;
        return;
    }

    running_ = true;
    {
        std::lock_guard<std::mutex> lock(state_mutex_);
        last_error_.clear();
    }

    while (!stop_requested_.load() && !view_state.should_close) {
        MSG msg;
        while (PeekMessage(&msg, nullptr, 0, 0, PM_REMOVE)) {
            if (msg.message == WM_QUIT) {
                view_state.should_close = true;
                break;
            }
            TranslateMessage(&msg);
            DispatchMessage(&msg);
        }

        auto snapshot = snapshot_provider_ ? snapshot_provider_() : std::shared_ptr<const WorldSnapshot>();
        if (snapshot) {
            view_state.paused = snapshot->paused;
        }
        update_camera_motion(view_state);
        {
            std::lock_guard<std::mutex> lock(state_mutex_);
            last_sim_time_ = snapshot ? snapshot->sim_time : 0.0;
            last_object_count_ = snapshot ? static_cast<long>(snapshot->objects.size()) : 0L;
            focus_uid_ = view_state.focus_uid;
        }

        render_scene(view_state, snapshot);
        std::this_thread::sleep_for(std::chrono::milliseconds(16));
    }

    destroy_gl_window(view_state);
    running_ = false;
}

#endif

}
