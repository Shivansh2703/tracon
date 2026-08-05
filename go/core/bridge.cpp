#include "bridge.h"

#include <cstddef>
#include <vector>

#include "kernels.hpp"

extern "C" {

int64_t tracon_select(int32_t kernel, int64_t n, const int32_t* stream,
                      const double* ready_ms, const double* service_ms,
                      const int32_t* waiters, const int32_t* warm, int64_t k,
                      double now, double starve_ms, int64_t* out_indices) {
    std::vector<tracon::RequestView> queue(static_cast<std::size_t>(n));
    for (std::size_t i = 0; i < queue.size(); ++i) {
        queue[i] = tracon::RequestView{static_cast<std::int64_t>(i), stream[i], ready_ms[i],
                                       service_ms[i],                waiters[i], warm[i]};
    }
    const auto picked = tracon::select_by_kernel(static_cast<tracon::Kernel>(kernel), queue, k,
                                                 now, starve_ms);
    for (std::size_t j = 0; j < picked.size(); ++j) {
        out_indices[j] = static_cast<int64_t>(picked[j]);
    }
    return static_cast<int64_t>(picked.size());
}

const char* tracon_version(void) { return tracon::kVersion; }

}  // extern "C"
