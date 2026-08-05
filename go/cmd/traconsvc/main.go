// traconsvc: the tracon scheduling core as a gRPC service. Stateless and
// deterministic — every Select call is a pure function of its request, backed by
// the same C++ kernels the Python seam compiles (core/src/kernels.hpp).
package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"math"
	"net"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"traconsvc/core"
	"traconsvc/schedpb"
)

type server struct {
	schedpb.UnimplementedSchedulerServer
}

func (s *server) Select(_ context.Context, req *schedpb.SelectRequest) (*schedpb.SelectResponse, error) {
	kernel, ok := core.Kernels[req.Kernel]
	if !ok {
		return nil, status.Errorf(codes.InvalidArgument, "unknown kernel: %q", req.Kernel)
	}
	// NaN sort keys violate stable_sort's strict weak ordering (UB in the C++
	// kernels) — reject at the boundary. Infinities order consistently and pass.
	if math.IsNaN(req.Now) || math.IsNaN(req.StarveMs) {
		return nil, status.Error(codes.InvalidArgument, "now/starve_ms must not be NaN")
	}
	queue := make([]core.RequestView, len(req.Queue))
	for i, r := range req.Queue {
		if math.IsNaN(r.ReadyMs) || math.IsNaN(r.ServiceMs) {
			return nil, status.Errorf(codes.InvalidArgument,
				"queue[%d]: ready_ms/service_ms must not be NaN", i)
		}
		queue[i] = core.RequestView{
			Req:       r.Req,
			Stream:    r.Stream,
			ReadyMs:   r.ReadyMs,
			ServiceMs: r.ServiceMs,
			Waiters:   r.Waiters,
			Warm:      r.Warm,
		}
	}
	return &schedpb.SelectResponse{
		Indices: core.Select(kernel, queue, req.K, req.Now, req.StarveMs),
	}, nil
}

func main() {
	addr := flag.String("addr", "127.0.0.1:50351", "listen address")
	flag.Parse()

	lis, err := net.Listen("tcp", *addr)
	if err != nil {
		log.Fatalf("listen %s: %v", *addr, err)
	}
	grpcServer := grpc.NewServer()
	schedpb.RegisterSchedulerServer(grpcServer, &server{})
	// the readiness line test fixtures wait for — keep format stable
	fmt.Printf("traconsvc %s listening on %s\n", core.Version(), lis.Addr())
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("serve: %v", err)
	}
}
