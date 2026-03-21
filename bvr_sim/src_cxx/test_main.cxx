#include <iostream>
#include <vector>
#include <string>
#include <cmath>
#include <functional>
#include "rubbish_can/json.hpp"

// Test result tracking
struct TestResult {
    std::string test_name;
    bool passed;
    std::string error_msg;
};

class TestRegistry {
public:
    using TestFunc = std::function<void()>;

    static TestRegistry& instance() {
        static TestRegistry registry;
        return registry;
    }

    void register_test(const std::string& module, const std::string& name, TestFunc func) {
        tests.push_back({module + "::" + name, false, ""});
        test_funcs.push_back(func);
    }

    void run_all() {
        std::cout << "\n=== Running C++ Unit Tests ===\n" << std::endl;

        for (size_t i = 0; i < test_funcs.size(); ++i) {
            current_test_idx = i;
            try {
                test_funcs[i]();
                tests[i].passed = true;
                std::cout << "✓ " << tests[i].test_name << std::endl;
            } catch (const std::string& msg) {
                tests[i].passed = false;
                tests[i].error_msg = msg;
                std::cout << "✗ " << tests[i].test_name << std::endl;
                if (!msg.empty()) {
                    std::cout << "  → " << msg << std::endl;
                }
            } catch (const std::exception& e) {
                tests[i].passed = false;
                tests[i].error_msg = e.what();
                std::cout << "✗ " << tests[i].test_name << std::endl;
                std::cout << "  → " << e.what() << std::endl;
            }
        }

        print_summary();
    }

    static void assert_true(bool condition, const std::string& msg) {
        if (!condition) {
            throw msg;
        }
    }

    static void assert_equal_double(double actual, double expected, const std::string& msg) {
        if (actual != expected) {
            throw msg + " (actual=" + std::to_string(actual) + ", expected=" + std::to_string(expected) + ")";
        }
    }

    static void assert_near(double actual, double expected, double tolerance, const std::string& msg) {
        if (std::abs(actual - expected) > tolerance) {
            throw msg + " (actual=" + std::to_string(actual) + ", expected=" + std::to_string(expected) + ", tol=" + std::to_string(tolerance) + ")";
        }
    }

    static void assert_range(double value, double min_val, double max_val, const std::string& msg) {
        if (value < min_val || value > max_val) {
            throw msg + " (value=" + std::to_string(value) + ", range=[" + std::to_string(min_val) + ", " + std::to_string(max_val) + "])";
        }
    }

    int get_exit_code() const {
        for (const auto& test : tests) {
            if (!test.passed) return 1;
        }
        return 0;
    }

private:
    TestRegistry() = default;

    std::vector<TestResult> tests;
    std::vector<TestFunc> test_funcs;
    size_t current_test_idx = 0;

    void print_summary() {
        int passed = 0, total = tests.size();
        for (const auto& test : tests) {
            if (test.passed) passed++;
        }
        std::cout << "\n=== Summary ===" << std::endl;
        std::cout << "Passed: " << passed << "/" << total << std::endl;
        if (passed == total) {
            std::cout << "All tests passed!" << std::endl;
        }
    }
};

// Macro for test registration
#define TEST(ModuleName, TestName) \
    void test_##ModuleName##_##TestName(); \
    namespace { \
        struct ModuleName##_##TestName##_Register { \
            ModuleName##_##TestName##_Register() { \
                TestRegistry::instance().register_test(#ModuleName, #TestName, test_##ModuleName##_##TestName); \
            } \
        }; \
        static ModuleName##_##TestName##_Register ModuleName##_##TestName##_registrar; \
    } \
    void test_##ModuleName##_##TestName()

// Assert macros
#define ASSERT(condition) \
    TestRegistry::assert_true((condition), "ASSERT failed: " #condition)

#define ASSERT_EQ(actual, expected) \
    TestRegistry::assert_equal_double((actual), (expected), "ASSERT_EQ failed: " #actual " == " #expected)

#define ASSERT_NEAR(actual, expected, tolerance) \
    TestRegistry::assert_near((actual), (expected), (tolerance), "ASSERT_NEAR failed: " #actual " near " #expected)

#define ASSERT_RANGE(value, min_val, max_val) \
    TestRegistry::assert_range((value), (min_val), (max_val), "ASSERT_RANGE failed: " #value " in [" #min_val ", " #max_val "]")

// Example tests (can be moved to separate files later)
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
