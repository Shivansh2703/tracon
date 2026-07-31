"""End-to-end parity through the Go gRPC service (docs/m4_plan.md, phase E).

The service compiles the same C++ kernels as the pybind11 seam, so a full
simulation driven over the wire must equal the in-process one byte for byte.
Skips unless the binary exists: ``cd go && go build -o bin/traconsvc ./cmd/traconsvc``.
"""

import socket
import subprocess
from pathlib import Path

import pytest
from test_core_policy_parity import _contended_fixture

from tracon.sim.runner import SimConfig, Simulation

BINARY = Path(__file__).resolve().parent.parent / "go" / "bin" / "traconsvc"

pytestmark = pytest.mark.skipif(
    not BINARY.exists(),
    reason="go service not built: cd go && go build -o bin/traconsvc ./cmd/traconsvc",
)


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
    workload = _contended_fixture(tmp_path)
    for kernel in ("fifo", "sjf", "tracon"):
        assert _run(workload, f"grpc-{kernel}") == _run(workload, f"core-{kernel}"), kernel


@pytest.mark.usefixtures("grpc_addr")
def test_grpc_determinism(tmp_path):
    workload = _contended_fixture(tmp_path)
    assert _run(workload, "grpc-tracon") == _run(workload, "grpc-tracon")
