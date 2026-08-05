package core

import (
	"reflect"
	"testing"
)

func view(stream int32, ready, service float64, waiters, warm int32) RequestView {
	return RequestView{Stream: stream, ReadyMs: ready, ServiceMs: service, Waiters: waiters, Warm: warm}
}

// Mirrors tests/test_core_seam.py: oldest-first with stable ties.
func TestSelectFifoStableTies(t *testing.T) {
	queue := []RequestView{
		view(0, 5.0, 1, 0, 0), view(1, 1.0, 1, 0, 0), view(2, 3.0, 1, 0, 0), view(3, 1.0, 1, 0, 0),
	}
	got := Select(Kernels["fifo"], queue, 3, 10.0, 1e12)
	want := []int64{1, 3, 2}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("fifo = %v, want %v", got, want)
	}
}

func TestSelectSjfOrdersByServiceWithGuard(t *testing.T) {
	queue := []RequestView{
		view(0, 0.0, 900, 0, 0), view(1, 1.0, 5, 0, 0), view(2, 2.0, 100, 0, 0),
	}
	if got := Select(Kernels["sjf"], queue, 3, 2.0, 1e12); !reflect.DeepEqual(got, []int64{1, 2, 0}) {
		t.Fatalf("sjf = %v", got)
	}
	// everyone past the guard: collapses to FIFO
	if got := Select(Kernels["sjf"], queue, 3, 1e9, 10.0); !reflect.DeepEqual(got, []int64{0, 1, 2}) {
		t.Fatalf("starved sjf = %v", got)
	}
}

func TestSelectTraconWaitersThenWarm(t *testing.T) {
	queue := []RequestView{
		view(0, 0.0, 1, 0, 0), view(1, 1.0, 1, 2, 0), view(2, 2.0, 1, 2, 1), view(3, 3.0, 1, 0, 1),
	}
	got := Select(Kernels["tracon"], queue, 4, 3.0, 1e12)
	// most waiters first (warm breaks the 2-2 tie), then warm zero-waiter, then cold
	want := []int64{2, 1, 3, 0}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("tracon = %v, want %v", got, want)
	}
}

func TestSelectEmptyAndZeroK(t *testing.T) {
	if got := Select(Kernels["fifo"], nil, 4, 0, 1e12); got != nil {
		t.Fatalf("empty queue = %v", got)
	}
	queue := []RequestView{view(0, 0, 1, 0, 0)}
	if got := Select(Kernels["fifo"], queue, 0, 0, 1e12); got != nil {
		t.Fatalf("k=0 = %v", got)
	}
}
