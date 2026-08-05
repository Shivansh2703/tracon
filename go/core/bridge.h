// C ABI over the shared scheduling kernels (core/src/kernels.hpp) — the seam Go
// crosses via cgo. Flat arrays only; no STL types cross the boundary.
#ifndef TRACON_BRIDGE_H
#define TRACON_BRIDGE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// Kernel ids mirror tracon::Kernel: 0=fifo 1=sjf 2=unblock 3=affinity 4=tracon.
// Arrays are parallel per-request fields of length n; out_indices must hold n.
// Returns the number of selected positions written to out_indices (<= k).
int64_t tracon_select(int32_t kernel, int64_t n, const int32_t* stream,
                      const double* ready_ms, const double* service_ms,
                      const int32_t* waiters, const int32_t* warm, int64_t k,
                      double now, double starve_ms, int64_t* out_indices);

const char* tracon_version(void);

#ifdef __cplusplus
}
#endif

#endif  // TRACON_BRIDGE_H
