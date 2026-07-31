from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class RequestView(_message.Message):
    __slots__ = ("req", "stream", "ready_ms", "service_ms", "waiters", "warm")
    REQ_FIELD_NUMBER: _ClassVar[int]
    STREAM_FIELD_NUMBER: _ClassVar[int]
    READY_MS_FIELD_NUMBER: _ClassVar[int]
    SERVICE_MS_FIELD_NUMBER: _ClassVar[int]
    WAITERS_FIELD_NUMBER: _ClassVar[int]
    WARM_FIELD_NUMBER: _ClassVar[int]
    req: int
    stream: int
    ready_ms: float
    service_ms: float
    waiters: int
    warm: int
    def __init__(self, req: _Optional[int] = ..., stream: _Optional[int] = ..., ready_ms: _Optional[float] = ..., service_ms: _Optional[float] = ..., waiters: _Optional[int] = ..., warm: _Optional[int] = ...) -> None: ...

class SelectRequest(_message.Message):
    __slots__ = ("kernel", "queue", "k", "now", "starve_ms")
    KERNEL_FIELD_NUMBER: _ClassVar[int]
    QUEUE_FIELD_NUMBER: _ClassVar[int]
    K_FIELD_NUMBER: _ClassVar[int]
    NOW_FIELD_NUMBER: _ClassVar[int]
    STARVE_MS_FIELD_NUMBER: _ClassVar[int]
    kernel: str
    queue: _containers.RepeatedCompositeFieldContainer[RequestView]
    k: int
    now: float
    starve_ms: float
    def __init__(self, kernel: _Optional[str] = ..., queue: _Optional[_Iterable[_Union[RequestView, _Mapping]]] = ..., k: _Optional[int] = ..., now: _Optional[float] = ..., starve_ms: _Optional[float] = ...) -> None: ...

class SelectResponse(_message.Message):
    __slots__ = ("indices",)
    INDICES_FIELD_NUMBER: _ClassVar[int]
    indices: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, indices: _Optional[_Iterable[int]] = ...) -> None: ...
