#pragma once

// #include "external/Eigen/Dense"
// #include "extern/eigen/Eigen/Dense"
#include <string>
#include <cmath>
#include <array>

#include "vector.hxx"
#include "def.hxx"
#include "io.hxx"

namespace c3utils {

	/*

		Basic utilities.

	*/
	constexpr inline float64_t deg2rad(float64_t deg) noexcept {
		return deg * pi / 180.0;
	}

	constexpr inline float64_t rad2deg(float64_t rad) noexcept {
		return rad * 180.0 / pi;
	}

	constexpr inline float64_t nm_to_meters(float64_t nm) noexcept {
		return nm * 1852.0;
	}
	constexpr inline float64_t meters_to_nm(float64_t nm) noexcept {
		return nm / 1852.0;
	}

	constexpr inline float64_t mps_to_kn(float64_t mps) noexcept {
		return mps * 1.9438452;
	}
	constexpr inline float64_t kn_to_mps(float64_t kn) noexcept {
		//return kn / 1.9438452;
		return kn *  0.5144442;
	}

	constexpr auto K_C0 = 273.15;
	constexpr inline float64_t K_to_C(float64_t K)noexcept {
		return K - K_C0;
	}
	constexpr inline float64_t C_to_K(float64_t C)noexcept{
		return C + K_C0;
	}

	inline float64_t estimate_temperature_C(float64_t altitude) noexcept {
		const float64_t T0 = 288.15;
		const float64_t L = 0.0065;
		const float64_t tropopause_altitude = 11000.0;
		float64_t ret = 216.65;

		if (altitude <= tropopause_altitude) {
			ret = T0 - L * altitude;
		}
		else if (altitude <= 20000.0) {
			ret = 216.65;
		}

		return K_to_C(ret);
	}

	inline float64_t mach_to_mps(float64_t mach, float64_t temperature_C) noexcept {
        const double gamma = 1.4;
        const double R = 287.05;
        double temperature_K = C_to_K(temperature_C);
        double local_ss = std::sqrt(gamma * R * temperature_K);
        return mach * local_ss;
	}

	inline float64_t get_mps(float64_t mach,float64_t alt) noexcept
	{
		return mach_to_mps(mach, estimate_temperature_C(alt));
	}

	inline float64_t get_mach(float64_t mps, float64_t alt) noexcept
	{
		const double gamma = 1.4;
		const double R = 287.05;
		double temperature_C = estimate_temperature_C(alt);
		double temperature_K = C_to_K(temperature_C);
		double local_ss = std::sqrt(gamma * R * temperature_K);
		return mps / local_ss;
	}

    constexpr inline float64_t meters_to_feet(float64_t meters) noexcept 
	{
        return meters * 3.28084;
    }

    constexpr inline float64_t feet_to_meters(float64_t feet) noexcept 
	{
        return feet / 3.28084;
    }


    inline float64_t abs(float64_t num) noexcept 
	{
        return ::std::abs(num);
    }

    constexpr inline float64_t pwr(float64_t num) noexcept 
	{
        return num * num;
    }

	inline float64_t sin(float64_t num) noexcept 
	{
		return ::std::sin(num);
	}

	inline float64_t cos(float64_t num) noexcept 
	{
		return ::std::cos(num);
	}

    inline float64_t 
	norm(float64_t x, float64_t lower_side = -1.0, float64_t upper_side = 1.0) noexcept 
	{
        if (lower_side > upper_side) lprintw("norm", "'lower_side' should be smaller than 'upper_side'!");
        if (x > upper_side) x = upper_side;
        if (x < lower_side) x = lower_side;
        return x;
    }

    constexpr inline float64_t no_neg(float64_t num) noexcept
	{
        return num<0. ? 0. : num;
    }

    inline float64_t norm_pi(float64_t angle) noexcept
	{
        while (angle > pi) {
            angle -= 2.0 * pi;
        }
        while (angle < -pi) {
            angle += 2.0 * pi;
        }
        return angle;
    }

    // Linear algebra norm function similar to np.linalg.norm
	inline float64_t linalg_norm_vec(const Vector3& vec) noexcept {
		return vec.get_module();
	}

	inline float64_t linalg_norm(const std::array<float64_t, 3>& vec) noexcept {
		return std::sqrt(vec[0] * vec[0] + vec[1] * vec[1] + vec[2] * vec[2]);
	}

	inline float64_t linalg_norm(const std::array<float64_t, 2>& vec) noexcept {
		return std::sqrt(vec[0] * vec[0] + vec[1] * vec[1]);
	}
	

	// template<std::size_t N>
	// inline float64_t linalg_norm(const std::array<float64_t, N>& vec) noexcept {
	// 	float64_t sum_sq = 0.0;
	// 	for (const auto& v : vec) {
	// 		sum_sq += v * v;
	// 	}
	// 	return std::sqrt(sum_sq);
	// }


	/*
	
		Utilities for Vector3/2.
	
	*/

    inline Vector3 
	make_vector3(const Vector2& vector2, float64_t z = 0.) noexcept 
	{
		return Vector3(
			static_cast<float64_t>(vector2[0]),
			static_cast<float64_t>(vector2[1]),
			z
		);
    }

    inline Vector2
	make_vector2(const Vector3& vector3) noexcept 
	{
		return Vector2(
			(vector3[0]),
			(vector3[1])
		);
    }

    inline Vector3 copy(const Vector3& vector3) noexcept 
	{
        return Vector3(vector3);
    }






	/*
	
		3D transformation utilities.
	
	*/

	inline Vector3
    NEU_to_self
    (
		const Vector3& neu_vec,
		float64_t roll, float64_t pitch, float64_t yaw   )  noexcept
	{
		Vector3 intent_vector(neu_vec[0], neu_vec[1], -neu_vec[2]);
		intent_vector.rev_rotate_zyx_self(roll, pitch, yaw);
		intent_vector[2] = -intent_vector[2]; 

		return intent_vector;
    }

	inline ::std::array<float64_t, 3>
    NEU_to_self
    (
		const ::std::array<float64_t,3>& neu_to,
		const ::std::array<float64_t,3>& neu_from ,
		float64_t roll, float64_t pitch, float64_t yaw  ) noexcept 
	{
		auto neu_vec = Vector3(
			neu_to[0] - neu_from[0],
			neu_to[1] - neu_from[1],
			neu_to[2] - neu_from[2]
		);
		return NEU_to_self(neu_vec, roll, pitch, yaw).get_list();	
    }
	inline Vector3	
    NEU_to_self
    (
		const Vector3& neu_to, 
		const Vector3& neu_from ,
		float64_t roll, float64_t pitch, float64_t yaw  ) noexcept 
	{
		auto neu_vec = Vector3(
			neu_to[0] - neu_from[0],
			neu_to[1] - neu_from[1],
			neu_to[2] - neu_from[2]
		);
		return NEU_to_self(neu_vec, roll, pitch, yaw);	
    }



    inline ::std::array<float64_t,3> 
    NEU_to_NED
    (
		const ::std::array<float64_t,3>& neu_to, 	
		const ::std::array<float64_t,3>& neu_from = ::std::array<float64_t,3>{ 0, 0,10000. }   ) 
	{
        // TODO: customized 'mid'
		if (neu_from[0] != 0. || neu_from[1] != 0. || neu_from[2] != 10000.) {
		    throw std::runtime_error(lprint_("NEU_to_NED", "Not implemented for mid other than [0, 0, 10000.]"));
		}

        std::array<float64_t,3> ned(neu_to);
        ned[2] = -(neu_to[2] - neu_from[2]);
		return ned;
	}
	inline Vector3
    NEU_to_NED
    (
		const Vector3& neu_to, 	
		const Vector3& neu_from = Vector3{ 0, 0,10000. }   ) 
	{
		return Vector3(NEU_to_NED(neu_to.get_list(), neu_from.get_list()));
	}


	inline ::std::array<float64_t,3>
	LLA_to_ECEF(const ::std::array<float64_t,3>& lla_to) noexcept
	{
		float64_t N = WGS84_a / sqrt(1 - WGS84_e2 * sin(lla_to[1]) * sin(lla_to[1]));

		::std::array<float64_t,3> ECEF;
		ECEF[0] = (N + lla_to[2]) * cos(lla_to[1]) * cos(lla_to[0]);
		ECEF[1] = (N + lla_to[2]) * cos(lla_to[1]) * sin(lla_to[0]);
		ECEF[2] = (N * (1 - WGS84_e2) + lla_to[2]) * sin(lla_to[1]);
		return ECEF;
	}

	inline ::std::array<float64_t,3>
	ECEF_to_LLA(float64_t x, float64_t y, float64_t z) noexcept
	{
		float64_t lon = ::std::atan2(y, x);
		float64_t p = ::std::sqrt(x*x + y*y);

		float64_t lat = ::std::atan2(z, p * (1 - WGS84_e2));

		for (int i = 0; i < 10; ++i) {
			float64_t N = WGS84_a / ::std::sqrt(1 - WGS84_e2 * ::std::sin(lat) * ::std::sin(lat));
			lat = ::std::atan2(z + WGS84_e2 * N * ::std::sin(lat), p);
		}

		float64_t N = WGS84_a / ::std::sqrt(1 - WGS84_e2 * ::std::sin(lat) * ::std::sin(lat));
		float64_t alt = p / ::std::cos(lat) - N;

		return {lon, lat, alt};
	}

	inline ::std::array<float64_t,3>
	NWU_to_LLA_
	(
		float64_t north, float64_t west, float64_t up,
		float64_t lon_ref, float64_t lat_ref, float64_t alt_ref
	) noexcept
	{
		float64_t east = -west;
		float64_t north_ = north;
		float64_t up_ = up;

		::std::array<float64_t,3> ECEF_ref = LLA_to_ECEF({lon_ref, lat_ref, alt_ref});

		float64_t sin_lon = ::std::sin(lon_ref);
		float64_t cos_lon = ::std::cos(lon_ref);
		float64_t sin_lat = ::std::sin(lat_ref);
		float64_t cos_lat = ::std::cos(lat_ref);

		float64_t dECEF_x = -sin_lon * east + (-sin_lat * cos_lon) * north_ + (cos_lat * cos_lon) * up_;
		float64_t dECEF_y =  cos_lon * east + (-sin_lat * sin_lon) * north_ + (cos_lat * sin_lon) * up_;
		float64_t dECEF_z =  0.0 * east    + (cos_lat) * north_           + (sin_lat) * up_;

		float64_t ECEF_target_x = ECEF_ref[0] + dECEF_x;
		float64_t ECEF_target_y = ECEF_ref[1] + dECEF_y;
		float64_t ECEF_target_z = ECEF_ref[2] + dECEF_z;

		return ECEF_to_LLA(ECEF_target_x, ECEF_target_y, ECEF_target_z);
	}

	inline ::std::array<float64_t,3>
	LLA_to_NWU
	(
		const ::std::array<float64_t,3>& lla_to,
		const ::std::array<float64_t,3>& lla_from    ) noexcept 
	{

		float64_t Delt[3];
		float64_t M[3][3];
		float64_t ENU[3];

		::std::array<float64_t,3> AECF = LLA_to_ECEF(lla_from);
		::std::array<float64_t,3> BECF = LLA_to_ECEF(lla_to);

		Delt[0] = BECF[0] - AECF[0];
		Delt[1] = BECF[1] - AECF[1];
		Delt[2] = BECF[2] - AECF[2];

		M[0][0] = -sin(lla_from[0]);
		M[0][1] = cos(lla_from[0]);
		M[0][2] = 0;
		M[1][0] = -sin(lla_from[1]) * cos(lla_from[0]);
		M[1][1] = -sin(lla_from[1]) * sin(lla_from[0]);
		M[1][2] = cos(lla_from[1]);
		M[2][0] = cos(lla_from[1]) * cos(lla_from[0]);
		M[2][1] = cos(lla_from[1]) * sin(lla_from[0]);
		M[2][2] = sin(lla_from[1]);

		ENU[0] = M[0][0] * Delt[0] + M[0][1] * Delt[1] + M[0][2] * Delt[2];
		ENU[1] = M[1][0] * Delt[0] + M[1][1] * Delt[1] + M[1][2] * Delt[2];
		ENU[2] = M[2][0] * Delt[0] + M[2][1] * Delt[1] + M[2][2] * Delt[2];

		::std::array<float64_t, 3> NWU;
		NWU[0] = ENU[1];
		NWU[1] = -ENU[0];
		NWU[2] = ENU[2];
		return NWU;
	}

	inline Vector3
	LLA_to_NWU
	(
		const Vector3& lla_to,
		const Vector3& lla_from    ) noexcept 
	{
		return Vector3(LLA_to_NWU(lla_to.get_list(),lla_from.get_list()));
	}

	inline ::std::array<float64_t,3>
	NWU_to_LLA_deg
	(
		float64_t north, float64_t west, float64_t up,
		float64_t lon_ref, float64_t lat_ref, float64_t alt_ref
	) noexcept
	{
		float64_t lon_ref_rad = deg2rad(lon_ref);
		float64_t lat_ref_rad = deg2rad(lat_ref);

		auto lla_rad = NWU_to_LLA_(north, west, up, lon_ref_rad, lat_ref_rad, alt_ref);

		float64_t lon = rad2deg(lla_rad[0]);
		float64_t lat = rad2deg(lla_rad[1]);
		float64_t alt = lla_rad[2];

		return {lon, lat, alt};
	}

	inline ::std::array<float64_t,3>
	LLA_to_NWU_deg
	(
		float64_t lon, float64_t lat, float64_t alt,
		float64_t lon_ref, float64_t lat_ref, float64_t alt_ref
	) noexcept
	{
		float64_t lon_rad = deg2rad(lon);
		float64_t lat_rad = deg2rad(lat);
		float64_t lon_ref_rad = deg2rad(lon_ref);
		float64_t lat_ref_rad = deg2rad(lat_ref);

		return LLA_to_NWU(std::array<float64_t,3>{lon_rad, lat_rad, alt}, std::array<float64_t,3>{lon_ref_rad, lat_ref_rad, alt_ref});
	}

	inline ::std::array<float64_t,3>
	NWU_to_LLA_deg_lowacc
	(
		float64_t north, float64_t west, float64_t up,
		float64_t lon_ref, float64_t lat_ref, float64_t alt_ref
	) noexcept
	{
		float64_t east = -west;

		float64_t lat = lat_ref + rad2deg(north / EARTH_RADIUS_MEAN);
		float64_t lon = lon_ref + rad2deg(east / EARTH_RADIUS_MEAN) / ::std::cos(deg2rad(lat_ref));
		float64_t alt = alt_ref + up;

		return {lon, lat, alt};
	}

	inline ::std::array<float64_t,3>
	LLA_to_NWU_deg_lowacc
	(
		float64_t lon, float64_t lat, float64_t alt,
		float64_t lon_ref, float64_t lat_ref, float64_t alt_ref
	) noexcept
	{
		float64_t dlat = deg2rad(lat - lat_ref);
		float64_t dlon = deg2rad(lon - lon_ref);

		float64_t north = dlat * EARTH_RADIUS_MEAN;
		float64_t west = -dlon * EARTH_RADIUS_MEAN * ::std::cos(deg2rad(lat_ref));
		float64_t up = alt - alt_ref;

		return {north, west, up};
	}

	inline ::std::array<float64_t,3>
	velocity_to_euler_NWU(const ::std::array<float64_t,3>& velocity) noexcept
	{
		Vector3 vel_vec(velocity);
		auto angles = vel_vec.get_rotate_angle_fix();
		return {angles[0], angles[1], angles[2]};
	}

	inline ::std::array<float64_t,3>
	velocity_to_euler_NWU(const Vector3& velocity) noexcept
	{
		return velocity.get_rotate_angle_fix();
	}

}

