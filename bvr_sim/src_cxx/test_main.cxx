#include <iostream>
#include <vector>
#include <string>
#include <cmath>
#include <functional>
#include "support/json.hpp"
#include "test_main.hxx"

// Example tests
TEST(Example, BasicAssertion) {
    ASSERT(true);
}

TEST(Example, EqualityCheck) {
    ASSERT_EQ(5.0, 5.0);
}

TEST(Example, NearCheck) {
    ASSERT_NEAR(3.14159, 3.14, 0.01);
}

TEST(Example, RangeCheck) {
    ASSERT_RANGE(5.0, 0.0, 10.0);
}

// Main entry point
int main() {
    TestRegistry::instance().run_all();
    return TestRegistry::instance().get_exit_code();
}
