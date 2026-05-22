#include "embedded_web_server.hxx"

#include "support/SL.hxx"
#include "support/check.hxx"

#include <algorithm>
#include <array>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <map>
#include <set>
#include <sstream>
#include <vector>

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "ws2_32.lib")
using SocketHandle = SOCKET;
static constexpr SocketHandle kInvalidSocket = INVALID_SOCKET;
#else
#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <unistd.h>
using SocketHandle = int;
static constexpr SocketHandle kInvalidSocket = -1;
#endif

namespace bvr_sim {

namespace {

struct SocketSystemGuard {
    SocketSystemGuard() {
#ifdef _WIN32
        WSADATA data;
        int rc = WSAStartup(MAKEWORD(2, 2), &data);
        format_check(rc == 0, "WSAStartup failed");
#endif
    }

    ~SocketSystemGuard() {
#ifdef _WIN32
        WSACleanup();
#endif
    }
};

SocketSystemGuard& socket_system_guard() {
    static SocketSystemGuard guard;
    return guard;
}

void close_socket(SocketHandle sock) {
    if (sock == kInvalidSocket) {
        return;
    }
#ifdef _WIN32
    closesocket(sock);
#else
    close(sock);
#endif
}

bool socket_is_valid(SocketHandle sock) {
    return sock != kInvalidSocket;
}

json::JSON make_server_error(const std::string& message) {
    json::JSON result = json::JSON::Make(json::JSON::Class::Object);
    result["status"] = json::String("error");
    result["message"] = json::String(message);
    return result;
}

json::JSON make_server_ok(const std::string& message) {
    json::JSON result = json::JSON::Make(json::JSON::Class::Object);
    result["status"] = json::String("ok");
    result["message"] = json::String(message);
    return result;
}

std::string json_compact_dump(const json::JSON& value) {
    return value.dump(1, "", "");
}

std::string trim(const std::string& value) {
    size_t start = 0;
    while (start < value.size() && std::isspace(static_cast<unsigned char>(value[start]))) {
        ++start;
    }
    size_t end = value.size();
    while (end > start && std::isspace(static_cast<unsigned char>(value[end - 1]))) {
        --end;
    }
    return value.substr(start, end - start);
}

std::string base64_encode(const std::string& input) {
    static const char table[] =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

    std::string output;
    output.reserve(((input.size() + 2) / 3) * 4);

    size_t i = 0;
    while (i + 2 < input.size()) {
        unsigned value = (static_cast<unsigned char>(input[i]) << 16)
            | (static_cast<unsigned char>(input[i + 1]) << 8)
            | static_cast<unsigned char>(input[i + 2]);
        output.push_back(table[(value >> 18) & 0x3F]);
        output.push_back(table[(value >> 12) & 0x3F]);
        output.push_back(table[(value >> 6) & 0x3F]);
        output.push_back(table[value & 0x3F]);
        i += 3;
    }

    if (i < input.size()) {
        unsigned value = static_cast<unsigned char>(input[i]) << 16;
        output.push_back(table[(value >> 18) & 0x3F]);
        if (i + 1 < input.size()) {
            value |= static_cast<unsigned char>(input[i + 1]) << 8;
            output.push_back(table[(value >> 12) & 0x3F]);
            output.push_back(table[(value >> 6) & 0x3F]);
            output.push_back('=');
        } else {
            output.push_back(table[(value >> 12) & 0x3F]);
            output.push_back('=');
            output.push_back('=');
        }
    }

    return output;
}

std::array<uint32_t, 5> sha1_digest(const std::string& input) {
    uint64_t bit_length = static_cast<uint64_t>(input.size()) * 8;
    std::vector<uint8_t> buffer(input.begin(), input.end());
    buffer.push_back(0x80);
    while ((buffer.size() % 64) != 56) {
        buffer.push_back(0x00);
    }
    for (int shift = 56; shift >= 0; shift -= 8) {
        buffer.push_back(static_cast<uint8_t>((bit_length >> shift) & 0xFF));
    }

    uint32_t h0 = 0x67452301;
    uint32_t h1 = 0xEFCDAB89;
    uint32_t h2 = 0x98BADCFE;
    uint32_t h3 = 0x10325476;
    uint32_t h4 = 0xC3D2E1F0;

    for (size_t chunk = 0; chunk < buffer.size(); chunk += 64) {
        uint32_t w[80] = {0};
        for (int i = 0; i < 16; ++i) {
            size_t offset = chunk + static_cast<size_t>(i) * 4;
            w[i] = (static_cast<uint32_t>(buffer[offset]) << 24)
                | (static_cast<uint32_t>(buffer[offset + 1]) << 16)
                | (static_cast<uint32_t>(buffer[offset + 2]) << 8)
                | static_cast<uint32_t>(buffer[offset + 3]);
        }
        for (int i = 16; i < 80; ++i) {
            uint32_t x = w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16];
            w[i] = (x << 1) | (x >> 31);
        }

        uint32_t a = h0;
        uint32_t b = h1;
        uint32_t c = h2;
        uint32_t d = h3;
        uint32_t e = h4;

        for (int i = 0; i < 80; ++i) {
            uint32_t f = 0;
            uint32_t k = 0;
            if (i < 20) {
                f = (b & c) | ((~b) & d);
                k = 0x5A827999;
            } else if (i < 40) {
                f = b ^ c ^ d;
                k = 0x6ED9EBA1;
            } else if (i < 60) {
                f = (b & c) | (b & d) | (c & d);
                k = 0x8F1BBCDC;
            } else {
                f = b ^ c ^ d;
                k = 0xCA62C1D6;
            }

            uint32_t temp = ((a << 5) | (a >> 27)) + f + e + k + w[i];
            e = d;
            d = c;
            c = (b << 30) | (b >> 2);
            b = a;
            a = temp;
        }

        h0 += a;
        h1 += b;
        h2 += c;
        h3 += d;
        h4 += e;
    }

    return {h0, h1, h2, h3, h4};
}

std::string websocket_accept_key(const std::string& key) {
    auto digest = sha1_digest(key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11");
    std::string raw;
    raw.reserve(20);
    for (uint32_t word : digest) {
        raw.push_back(static_cast<char>((word >> 24) & 0xFF));
        raw.push_back(static_cast<char>((word >> 16) & 0xFF));
        raw.push_back(static_cast<char>((word >> 8) & 0xFF));
        raw.push_back(static_cast<char>(word & 0xFF));
    }
    return base64_encode(raw);
}

bool send_all(SocketHandle sock, const char* data, size_t length) {
    size_t sent = 0;
    while (sent < length) {
#ifdef _WIN32
        int rc = send(sock, data + sent, static_cast<int>(length - sent), 0);
#else
        ssize_t rc = send(sock, data + sent, length - sent, 0);
#endif
        if (rc <= 0) {
            return false;
        }
        sent += static_cast<size_t>(rc);
    }
    return true;
}

bool send_all(SocketHandle sock, const std::string& data) {
    return send_all(sock, data.data(), data.size());
}

bool recv_exact(SocketHandle sock, char* buffer, size_t length) {
    size_t received = 0;
    while (received < length) {
#ifdef _WIN32
        int rc = recv(sock, buffer + received, static_cast<int>(length - received), 0);
#else
        ssize_t rc = recv(sock, buffer + received, length - received, 0);
#endif
        if (rc <= 0) {
            return false;
        }
        received += static_cast<size_t>(rc);
    }
    return true;
}

std::string build_ws_frame(const std::string& payload) {
    std::string frame;
    frame.push_back(static_cast<char>(0x81));
    if (payload.size() < 126) {
        frame.push_back(static_cast<char>(payload.size()));
    } else if (payload.size() <= 0xFFFF) {
        frame.push_back(126);
        frame.push_back(static_cast<char>((payload.size() >> 8) & 0xFF));
        frame.push_back(static_cast<char>(payload.size() & 0xFF));
    } else {
        frame.push_back(127);
        for (int shift = 56; shift >= 0; shift -= 8) {
            frame.push_back(static_cast<char>((payload.size() >> shift) & 0xFF));
        }
    }
    frame += payload;
    return frame;
}

bool recv_ws_frame(SocketHandle sock, std::string& payload_out, bool& close_requested) {
    close_requested = false;
    uint8_t header[2];
    if (!recv_exact(sock, reinterpret_cast<char*>(header), 2)) {
        return false;
    }

    uint8_t opcode = header[0] & 0x0F;
    bool masked = (header[1] & 0x80) != 0;
    uint64_t payload_length = header[1] & 0x7F;

    if (payload_length == 126) {
        uint8_t ext[2];
        if (!recv_exact(sock, reinterpret_cast<char*>(ext), 2)) {
            return false;
        }
        payload_length = (static_cast<uint64_t>(ext[0]) << 8) | ext[1];
    } else if (payload_length == 127) {
        uint8_t ext[8];
        if (!recv_exact(sock, reinterpret_cast<char*>(ext), 8)) {
            return false;
        }
        payload_length = 0;
        for (uint8_t byte : ext) {
            payload_length = (payload_length << 8) | byte;
        }
    }

    uint8_t mask[4] = {0, 0, 0, 0};
    if (masked && !recv_exact(sock, reinterpret_cast<char*>(mask), 4)) {
        return false;
    }

    std::string payload(payload_length, '\0');
    if (payload_length > 0 && !recv_exact(sock, payload.data(), static_cast<size_t>(payload_length))) {
        return false;
    }

    if (masked) {
        for (size_t i = 0; i < payload.size(); ++i) {
            payload[i] ^= static_cast<char>(mask[i % 4]);
        }
    }

    if (opcode == 0x8) {
        close_requested = true;
        return true;
    }

    payload_out = std::move(payload);
    return opcode == 0x1;
}

struct HttpRequest {
    std::string method;
    std::string path;
    std::map<std::string, std::string> headers;
};

bool read_http_request(SocketHandle sock, HttpRequest& request) {
    std::string buffer;
    char chunk[1024];
    while (buffer.find("\r\n\r\n") == std::string::npos) {
#ifdef _WIN32
        int rc = recv(sock, chunk, sizeof(chunk), 0);
#else
        ssize_t rc = recv(sock, chunk, sizeof(chunk), 0);
#endif
        if (rc <= 0) {
            return false;
        }
        buffer.append(chunk, static_cast<size_t>(rc));
        if (buffer.size() > 16384) {
            return false;
        }
    }

    std::istringstream stream(buffer);
    std::string request_line;
    if (!std::getline(stream, request_line)) {
        return false;
    }
    if (!request_line.empty() && request_line.back() == '\r') {
        request_line.pop_back();
    }

    std::istringstream request_line_stream(request_line);
    request_line_stream >> request.method >> request.path;
    if (request.method.empty() || request.path.empty()) {
        return false;
    }

    std::string line;
    while (std::getline(stream, line)) {
        if (line == "\r" || line.empty()) {
            break;
        }
        if (!line.empty() && line.back() == '\r') {
            line.pop_back();
        }
        auto separator = line.find(':');
        if (separator == std::string::npos) {
            continue;
        }
        auto key = trim(line.substr(0, separator));
        auto value = trim(line.substr(separator + 1));
        std::transform(key.begin(), key.end(), key.begin(), [](unsigned char c) {
            return static_cast<char>(std::tolower(c));
        });
        request.headers[key] = value;
    }

    return true;
}

std::string make_http_response(int status_code, const std::string& status_text, const std::string& body) {
    std::ostringstream oss;
    oss << "HTTP/1.1 " << status_code << " " << status_text << "\r\n";
    oss << "Content-Type: application/json\r\n";
    oss << "Content-Length: " << body.size() << "\r\n";
    oss << "Connection: close\r\n";
    oss << "\r\n";
    oss << body;
    return oss.str();
}

std::string make_http_response_with_content_type(
    int status_code,
    const std::string& status_text,
    const std::string& content_type,
    const std::string& body) {
    std::ostringstream oss;
    oss << "HTTP/1.1 " << status_code << " " << status_text << "\r\n";
    oss << "Content-Type: " << content_type << "\r\n";
    oss << "Content-Length: " << body.size() << "\r\n";
    oss << "Connection: close\r\n";
    oss << "\r\n";
    oss << body;
    return oss.str();
}

std::string guess_content_type(const std::filesystem::path& path) {
    const auto extension = path.extension().string();
    if (extension == ".html") {
        return "text/html; charset=utf-8";
    }
    if (extension == ".js") {
        return "application/javascript; charset=utf-8";
    }
    if (extension == ".css") {
        return "text/css; charset=utf-8";
    }
    if (extension == ".json") {
        return "application/json; charset=utf-8";
    }
    if (extension == ".svg") {
        return "image/svg+xml";
    }
    if (extension == ".png") {
        return "image/png";
    }
    if (extension == ".jpg" || extension == ".jpeg") {
        return "image/jpeg";
    }
    if (extension == ".ico") {
        return "image/x-icon";
    }
    return "application/octet-stream";
}

std::string read_file_to_string(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    format_check(input.good(), "EmbeddedWebServer failed to open static asset");
    std::ostringstream buffer;
    buffer << input.rdbuf();
    return buffer.str();
}

std::filesystem::path normalize_static_root(const std::string& raw_root) {
    if (raw_root.empty()) {
        return {};
    }
    std::error_code ec;
    auto root = std::filesystem::weakly_canonical(std::filesystem::path(raw_root), ec);
    if (ec) {
        return {};
    }
    return root;
}

std::filesystem::path find_default_static_root() {
    const std::vector<std::filesystem::path> candidates = {
        std::filesystem::current_path() / "bvr_sim" / "web" / "dist",
        std::filesystem::current_path().parent_path() / "bvr_sim" / "web" / "dist",
        std::filesystem::current_path().parent_path().parent_path() / "bvr_sim" / "web" / "dist"
    };

    for (const auto& candidate : candidates) {
        std::error_code ec;
        if (std::filesystem::exists(candidate, ec) && std::filesystem::is_directory(candidate, ec)) {
            return std::filesystem::weakly_canonical(candidate, ec);
        }
    }
    return {};
}

std::filesystem::path resolve_static_request_path(
    const std::filesystem::path& static_root,
    const std::string& request_path) {
    if (static_root.empty()) {
        return {};
    }

    std::string relative_path = request_path;
    const auto query_pos = relative_path.find('?');
    if (query_pos != std::string::npos) {
        relative_path = relative_path.substr(0, query_pos);
    }
    if (relative_path.empty() || relative_path == "/") {
        relative_path = "/index.html";
    }

    format_check(relative_path.front() == '/', "EmbeddedWebServer request path must start with /");
    auto candidate = static_root / relative_path.substr(1);

    std::error_code ec;
    candidate = std::filesystem::weakly_canonical(candidate, ec);
    if (ec) {
        return {};
    }

    const auto root_string = static_root.generic_string();
    const auto candidate_string = candidate.generic_string();
    if (candidate_string.rfind(root_string, 0) != 0) {
        colorful::printHONG("[EmbeddedWebServer] blocked static path traversal");
        SL::get().print("[EmbeddedWebServer] blocked static path traversal");
        check(false, "EmbeddedWebServer detected static path traversal");
    }
    return candidate;
}

}

class EmbeddedWebServer::Impl {
public:
    explicit Impl(EmbeddedWebServer& owner)
        : owner_(owner) {
    }

    ~Impl() {
        stop();
    }

    void start(int port) {
        if (running_.load()) {
            return;
        }

        socket_system_guard();

        SocketHandle listen_socket = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
        format_check(socket_is_valid(listen_socket), "EmbeddedWebServer socket creation failed");

        int reuse = 1;
        setsockopt(listen_socket, SOL_SOCKET, SO_REUSEADDR, reinterpret_cast<const char*>(&reuse), sizeof(reuse));

        sockaddr_in address{};
        address.sin_family = AF_INET;
        address.sin_port = htons(static_cast<uint16_t>(port > 0 ? port : 8765));
        inet_pton(AF_INET, "127.0.0.1", &address.sin_addr);

        int bind_result = bind(listen_socket, reinterpret_cast<sockaddr*>(&address), sizeof(address));
        if (bind_result != 0) {
            close_socket(listen_socket);
            check(false, "EmbeddedWebServer bind failed");
        }

        if (listen(listen_socket, 16) != 0) {
            close_socket(listen_socket);
            check(false, "EmbeddedWebServer listen failed");
        }

        listen_socket_ = listen_socket;
        bound_port_ = port > 0 ? port : 8765;
        running_ = true;
        accept_thread_ = std::thread([this]() { accept_loop(); });
        broadcast_thread_ = std::thread([this]() { broadcast_loop(); });
        SL::get().printf("[EmbeddedWebServer] started on port %d\n", bound_port_);
    }

    void stop() {
        if (!running_.load()) {
            return;
        }
        running_ = false;

        close_socket(listen_socket_);
        listen_socket_ = kInvalidSocket;

        {
            std::lock_guard<std::mutex> lock(ws_clients_mutex_);
            for (auto client : ws_clients_) {
                close_socket(client);
            }
            ws_clients_.clear();
        }

        if (accept_thread_.joinable()) {
            accept_thread_.join();
        }
        if (broadcast_thread_.joinable()) {
            broadcast_thread_.join();
        }
    }

    bool is_running() const noexcept {
        return running_.load();
    }

    int bound_port() const noexcept {
        return bound_port_;
    }

    size_t client_count() const noexcept {
        std::lock_guard<std::mutex> lock(ws_clients_mutex_);
        return ws_clients_.size();
    }

private:
    void accept_loop() {
        while (running_.load()) {
            fd_set read_set;
            FD_ZERO(&read_set);
            FD_SET(listen_socket_, &read_set);
            timeval timeout{};
            timeout.tv_sec = 0;
            timeout.tv_usec = 200000;

            int ready = select(static_cast<int>(listen_socket_) + 1, &read_set, nullptr, nullptr, &timeout);
            if (ready <= 0) {
                continue;
            }

            sockaddr_in client_addr{};
#ifdef _WIN32
            int client_len = sizeof(client_addr);
#else
            socklen_t client_len = sizeof(client_addr);
#endif
            SocketHandle client = accept(listen_socket_, reinterpret_cast<sockaddr*>(&client_addr), &client_len);
            if (!socket_is_valid(client)) {
                continue;
            }

            std::thread([this, client]() {
                handle_client(client);
            }).detach();
        }
    }

    void handle_client(SocketHandle client) {
        HttpRequest request;
        if (!read_http_request(client, request)) {
            close_socket(client);
            return;
        }

        auto upgrade_it = request.headers.find("upgrade");
        bool wants_websocket = upgrade_it != request.headers.end()
            && trim(upgrade_it->second) == "websocket";

        if (wants_websocket) {
            handle_websocket_client(client, request);
            return;
        }

        handle_http_client(client, request);
        close_socket(client);
    }

    void handle_http_client(SocketHandle client, const HttpRequest& request) {
        if (request.path == "/health") {
            auto body = json_compact_dump(make_server_ok("visualization server running"));
            send_all(client, make_http_response(200, "OK", body));
            return;
        }

        if (request.path == "/diagnostics") {
            auto body = json_compact_dump(owner_.diagnostics_provider_ ? owner_.diagnostics_provider_() : make_server_error("diagnostics unavailable"));
            send_all(client, make_http_response(200, "OK", body));
            return;
        }

        if (serve_static_asset(client, request.path)) {
            return;
        }

        auto body = json_compact_dump(make_server_error("endpoint not found"));
        send_all(client, make_http_response(404, "Not Found", body));
    }

    bool serve_static_asset(SocketHandle client, const std::string& request_path) {
        std::filesystem::path static_root;
        {
            std::lock_guard<std::mutex> lock(owner_.callback_mutex_);
            static_root = normalize_static_root(owner_.static_root_);
        }
        if (static_root.empty()) {
            return false;
        }

        const auto target_path = resolve_static_request_path(static_root, request_path);
        if (target_path.empty()) {
            return false;
        }

        std::error_code ec;
        if (!std::filesystem::exists(target_path, ec) || !std::filesystem::is_regular_file(target_path, ec)) {
            return false;
        }

        const auto body = read_file_to_string(target_path);
        return send_all(
            client,
            make_http_response_with_content_type(200, "OK", guess_content_type(target_path), body));
    }

    void handle_websocket_client(SocketHandle client, const HttpRequest& request) {
        auto key_it = request.headers.find("sec-websocket-key");
        if (key_it == request.headers.end()) {
            send_all(client, make_http_response(400, "Bad Request", json_compact_dump(make_server_error("missing websocket key"))));
            close_socket(client);
            return;
        }

        std::ostringstream handshake;
        handshake << "HTTP/1.1 101 Switching Protocols\r\n";
        handshake << "Upgrade: websocket\r\n";
        handshake << "Connection: Upgrade\r\n";
        handshake << "Sec-WebSocket-Accept: " << websocket_accept_key(key_it->second) << "\r\n";
        handshake << "\r\n";

        if (!send_all(client, handshake.str())) {
            close_socket(client);
            return;
        }

        {
            std::lock_guard<std::mutex> lock(ws_clients_mutex_);
            ws_clients_.insert(client);
        }

        send_snapshot(client);

        while (running_.load()) {
            std::string payload;
            bool close_requested = false;
            if (!recv_ws_frame(client, payload, close_requested)) {
                break;
            }
            if (close_requested) {
                break;
            }
            auto response = parse_and_submit_command(payload);
            if (!send_all(client, build_ws_frame(json_compact_dump(response)))) {
                break;
            }
        }

        {
            std::lock_guard<std::mutex> lock(ws_clients_mutex_);
            ws_clients_.erase(client);
        }
        close_socket(client);
    }

    json::JSON parse_and_submit_command(const std::string& payload) {
        json::JSON parsed;
        try {
            parsed = json::JSON::Load(payload);
        } catch (...) {
            return make_server_error("invalid json payload");
        }

        if (parsed.JSONType() != json::JSON::Class::Object) {
            return make_server_error("command payload must be object");
        }
        if (!parsed.hasKey("kind", json::JSON::Class::String)) {
            return make_server_error("missing string kind");
        }

        auto kind = telemetry_command_kind_from_string(parsed.at("kind").ToString());
        if (!kind.has_value()) {
            return make_server_error("unknown command kind");
        }

        TelemetryCommand command;
        command.kind = *kind;
        if (parsed.hasKey("target_uid", json::JSON::Class::String)) {
            command.target_uid = parsed.at("target_uid").ToString();
        }
        if (parsed.hasKey("payload")) {
            command.payload = parsed.at("payload");
        }

        if (!owner_.command_submitter_) {
            return make_server_error("command submitter unavailable");
        }

        owner_.command_submitter_(command);
        return make_server_ok("command queued");
    }

    void broadcast_loop() {
        while (running_.load()) {
            std::vector<SocketHandle> clients_copy;
            {
                std::lock_guard<std::mutex> lock(ws_clients_mutex_);
                for (auto client : ws_clients_) {
                    clients_copy.push_back(client);
                }
            }

            for (auto client : clients_copy) {
                send_snapshot(client);
            }

            std::this_thread::sleep_for(std::chrono::milliseconds(50));
        }
    }

    void send_snapshot(SocketHandle client) {
        if (!owner_.snapshot_provider_) {
            return;
        }
        auto frame = build_ws_frame(json_compact_dump(owner_.snapshot_provider_()));
        if (!send_all(client, frame)) {
            std::lock_guard<std::mutex> lock(ws_clients_mutex_);
            ws_clients_.erase(client);
            close_socket(client);
        }
    }

    EmbeddedWebServer& owner_;
    std::atomic<bool> running_{false};
    SocketHandle listen_socket_ = kInvalidSocket;
    int bound_port_ = 0;
    std::thread accept_thread_;
    std::thread broadcast_thread_;
    mutable std::mutex ws_clients_mutex_;
    std::set<SocketHandle> ws_clients_;
};

EmbeddedWebServer::EmbeddedWebServer()
    : impl_(std::make_shared<Impl>(*this)),
      running_(false),
      port_(0) {
}

EmbeddedWebServer::~EmbeddedWebServer() {
    stop();
}

void EmbeddedWebServer::set_snapshot_provider(JsonProvider provider) {
    std::lock_guard<std::mutex> lock(callback_mutex_);
    snapshot_provider_ = std::move(provider);
}

void EmbeddedWebServer::set_diagnostics_provider(JsonProvider provider) {
    std::lock_guard<std::mutex> lock(callback_mutex_);
    diagnostics_provider_ = std::move(provider);
}

void EmbeddedWebServer::set_command_submitter(CommandSubmitter submitter) {
    std::lock_guard<std::mutex> lock(callback_mutex_);
    command_submitter_ = std::move(submitter);
}

void EmbeddedWebServer::set_static_root(const std::string& static_root) {
    std::lock_guard<std::mutex> lock(callback_mutex_);
    static_root_ = static_root;
}

void EmbeddedWebServer::start(int port) {
    if (running_.load()) {
        return;
    }
    {
        std::lock_guard<std::mutex> lock(callback_mutex_);
        if (static_root_.empty()) {
            static_root_ = find_default_static_root().string();
        }
    }
    impl_->start(port);
    port_ = impl_->bound_port();
    running_ = true;
}

void EmbeddedWebServer::stop() {
    if (!running_.load()) {
        return;
    }
    impl_->stop();
    running_ = false;
    port_ = 0;
}

bool EmbeddedWebServer::is_running() const noexcept {
    return running_.load();
}

int EmbeddedWebServer::get_port() const noexcept {
    return port_;
}

std::string EmbeddedWebServer::get_base_url() const {
    if (!is_running()) {
        return "";
    }
    std::ostringstream oss;
    oss << "http://127.0.0.1:" << port_;
    return oss.str();
}

std::string EmbeddedWebServer::get_frontend_url() const {
    if (!is_running() || !is_static_frontend_available()) {
        return "";
    }
    std::ostringstream oss;
    oss << get_base_url() << "/";
    return oss.str();
}

size_t EmbeddedWebServer::get_client_count() const noexcept {
    return impl_->client_count();
}

std::string EmbeddedWebServer::get_static_root() const {
    std::lock_guard<std::mutex> lock(callback_mutex_);
    return static_root_;
}

bool EmbeddedWebServer::is_static_frontend_available() const {
    std::filesystem::path static_root;
    {
        std::lock_guard<std::mutex> lock(callback_mutex_);
        static_root = normalize_static_root(static_root_);
    }
    std::error_code ec;
    return !static_root.empty()
        && std::filesystem::exists(static_root / "index.html", ec)
        && std::filesystem::is_regular_file(static_root / "index.html", ec);
}

}
