#include "vector.hxx"
#include "../extern/eigen/Eigen/Dense"
#include <array>
#include <string>
#include <stdexcept>
#include "def.hxx"
#include "io.hxx"

using c3utils::Vector3;
using c3utils::float64_t;

Vector3::Vector3(const Eigen::Vector3d& vec) noexcept : vec(vec) {}

Vector3::Vector3(float64_t x, float64_t y, float64_t z) noexcept : vec(x, y, z) {}

Vector3::Vector3(const std::array<float64_t,3>& arr3) noexcept
{
    vec = Eigen::Vector3d(arr3[0], arr3[1], arr3[2]);
}

Vector3::Vector3(const Vector3& copy_target) noexcept :vec(copy_target.vec){}

#ifndef FOR_PYTHON
Vector3& Vector3::rotate_xyz_fix(std::array<float64_t, 3>& rotate_ang_arr_xyz) noexcept 
{
    return rotate_xyz_fix(rotate_ang_arr_xyz[0],rotate_ang_arr_xyz[1],rotate_ang_arr_xyz[2] );
}
#endif

Vector3& Vector3::rotate_xyz_fix(float64_t ax, float64_t ay, float64_t az) noexcept
{
    Eigen::Matrix3d mx, my, mz;
    mx = Eigen::AngleAxisd(ax, Eigen::Vector3d::UnitX()).toRotationMatrix();
    my = Eigen::AngleAxisd(ay, Eigen::Vector3d::UnitY()).toRotationMatrix();
    mz = Eigen::AngleAxisd(az, Eigen::Vector3d::UnitZ()).toRotationMatrix();
    vec = mz * my * mx * vec;
    return *this;
}

Vector3& Vector3::rev_rotate_xyz_fix(float64_t ax, float64_t ay, float64_t az) noexcept
{
    Eigen::Matrix3d mx, my, mz;
    mx = Eigen::AngleAxisd(-ax, Eigen::Vector3d::UnitX()).toRotationMatrix();
    my = Eigen::AngleAxisd(-ay, Eigen::Vector3d::UnitY()).toRotationMatrix();
    mz = Eigen::AngleAxisd(-az, Eigen::Vector3d::UnitZ()).toRotationMatrix();
    vec = mx * my * mz * vec;
    return *this;
}



Vector3& Vector3::rotate_xyz_self(float64_t ax, float64_t ay, float64_t az) noexcept
{
    Eigen::Matrix3d mx, my, mz;
    mx = Eigen::AngleAxisd(ax, Eigen::Vector3d::UnitX()).toRotationMatrix();
    my = Eigen::AngleAxisd(ay, Eigen::Vector3d::UnitY()).toRotationMatrix();
    mz = Eigen::AngleAxisd(az, Eigen::Vector3d::UnitZ()).toRotationMatrix();
    vec = mx * my * mz * vec;
    return *this;
}
Vector3& Vector3::rev_rotate_xyz_self(float64_t ax, float64_t ay, float64_t az) noexcept
{
    Eigen::Matrix3d mx, my, mz;
    mx = Eigen::AngleAxisd(-ax, Eigen::Vector3d::UnitX()).toRotationMatrix();
    my = Eigen::AngleAxisd(-ay, Eigen::Vector3d::UnitY()).toRotationMatrix();
    mz = Eigen::AngleAxisd(-az, Eigen::Vector3d::UnitZ()).toRotationMatrix();
    vec = mz * my * mx * vec;
    return *this;
}


Vector3& Vector3::rotate_zyx_self(float64_t ax, float64_t ay, float64_t az) noexcept
{
    Eigen::Matrix3d mx, my, mz;
    mx = Eigen::AngleAxisd(ax, Eigen::Vector3d::UnitX()).toRotationMatrix();
    my = Eigen::AngleAxisd(ay, Eigen::Vector3d::UnitY()).toRotationMatrix();
    mz = Eigen::AngleAxisd(az, Eigen::Vector3d::UnitZ()).toRotationMatrix();
    vec = mz * my * mx * vec;
    return *this;
}
Vector3& Vector3::rev_rotate_zyx_self(float64_t ax, float64_t ay, float64_t az) noexcept
{
    Eigen::Matrix3d mz, my, mx;
    mx = Eigen::AngleAxisd(-ax, Eigen::Vector3d::UnitX()).toRotationMatrix();
    my = Eigen::AngleAxisd(-ay, Eigen::Vector3d::UnitY()).toRotationMatrix();
    mz = Eigen::AngleAxisd(-az, Eigen::Vector3d::UnitZ()).toRotationMatrix();
    vec = mx * my * mz * vec;
    return *this;
}


std::array<float64_t, 3> Vector3::get_rotate_angle_fix()const noexcept 
{
    float64_t vx = this->vec[0];
    float64_t vy = this->vec[1];
    float64_t vz = this->vec[2];

    float64_t alpha = std::atan2(vy, vx);
    float64_t beta = std::atan2(-vz, std::sqrt(vx*vx + vy*vy));
    float64_t gamma = 0;

    return { gamma, beta, alpha };
}


float64_t Vector3::get_angle(const Vector3& other, int pid_set_zero /*= -1*/, int pid_sign_dim /*= -1*/) const
{
    if (pid_set_zero == -1) {
        float64_t dot_product = this->get_dot(other);
        float64_t modules_product = this->get_module(true) * other.get_module(true);
        float64_t ang = dot_product / modules_product;
        if (ang > 1.) ang = 1.;
        if (ang < -1.) ang = -1.;
        return std::acos(ang);
    }

    Vector3 temp(other);
    int set_zero_dim;
    int sign_dim = 1;
    switch (pid_set_zero) {
    case 0:
        set_zero_dim = 0;
        sign_dim = 1;
        break;
    case 1:
        set_zero_dim = 1;
        sign_dim = 2;
        break;
    case 2:
        set_zero_dim = 2;
        sign_dim = 0;
        break;
    default:
        throw std::invalid_argument(lprint_(this, "Invalid pid_set_zero value"));
        return std::numeric_limits<float64_t>::quiet_NaN();
    }

    if (pid_sign_dim != -1) {
        if (0 <= pid_sign_dim && pid_sign_dim < 3) {
            sign_dim = pid_sign_dim;
        }
        else {
            throw std::invalid_argument(lprint_(this, "Invalid pid_sign_dim value"));
            return std::numeric_limits<float64_t>::quiet_NaN();
        }
    }

    temp.vec(set_zero_dim) = 0;

    float64_t dot_product = this->get_prod(temp);
    float64_t modules_product = this->get_module(true) * temp.get_module(true);
    float64_t ang = dot_product / modules_product;
    if (ang > 1) ang = 1;
    if (ang < -1) ang = -1;

    float64_t angle = std::acos(ang);
    if (temp.vec(sign_dim) < 0) {
        angle = -angle;
    }

    return angle;
}


Vector3& Vector3::prod(float64_t x) noexcept
{
    vec *= x;
    return *this;
}

float64_t Vector3::get_prod(const Vector3& other) const noexcept
{
    return this->get_dot(other);
}
float64_t Vector3::get_dot(const Vector3& other) const noexcept
{
    return vec.dot(other.vec);
}

Vector3& Vector3::add(const Vector3& other) noexcept
{
    vec += other.vec;
    return *this;
}

float64_t Vector3::get_module(bool non_zero /*= false*/) const noexcept
{
    float64_t mo = vec.squaredNorm();
    if (non_zero && mo == 0) mo = ::std::numeric_limits<float64_t>::min();
    return std::sqrt(mo);
}

Vector3 Vector3::normalize() const noexcept
{
    return Vector3(*this).prod(1.0 / this->get_module(true));
}

std::array<float64_t,3> Vector3::get_list() const noexcept
{
    return { vec[0], vec[1], vec[2] };
}

std::string Vector3::str() const noexcept
{
    std::string buff; buff.reserve(VECTOR_LEFT_BRACKET_LEN + 2 + 2 + VECTOR_RIGHT_BRACKET_LEN + 18);
    buff.append(VECTOR_LEFT_BRACKET)
        .append(round_str(vec[0]))
        .append(", ")
        .append(round_str(vec[1]))
        .append(", ")
        .append(round_str(vec[2]))
        .append(VECTOR_RIGHT_BRACKET);
    return buff;
}

std::string Vector3::repr() const noexcept
{
    std::string buff; buff.reserve(VECTOR_LEFT_BRACKET_LEN + 2 + 2 + VECTOR_RIGHT_BRACKET_LEN + 18);
    buff.append(round_str(vec[0]))
        .append(", ")
        .append(round_str(vec[1]))
        .append(", ")
        .append(round_str(vec[2]));
    return lprint_(this, buff);
}


