// tracon_core: pybind11 bindings over the shared scheduling kernels
// (kernels.hpp — also compiled by the Go gRPC service, so both transports make
// identical decisions by construction). Plain data crosses the seam:
// RequestView in, queue positions out.

#include <string>
#include <vector>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "kernels.hpp"

namespace py = pybind11;

using tracon::RequestView;

PYBIND11_MODULE(tracon_core, m) {
    m.doc() = "tracon compiled scheduling core: RequestView in, queue positions out";
    m.def("version", [] { return std::string(tracon::kVersion); });

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

    m.def("select_fifo", &tracon::select_fifo, py::arg("ready_ms"), py::arg("k"));
    m.def("select_fifo_views", &tracon::select_fifo_views, py::arg("queue"), py::arg("k"));
    m.def("select_sjf", &tracon::select_sjf, py::arg("queue"), py::arg("k"), py::arg("now"),
          py::arg("starve_ms"));
    m.def("select_unblock", &tracon::select_unblock, py::arg("queue"), py::arg("k"),
          py::arg("now"), py::arg("starve_ms"));
    m.def("select_affinity", &tracon::select_affinity, py::arg("queue"), py::arg("k"),
          py::arg("now"), py::arg("starve_ms"));
    m.def("select_tracon", &tracon::select_tracon, py::arg("queue"), py::arg("k"),
          py::arg("now"), py::arg("starve_ms"));
}
