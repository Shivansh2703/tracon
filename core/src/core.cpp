// tracon_core: the compiled scheduling decision core (docs/m4_plan.md).
//
// Plain data crosses the seam: RequestView in, queue positions out. Every policy
// is a sort key over one stable-argsort primitive — ties always resolve to the
// lower queue position, so identical inputs give identical selections everywhere.

#include <algorithm>
#include <cstdint>
#include <numeric>
#include <string>
#include <tuple>
#include <vector>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

namespace py = pybind11;

namespace {

constexpr const char* kVersion = "0.1.0";

struct RequestView {
    std::int64_t req;      // caller-side handle (the adapter passes the queue position)
    std::int32_t stream;   // interned stream id
    double ready_ms;       // when the request became ready
    double service_ms;     // traced service time (oracle policies read it)
    std::int32_t waiters;  // chains blocked on this request's completion (phase B)
    std::int32_t warm;     // 1 if the stream's context is resident on a free executor
};

// Stable argsort by key, truncated to k: the primitive every policy builds on.
// std::stable_sort (not sort) is what makes equal keys keep queue order.
template <typename Key>
std::vector<std::size_t> take_k(std::size_t n, long long k, Key key) {
    std::vector<std::size_t> order(n);
    std::iota(order.begin(), order.end(), std::size_t{0});
    std::stable_sort(order.begin(), order.end(),
                     [&](std::size_t a, std::size_t b) { return key(a) < key(b); });
    const auto kept = std::min(n, static_cast<std::size_t>(std::max(k, 0LL)));
    order.resize(kept);
    return order;
}

std::vector<std::size_t> select_fifo(const std::vector<double>& ready_ms, long long k) {
    return take_k(ready_ms.size(), k, [&](std::size_t i) { return ready_ms[i]; });
}

std::vector<std::size_t> select_fifo_views(const std::vector<RequestView>& queue, long long k) {
    return take_k(queue.size(), k, [&](std::size_t i) { return queue[i].ready_ms; });
}

// Oracle-SJF with a starvation guard: requests waiting >= starve_ms jump the line
// oldest-first; the rest order by traced service time.
std::vector<std::size_t> select_sjf(const std::vector<RequestView>& queue, long long k,
                                    double now, double starve_ms) {
    return take_k(queue.size(), k, [&](std::size_t i) {
        const bool starved = now - queue[i].ready_ms >= starve_ms;
        return std::make_tuple(starved ? 0 : 1,
                               starved ? queue[i].ready_ms : queue[i].service_ms);
    });
}

// Dependency-aware: serve the request whose completion unblocks the most waiting
// work (waiters = same-stream turns already arrived + parents gated on a sync
// spawn). Zero-waiter requests and ties fall back to queue order; same guard.
std::vector<std::size_t> select_unblock(const std::vector<RequestView>& queue, long long k,
                                        double now, double starve_ms) {
    return take_k(queue.size(), k, [&](std::size_t i) {
        const bool starved = now - queue[i].ready_ms >= starve_ms;
        return std::make_tuple(starved ? 0 : 1,
                               starved ? queue[i].ready_ms
                                       : -static_cast<double>(queue[i].waiters));
    });
}

// Session-aware: requests whose stream context is warm on a free executor go
// first (avoiding cold-context reload penalties); FIFO within warm/cold groups.
std::vector<std::size_t> select_affinity(const std::vector<RequestView>& queue, long long k,
                                         double now, double starve_ms) {
    return take_k(queue.size(), k, [&](std::size_t i) {
        const bool starved = now - queue[i].ready_ms >= starve_ms;
        return std::make_tuple(starved ? 0 : 1,
                               starved ? queue[i].ready_ms : (queue[i].warm ? 0.0 : 1.0));
    });
}

// The flagship: dependency-aware first (most blocked waiters), session-aware
// second (warm context), FIFO last. No oracle knowledge — unlike SJF it never
// reads service_ms, so a real server could run it as-is.
std::vector<std::size_t> select_tracon(const std::vector<RequestView>& queue, long long k,
                                       double now, double starve_ms) {
    return take_k(queue.size(), k, [&](std::size_t i) {
        const bool starved = now - queue[i].ready_ms >= starve_ms;
        if (starved) return std::make_tuple(0, queue[i].ready_ms, 0.0);
        return std::make_tuple(1, -static_cast<double>(queue[i].waiters),
                               queue[i].warm ? 0.0 : 1.0);
    });
}

}  // namespace

PYBIND11_MODULE(tracon_core, m) {
    m.doc() = "tracon compiled scheduling core: RequestView in, queue positions out";
    m.def("version", [] { return std::string(kVersion); });

    py::class_<RequestView>(m, "RequestView")
        .def(py::init([](std::int64_t req, std::int32_t stream, double ready_ms,
                         double service_ms, std::int32_t waiters, std::int32_t warm) {
                 return RequestView{req, stream, ready_ms, service_ms, waiters, warm};
             }),
             py::arg("req"), py::arg("stream"), py::arg("ready_ms"), py::arg("service_ms"),
             py::arg("waiters") = 0, py::arg("warm") = 0)
        .def_readwrite("req", &RequestView::req)
        .def_readwrite("stream", &RequestView::stream)
        .def_readwrite("ready_ms", &RequestView::ready_ms)
        .def_readwrite("service_ms", &RequestView::service_ms)
        .def_readwrite("waiters", &RequestView::waiters)
        .def_readwrite("warm", &RequestView::warm);

    m.def("select_fifo", &select_fifo, py::arg("ready_ms"), py::arg("k"));
    m.def("select_fifo_views", &select_fifo_views, py::arg("queue"), py::arg("k"));
    m.def("select_sjf", &select_sjf, py::arg("queue"), py::arg("k"), py::arg("now"),
          py::arg("starve_ms"));
    m.def("select_unblock", &select_unblock, py::arg("queue"), py::arg("k"), py::arg("now"),
          py::arg("starve_ms"));
    m.def("select_affinity", &select_affinity, py::arg("queue"), py::arg("k"), py::arg("now"),
          py::arg("starve_ms"));
    m.def("select_tracon", &select_tracon, py::arg("queue"), py::arg("k"), py::arg("now"),
          py::arg("starve_ms"));
}
