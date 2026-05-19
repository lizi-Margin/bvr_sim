#pragma once

#include <iostream>

namespace colorful {

template<typename T, typename... Args>
void print(const T& first, const Args&... args) {
    std::cout << first;
    ((std::cout << " " << args), ...);
    std::cout << std::endl;
}

template<typename T, typename... Args>
void printHONG(const T& first, const Args&... args) {
    std::cout << "\033[0;31m" << first;
    ((std::cout << " " << args), ...);
    std::cout << "\033[0m" << std::endl;
}

template<typename T, typename... Args>
void printLV(const T& first, const Args&... args) {
    std::cout << "\033[0;32m" << first;
    ((std::cout << " " << args), ...);
    std::cout << "\033[0m" << std::endl;
}

template<typename T, typename... Args>
void printHUANG(const T& first, const Args&... args) {
    std::cout << "\033[0;33m" << first;
    ((std::cout << " " << args), ...);
    std::cout << "\033[0m" << std::endl;
}

template<typename T, typename... Args>
void printLAN(const T& first, const Args&... args) {
    std::cout << "\033[0;34m" << first;
    ((std::cout << " " << args), ...);
    std::cout << "\033[0m" << std::endl;
}

template<typename T, typename... Args>
void printZI(const T& first, const Args&... args) {
    std::cout << "\033[0;35m" << first;
    ((std::cout << " " << args), ...);
    std::cout << "\033[0m" << std::endl;
}

template<typename T, typename... Args>
void printDIAN(const T& first, const Args&... args) {
    std::cout << "\033[0;36m" << first;
    ((std::cout << " " << args), ...);
    std::cout << "\033[0m" << std::endl;
}

template<typename T, typename... Args>
void printLIANGHONG(const T& first, const Args&... args) {
    std::cout << "\033[1;31m" << first;
    ((std::cout << " " << args), ...);
    std::cout << "\033[0m" << std::endl;
}

template<typename T, typename... Args>
void printLIANGLV(const T& first, const Args&... args) {
    std::cout << "\033[1;32m" << first;
    ((std::cout << " " << args), ...);
    std::cout << "\033[0m" << std::endl;
}

template<typename T, typename... Args>
void printLIANGHUANG(const T& first, const Args&... args) {
    std::cout << "\033[1;33m" << first;
    ((std::cout << " " << args), ...);
    std::cout << "\033[0m" << std::endl;
}

template<typename T, typename... Args>
void printLIANGLAN(const T& first, const Args&... args) {
    std::cout << "\033[1;34m" << first;
    ((std::cout << " " << args), ...);
    std::cout << "\033[0m" << std::endl;
}

template<typename T, typename... Args>
void printLIANGZI(const T& first, const Args&... args) {
    std::cout << "\033[1;35m" << first;
    ((std::cout << " " << args), ...);
    std::cout << "\033[0m" << std::endl;
}

template<typename T, typename... Args>
void printLIANGDIAN(const T& first, const Args&... args) {
    std::cout << "\033[1;36m" << first;
    ((std::cout << " " << args), ...);
    std::cout << "\033[0m" << std::endl;
}

}
