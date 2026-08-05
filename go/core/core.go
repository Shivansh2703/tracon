// Package core wraps the shared C++ scheduling kernels (core/src/kernels.hpp)
// via cgo. The C++ compiles into this binary — no shared library, and the exact
// same decision code the Python seam uses.
package core

/*
#cgo CXXFLAGS: -std=c++20 -I${SRCDIR}/../../core/src
#include "bridge.h"
*/
import "C"

import "unsafe"

// RequestView mirrors the seam struct: plain data in, queue positions out.
type RequestView struct {
	Req       int64
	Stream    int32
	ReadyMs   float64
	ServiceMs float64
	Waiters   int32
	Warm      int32
}

// Kernel ids mirror tracon::Kernel in kernels.hpp.
var Kernels = map[string]int32{
	"fifo":     0,
	"sjf":      1,
	"unblock":  2,
	"affinity": 3,
	"tracon":   4,
}

func Version() string {
	return C.GoString(C.tracon_version())
}

// Select returns up to k queue positions in dispatch order.
func Select(kernel int32, queue []RequestView, k int64, now, starveMs float64) []int64 {
	n := len(queue)
	if n == 0 || k <= 0 {
		return nil
	}
	stream := make([]int32, n)
	ready := make([]float64, n)
	service := make([]float64, n)
	waiters := make([]int32, n)
	warm := make([]int32, n)
	for i, r := range queue {
		stream[i] = r.Stream
		ready[i] = r.ReadyMs
		service[i] = r.ServiceMs
		waiters[i] = r.Waiters
		warm[i] = r.Warm
	}
	out := make([]int64, n)
	wrote := C.tracon_select(
		C.int32_t(kernel), C.int64_t(n),
		(*C.int32_t)(unsafe.Pointer(&stream[0])),
		(*C.double)(unsafe.Pointer(&ready[0])),
		(*C.double)(unsafe.Pointer(&service[0])),
		(*C.int32_t)(unsafe.Pointer(&waiters[0])),
		(*C.int32_t)(unsafe.Pointer(&warm[0])),
		C.int64_t(k), C.double(now), C.double(starveMs),
		(*C.int64_t)(unsafe.Pointer(&out[0])),
	)
	return out[:wrote]
}
