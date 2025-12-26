#include <iostream>
#include <stdlib.h>
#include <random>
#include <thread>
#include <chrono>
#include "c3utils.hxx"


#define de(arg) ::std::cout << arg << ::std::endl;

void test_NEUvec_to_self() {
    c3u::Vector3 neu_vec(1.0, 2.0, 3.0);
    double roll = 0.1, pitch = 0.2, yaw = 0.3;
    c3u::Vector3 result = c3u::NEU_to_self(neu_vec, roll, pitch, yaw);
    // 打印结果
    std::cout << "NEU_to_self result: (" << result[0] << ", " << result[1] << ", " << result[2] << ")\n";
}

void test_NEU_to_self() {
    std::array<double, 3> neu_to = {1.0, 2.0, 3.0};
    std::array<double, 3> neu_from = {0.0, 0.0, 0.0};
    double roll = 0.1, pitch = 0.2, yaw = 0.3;
    auto result = c3u::NEU_to_self(c3u::Vector3(neu_to), c3u::Vector3(neu_from), roll, pitch, yaw);

    // 打印结果
    std::cout << "NEU_to_self result: (" << result[0] << ", " << result[1] << ", " << result[2] << ")\n";
}

void test_NEU_to_NED() {
    std::array<double, 3> neu_to{1.0, 2.0, 12000.0};
    auto result = c3u::NEU_to_NED(c3u::Vector3(neu_to));

    // 打印结果
    std::cout << "NEU_to_NED result: (" << result[0] << ", " << result[1] << ", " << result[2] << ")\n";
}

void test_LLA_to_ECEF() {
    std::array<double, 3> lla_to = {1.0, 2.0, 3.0};
    auto result = c3u::LLA_to_ECEF(lla_to);

    // 打印结果
    std::cout << "LLA_to_ECEF result: (" << result[0] << ", " << result[1] << ", " << result[2] << ")\n";
}

void test_LLA_to_NWU() {
    std::array<double, 3> lla_to = {1.0, 2.0, 3.0};
    std::array<double, 3> lla_from = {0.0, 0.0, 0.0};
    auto result = c3u::LLA_to_NWU(c3u::Vector3(lla_to), c3u::Vector3(lla_from));

    // 打印结果
    std::cout << "LLA_to_NWU result: (" << result[0] << ", " << result[1] << ", " << result[2] << ")\n";
}

int main() {
    // 测试旋转
    std::cout << "Testing 3D transformations..." << std::endl;
    c3u::Vector3 v1(1.0, 0.0, 0.0);
    std::cout << "Initial Vector: " << v1 << std::endl;

    // 旋转 180 度 (PI) 绕 Z 轴
    v1.rotate_xyz_fix(0, 0, c3u::pi);
    std::cout << "Rotated 180 degrees around Z-axis: " << v1 << std::endl;

    // 反向旋转 180 度 (PI) 绕 Z 轴
    v1.rev_rotate_xyz_fix(0, 0, c3u::pi);
    std::cout << "Reversed rotated 180 degrees around Z-axis: " << v1 << std::endl;

    // 测试 get_angle 方法
    std::cout << "\nTesting get_angle() method..." << std::endl;
    c3u::Vector3 v2(0.0, 1.0, 0.0);
    std::cout << "Vector1: " << v1 << std::endl;
    std::cout << "Vector2: " << v2 << std::endl;

    double angle = v1.get_angle(v2);
    std::cout << "Angle between Vector1 and Vector2: " << angle << " radians" << std::endl;

    // 测试其他旋转方法
    std::cout << "\nTesting other rotation methods..." << std::endl;
    c3u::Vector3 v3(1.0, 0.0, 0.0);
    v3.rotate_zyx_self(c3u::pi / 2, c3u::pi / 2, c3u::pi / 2);
    std::cout << "Rotated 90 degrees around each axis (ZYX): " << v3 << std::endl;

    v3.rev_rotate_zyx_self(c3u::pi / 2, c3u::pi / 2, c3u::pi / 2);
    std::cout << "Reversed rotated 90 degrees around each axis (ZYX): " << v3 << std::endl;

    v3.rotate_xyz_self(c3u::pi / 2, c3u::pi / 2, c3u::pi / 2);
    std::cout << "Rotated 90 degrees around each axis (XYZ): " << v3 << std::endl;

    v3.rev_rotate_xyz_self(c3u::pi / 2, c3u::pi / 2, c3u::pi / 2);
    std::cout << "Reversed rotated 90 degrees around each axis (XYZ): " << v3 << std::endl;


    std::cout << std::endl;


    test_NEUvec_to_self();
    test_NEU_to_self();
    test_NEU_to_NED();
    test_LLA_to_ECEF();
    test_LLA_to_NWU();
    std::cout << std::endl;


    c3u::Vector3 v_1(1.0, -1.0, 0.5);
    std::cout << "Initial Vector: " << v_1 << std::endl;

    std::cout << "v_1 - v_1: " << v_1 - v_1 << std::endl;
    std::cout << "v_1 + v_1: " << v_1 + v_1 << std::endl;


    using namespace c3u;
    std::cout << std::endl;
    std::cout << "mach 1 on 0m: " << mps_to_kn(get_mps(1, 0)) << std::endl;
    std::cout << "mach 1 on 5000m: " << mps_to_kn(get_mps(1, 5000)) << std::endl;
    std::cout << "mach 1 on 10000m: " << mps_to_kn(get_mps(1, 1e4)) << std::endl;
    std::cout << std::endl;


    c3u::Vector3 v_2(0, 1, 2);
    std::cout << "Initial Vector: " << v_2 << std::endl;
    std::cout << "module " << v_2.get_module() << std::endl;
    std::cout << "module 2d " << make_vector2(v_2).get_module() << std::endl;
    auto res_angle3 = v_2.get_rotate_angle_fix();
    std::cout << "get rotate angel " << res_angle3[0] / c3u::pi * 180 << " " << res_angle3[1] / c3u::pi * 180 << " " << res_angle3[2] / c3u::pi * 180 << std::endl;
#ifndef FOR_PYTHON
    std::cout << "Rotate Vector: " << Vector3(1, 0, 0).prod(v_2.get_module()).rotate_xyz_fix(res_angle3) << std::endl;
#endif //FOR_PYTHON

    c3u::Vector3 test_get_v(1, 2, 3);
    c3u::Vector3 test_set_v(3, 2, 1);
    std::cout << "test_get_v" << std::endl;
    for (size_t i = 0; i < 3; i += 1) {
        std::cout << "\t" << i << " : " << test_get_v[i] << std::endl;
    }

    std::cout << "test_set_v" << std::endl;
    std::cout << "original" << std::endl;
    for (size_t i = 0; i < 3; i += 1) {
        std::cout << "\t" << i << " : " << test_set_v[i] << std::endl;
        test_set_v[i] = test_get_v[i];
    }
    std::cout << "modified, set the same value as test_get_v" << std::endl;
    for (size_t i = 0; i < 3; i += 1) {
        std::cout << "\t" << i << " : " << test_set_v[i] << std::endl;
    }
    
    c3u::Vector3 test_op_a(1, 2, 3);
    c3u::Vector3 test_op_b(3, 2, 1);
    std::cout << std::endl << "Now test new operators of the Vector3" << std::endl;
    std::cout << "test_op_a: " << test_op_a << std::endl;
    std::cout << "test_op_b: " << test_op_b << std::endl;
    std::cout << "test_op_a - test_op_b: " << (test_op_a - test_op_b) << std::endl;
    std::cout << "test_op_a + test_op_b: " << (test_op_a + test_op_b) << std::endl;
    std::cout << "test_op_a == test_op_b: " << (test_op_a == test_op_b) << std::endl;

    std::cout << std::endl << "Now test new io functions" << std::endl;
    c3u::Vector3 test_io_vec(1, 2, 3);
    std::cout << "test_io_vec: " << test_io_vec << std::endl;
    c3u::print("test_io_vec.repr(): ", test_io_vec.repr());
    c3u::print("test_io_vec.str(): ", test_io_vec.str());
    c3u::print("lprintw");
    c3u::lprintw("WHO", "dododo");
    c3u::print("lprint");
    c3u::lprint("WHO", "dododo");





    std::random_device rd;
    std::mt19937 gen(rd());
    std::uniform_real_distribution<> dis(-100.0, 100.0);
    std::array<c3u::float64_t, 3> v3_arr{};
    for (size_t _ = 0; _ < 20; _ += 1)
    {
        for (int i = 0; i < 3; ++i) 
        {
            v3_arr[i] = dis(gen);
        }
        print('\n');
        print(v3_arr[0], v3_arr[1], v3_arr[2]);
        print(c3u::Vector3(v3_arr));
        print(c3u::Vector3(v3_arr).repr());
        std::this_thread::sleep_for(std::chrono::microseconds(500 * 1000));
    }


    //system("pause");
    return 0;
}
