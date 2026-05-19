#pragma once
#include <vector>
#include <stdexcept>
#include <algorithm>
#include "check.hxx"
#include "colorful.hxx"
#include "json.hpp"

class InterpTable {
public:
    InterpTable(const std::vector<double>& x, const std::vector<double>& y)
        : x_(x), y_(y)
    {
        check(x.size(), "InterpTable: x and y cannot be empty");
        check(x.size() == y.size(), "InterpTable: x and y must have the same size");
        // check x is sorted in ascending order
        for (size_t i = 1; i < x.size(); ++i) { 
            check(x[i] > x[i-1], "InterpTable: x must be sorted in ascending order");
        }
    }

    double interpolate(double x) const {
        const size_t n = x_.size();

        if (n == 1) {
            return y_[0];  
        }

        if (x <= x_.front()) {
            // colorful::printHONG("InterpTable: x" + std::to_string(x) + " is out of range");
            // const double x0 = x_[0], x1 = x_[1];
            // const double y0 = y_[0], y1 = y_[1];
            // return y0 + (x - x0) * (y1 - y0) / (x1 - x0);
            return y_.front();
        }

        if (x >= x_.back()) {
            // colorful::printHONG("InterpTable: x" + std::to_string(x) + " is out of range");
            // const double x0 = x_[n-2], x1 = x_[n-1];
            // const double y0 = y_[n-2], y1 = y_[n-1];
            // return y0 + (x - x0) * (y1 - y0) / (x1 - x0);
            return y_.back();
        }

        auto it = std::lower_bound(x_.begin(), x_.end(), x);
        const size_t i = std::distance(x_.begin(), it);
        const double x0 = x_[i-1], x1 = x_[i];
        const double y0 = y_[i-1], y1 = y_[i];
        return y0 + (x - x0) * (y1 - y0) / (x1 - x0);
    }

    const std::vector<double>& getX() const { return x_; }
    const std::vector<double>& getY() const { return y_; }

    json::JSON to_json() const {
        json::JSON j = json::JSON::Make(json::JSON::Class::Object);
        json::JSON x_arr = json::JSON::Make(json::JSON::Class::Array);
        json::JSON y_arr = json::JSON::Make(json::JSON::Class::Array);
        for (size_t i = 0; i < x_.size(); ++i) {
            x_arr.append(x_[i]);
            y_arr.append(y_[i]);
        }
        j["x"] = x_arr;
        j["y"] = y_arr;
        return j;
    }

    static InterpTable from_json(const json::JSON& j) {
        check(j.hasKey("x") && j.hasKey("y"), "InterpTable::from_json: missing 'x' or 'y' key");
        std::vector<double> x, y;
        for (auto& v : j.at("x").ArrayRange())
            x.push_back(v.IsFloating() ? v.ToFloat() : static_cast<double>(v.ToInt()));
        for (auto& v : j.at("y").ArrayRange())
            y.push_back(v.IsFloating() ? v.ToFloat() : static_cast<double>(v.ToInt()));
        return InterpTable(x, y);
    }

private:
    std::vector<double> x_; 
    std::vector<double> y_;
};