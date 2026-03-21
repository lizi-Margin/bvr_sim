#include <signal.h>
#include <iostream>
#include <cpptrace/cpptrace.hpp>
#include "trace.hxx"


void register_trace() {
    cpptrace::register_terminate_handler();
    signal(SIGSEGV, handle_segnal);
    // signal(SIGTERM, handle_segnal);
    // signal(SIGINT, handle_segnal);    // 2  - 中断 (Ctrl+C)
    
    // signal(SIGILL, handle_segnal);    // 4  - 非法指令
    // signal(SIGABRT, handle_segnal);   // 6  - 中止
    // signal(SIGFPE, handle_segnal);    // 8  - 浮点异常
}


void handle_segnal(int signalCode) {
    std::cerr << "Error: Program received signal " << signalCode << " (Segmentation Fault)" << std::endl;
    std::cout << "Error: Program received signal " << signalCode << " (Segmentation Fault)" << std::endl;
    // Generate and print the stack trace using cpptrace
    cpptrace::generate_trace().print();

    // Re-raise the signal for default OS handling (e.g., core dump)
    signal(signalCode, SIG_DFL);
    raise(signalCode);
}