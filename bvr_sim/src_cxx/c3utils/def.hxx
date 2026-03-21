#pragma once

// #include "external/Eigen/Dense"
// #include <eigen3/Eigen/Dense>

#if defined(_MSC_VER) || defined(WIN64) || defined(_WIN64) || defined(__WIN64__) || defined(WIN32) || defined(_WIN32) || defined(__WIN32__) || defined(__NT__)
#  define DLL_EXPORT __declspec(dllexport)
#  define DLL_IMPORT __declspec(dllimport)
#else
#  define DLL_EXPORT __attribute__((visibility("default")))
#  define DLL_IMPORT __attribute__((visibility("default")))
#endif



namespace c3utils {
	// constexpr long double pi = 3.141592653589793238462643383279502884197169399375105820974944592307816406L;
	constexpr double pi = 3.141592653589793238462643383279502884197169399375105820974944592307816406L;
	typedef double float64_t;

	constexpr float64_t WGS84_a = 6378137.0;
	constexpr float64_t WGS84_b = 6356752.3142;
	constexpr float64_t WGS84_f = 1.0 / 298.257223565;
	constexpr float64_t WGS84_e2 = WGS84_f * (2.0 - WGS84_f);

	constexpr float64_t EARTH_RADIUS_MEAN = 6371000.0;
}

// #define FOR_PYTHON
