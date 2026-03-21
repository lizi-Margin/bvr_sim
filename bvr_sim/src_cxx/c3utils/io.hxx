#pragma once

#include <iostream>
#include <typeinfo>
#include <string>
#include <cmath>
#include <regex>
#include "def.hxx"


namespace c3utils {
	//  IO  //
	// template <std::size_t N> constexpr std::size_t cstrlen(const char(&str)[N]) noexcept { return N - 1; }

	constexpr const char LOG_LEFT_BRACKET[] = "[";
	constexpr const char LOG_RIGHT_BRACKET[] = "]";
	constexpr std::size_t LOG_LEFT_BRACKET_LEN = 1;
	constexpr std::size_t LOG_RIGHT_BRACKET_LEN = 1;
	// constexpr std::size_t LOG_LEFT_BRACKET_LEN = cstrlen(LOG_LEFT_BRACKET);
	// constexpr std::size_t LOG_RIGHT_BRACKET_LEN = cstrlen(LOG_RIGHT_BRACKET);

	//print as python
	template<typename T>
	void print(const T& value) noexcept 
	{
		std::cout << value << std::endl;
	}
	template<typename First, typename... Rest>
	void print(const First& first, const Rest&... rest) noexcept 
	{
		std::cout << first << " ";
		print(rest...);
	}

	//lprint as python
	inline std::string _lprint_core(const std::string& who, const std::string& content) noexcept
	{
		std::string buff; buff.reserve(LOG_LEFT_BRACKET_LEN + who.size() + LOG_RIGHT_BRACKET_LEN + 2 + content.size());
		buff.append(LOG_LEFT_BRACKET);
		if (who.empty())
		{
			buff.append("UNKNOWN");
		} else {
			buff.append(who);
		}
		buff.append(LOG_RIGHT_BRACKET).append(" ");

		if (content.empty()) 
		{
			buff.append("NO_CONTENT");
		} else {
			buff.append(content);
		}
		buff.append("\n");
		return buff;
	}
	template <typename T>
	inline std::string lprint_(const T& who_, const std::string& content) noexcept
	{
		const std::type_info& type = typeid(who_);
		std::string who; who.reserve(static_cast<size_t>(9 + 37));  //37: class c3utils::Vector3 const * __ptr64
		who.append("cxxtype(").append(type.name()).append(")");
		return _lprint_core(std::regex_replace(who, std::regex(" "), "-"), content);
	}

	//print out the buff directly
	template <typename T>
	void lprint(const T& who_, const std::string& content) noexcept
	{
		print(lprint_(who_, content));
	}
	template <typename T>
	void lprintw(const T& who_, const std::string& content) noexcept
	{
		std::cerr << "Warning: " << lprint_(who_, content) << std::endl;
	}

	//specify the const string
	template <>
	inline std::string lprint_<std::string>(const std::string& who, const std::string& content) noexcept
	{
		return _lprint_core(who, content);
	}

	//specify the const char[N]
	template <std::size_t N>
	inline std::string lprint_(const char(&who_)[N], const std::string& content) noexcept
	{
		return _lprint_core(std::string(who_), content);
	}


	inline std::string round_str(float64_t f, unsigned int dec = 2) noexcept
	{
		float64_t multi = std::pow(10., dec);
		float64_t rounded = std::round(f * multi) / multi;

		//std::ostringstream oss;
		//oss << std::fixed << std::setprecision(dec) << rounded;
		//return oss.str();

		long long int_part = static_cast<long long>(rounded);
		float64_t dec_part = std::abs(rounded - int_part);

		std::string result = std::to_string(int_part);
		if (dec > 0)
		{
			result.reserve(static_cast<size_t>(result.size() + 1 + dec));
			result += '.';
			std::string dec_str = std::to_string(static_cast<long long>(dec_part * multi));

			if (dec_str.size() < dec)
			{
				dec_str = std::string(dec - dec_str.size(), '0') + dec_str;
			}
			result.append(dec_str);
		}
		return result;
	}
}