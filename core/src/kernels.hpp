// tracon scheduling kernels — the single source of truth for every transport.
// The pybind11 module (core.cpp) and the Go gRPC service (go/core, via cgo)
// compile this same header, so both seams make identical decisions by
// construction. Every policy is a sort key over one stable-argsort primitive:
// ties always resolve to the lower queue position.

#pragma once

#include <algorithm>
#include <cstdint>
#include <numeric>
#include <tuple>
#include <vector>

namespace tracon {

constexpr const char* kVersion = "0.1.0";

struct RequestView {
    std::int64_t req;      // caller-side handle (adapters pass the queue position)
    std::int32_t stream;   // interned stream id
    double ready_ms;       // when the request became ready
    double service_ms;     // traced service time (oracle policies read it)
    std::int32_t waiters;  // chains blocked on this request's completion
    std::int32_t warm;     // 1 if the stream's context is resident on a free executor
};

// Stable argsort by key, truncated to k: the primitive every policy builds on.
// std::stable_sort (not sort) is what makes equal keys keep queue order.
template <typename Key>
inline std::vector<std::size_t> take_k(std::size_t n, long long k, Key key) {
    std::vector<std::size_t> order(n);
    std::iota(order.begin(), order.end(), std::size_t{0});
    std::stable_sort(order.begin(), order.end(),
                     [&](std::size_t a, std::size_t b) { return key(a) < key(b); });
    const auto kept = std::min(n, static_cast<std::size_t>(std::max(k, 0LL)));
    order.resize(kept);
    return order;
}

inline std::vector<std::size_t> select_fifo(const std::vector<double>& ready_ms, long long k) {
    return take_k(ready_ms.size(), k, [&](std::size_t i) { return ready_ms[i]; });
}

inline std::vector<std::size_t> select_fifo_views(const std::vector<RequestView>& queue,
                                                  long long k) {
    return take_k(queue.size(), k, [&](std::size_t i) { return queue[i].ready_ms; });
}

// Oracle-SJF with a starvation guard: requests waiting >= starve_ms jump the line
// oldest-first; the rest order by traced service time.
inline std::vector<std::size_t> select_sjf(const std::vector<RequestView>& queue, long long k,
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
inline std::vector<std::size_t> select_unblock(const std::vector<RequestView>& queue,
                                               long long k, double now, double starve_ms) {
    return take_k(queue.size(), k, [&](std::size_t i) {
        const bool starved = now - queue[i].ready_ms >= starve_ms;
        return std::make_tuple(starved ? 0 : 1,
                               starved ? queue[i].ready_ms
                                       : -static_cast<double>(queue[i].waiters));
    });
}

// Session-aware: requests whose stream context is warm on a free executor go
// first (avoiding cold-context reload penalties); FIFO within warm/cold groups.
inline std::vector<std::size_t> select_affinity(const std::vector<RequestView>& queue,
                                                long long k, double now, double starve_ms) {
    return take_k(queue.size(), k, [&](std::size_t i) {
        const bool starved = now - queue[i].ready_ms >= starve_ms;
        return std::make_tuple(starved ? 0 : 1,
                               starved ? queue[i].ready_ms : (queue[i].warm ? 0.0 : 1.0));
    });
}

// The flagship: dependency-aware first (most blocked waiters), session-aware
// second (warm context), FIFO last. No oracle knowledge — unlike SJF it never
// reads service_ms, so a real server could run it as-is.
inline std::vector<std::size_t> select_tracon(const std::vector<RequestView>& queue, long long k,
                                              double now, double starve_ms) {
    return take_k(queue.size(), k, [&](std::size_t i) {
        const bool starved = now - queue[i].ready_ms >= starve_ms;
        if (starved) return std::make_tuple(0, queue[i].ready_ms, 0.0);
        return std::make_tuple(1, -static_cast<double>(queue[i].waiters),
                               queue[i].warm ? 0.0 : 1.0);
    });
}

// Kernel ids shared across the C ABI and gRPC transport.
enum class Kernel : std::int32_t {
    kFifo = 0,
    kSjf = 1,
    kUnblock = 2,
    kAffinity = 3,
    kTracon = 4,
};

inline std::vector<std::size_t> select_by_kernel(Kernel kernel,
                                                 const std::vector<RequestView>& queue,
                                                 long long k, double now, double starve_ms) {
    switch (kernel) {
        case Kernel::kFifo:
            return select_fifo_views(queue, k);
        case Kernel::kSjf:
            return select_sjf(queue, k, now, starve_ms);
        case Kernel::kUnblock:
            return select_unblock(queue, k, now, starve_ms);
        case Kernel::kAffinity:
            return select_affinity(queue, k, now, starve_ms);
        case Kernel::kTracon:
            return select_tracon(queue, k, now, starve_ms);
    }
    return {};
}

}  // namespace tracon
