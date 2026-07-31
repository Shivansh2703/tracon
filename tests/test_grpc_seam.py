"""End-to-end parity through the Go gRPC service (docs/scheduler.md).

The service compiles the same C++ kernels as the pybind11 seam, so a full
simulation driven over the wire must equal the in-process one byte for byte.
Skips unless the binary exists: ``cd go && go build -o bin/traconsvc ./cmd/traconsvc``.
"""

import shutil
import socket
import subprocess
from pathlib import Path

import grpc
import pytest
from test_core_policy_parity import _contended_fixture

from tracon.schedpb import scheduler_pb2, scheduler_pb2_grpc
from tracon.sim.runner import SimConfig, Simulation

GO_DIR = Path(__file__).resolve().parent.parent / "go"
BINARY = GO_DIR / "bin" / "traconsvc"


def _ensure_binary() -> str | None:
    """Build the service on demand. Only a missing Go toolchain may skip these
    tests; a failing build must fail the suite, not silently skip it (codex #1)."""
    if BINARY.exists():
        return None
    go = shutil.which("go")
    if go is None:
        return "go toolchain not installed"
    build = subprocess.run(  # noqa: S603
        [go, "build", "-o", str(BINARY), "./cmd/traconsvc"],
        cwd=GO_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    if build.returncode != 0:
        pytest.fail(f"go service failed to build:\n{build.stderr}")
    return None


pytestmark = pytest.mark.skipif(_ensure_binary() is not None, reason="go toolchain not installed")


@pytest.fixture
def grpc_addr(monkeypatch):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        addr = f"127.0.0.1:{sock.getsockname()[1]}"
    proc = subprocess.Popen(  # noqa: S603 — our own freshly-built binary
        [str(BINARY), "-addr", addr], stdout=subprocess.PIPE, text=True
    )
    try:
        assert proc.stdout is not None
        ready = proc.stdout.readline()  # the stable readiness line from main.go
        assert "listening" in ready, ready
        monkeypatch.setenv("TRACON_GRPC_ADDR", addr)
        yield addr
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def _run(workload, policy):
    config = SimConfig(
        executors=1,
        max_batch=2,
        max_wait_ms=100.0,
        policy=policy,
        cold_penalty_ms=3_000.0,
        resident_streams=2,
    )
    results = Simulation(workload, config).run()
    results["config"]["policy"] = "-"
    return results


@pytest.mark.usefixtures("grpc_addr")
def test_grpc_matches_pybind_end_to_end(tmp_path):
    # every kernel id: Go's map and the C++ enum are independently maintained,
    # so a swapped id would silently swap policies (codex #5)
    workload = _contended_fixture(tmp_path)
    for kernel in ("fifo", "sjf", "unblock", "affinity", "tracon"):
        assert _run(workload, f"grpc-{kernel}") == _run(workload, f"core-{kernel}"), kernel


@pytest.mark.usefixtures("grpc_addr")
def test_grpc_determinism(tmp_path):
    workload = _contended_fixture(tmp_path)
    assert _run(workload, "grpc-tracon") == _run(workload, "grpc-tracon")


def test_grpc_rejects_nan(grpc_addr):
    # NaN sort keys would break stable_sort's strict weak ordering — the service
    # must refuse them at the boundary instead of hitting UB (codex #3)
    stub = scheduler_pb2_grpc.SchedulerStub(grpc.insecure_channel(grpc_addr))
    request = scheduler_pb2.SelectRequest(
        kernel="sjf",
        queue=[scheduler_pb2.RequestView(req=0, stream=0, ready_ms=0.0, service_ms=float("nan"))],
        k=1,
        now=0.0,
        starve_ms=60_000.0,
    )
    with pytest.raises(grpc.RpcError) as err:
        stub.Select(request, timeout=5.0)
    assert isinstance(err.value, grpc.Call)  # unary errors carry status via Call
    assert err.value.code() == grpc.StatusCode.INVALID_ARGUMENT


def test_grpc_rejects_unknown_kernel(grpc_addr):
    stub = scheduler_pb2_grpc.SchedulerStub(grpc.insecure_channel(grpc_addr))
    with pytest.raises(grpc.RpcError) as err:
        stub.Select(scheduler_pb2.SelectRequest(kernel="lifo", k=1), timeout=5.0)
    assert isinstance(err.value, grpc.Call)  # unary errors carry status via Call
    assert err.value.code() == grpc.StatusCode.INVALID_ARGUMENT
