#pragma once
#include <vector>
#include <stdexcept>
#include <algorithm>
#include "check.hxx"
#include "colorful.hxx"

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

private:
    std::vector<double> x_; 
    std::vector<double> y_;
};