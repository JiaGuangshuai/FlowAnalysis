from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

import numpy as np


def uid() -> str:
    return uuid4().hex


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Transform:
    kind: str = "linear"
    cofactor: float = 150.0
    t: float = 262144.0
    m: float = 4.5
    w: float = 0.5
    a: float = 0.0
    fk_class: str = ""
    fk_parameters: dict = field(default_factory=dict)

    def apply(self, values: np.ndarray) -> np.ndarray:
        from flowutils import transforms

        x = np.asarray(values, dtype=np.float64)
        if self.kind == "linear":
            return x
        if self.kind == "flowkit":
            import flowkit as fk
            allowed = {"LinearTransform", "LogTransform", "AsinhTransform", "LogicleTransform",
                       "HyperlogTransform", "WSPBiexTransform", "WSPLogTransform"}
            if self.fk_class not in allowed:
                raise ValueError("Unsupported imported transform")
            return getattr(fk.transforms, self.fk_class)(**self.fk_parameters).apply(x)
        if self.kind == "arcsinh":
            if self.cofactor <= 0:
                raise ValueError("Cofactor must be positive")
            return np.arcsinh(x / self.cofactor)
        if self.kind == "log":
            out = np.full(x.shape, np.nan)
            np.log10(x, out=out, where=x > 0)
            return out
        if self.kind in ("logicle", "hyperlog"):
            if self.t <= 0 or self.m <= 0 or not 0 <= self.w <= self.m / 2 or not -self.w <= self.a <= self.m - 2 * self.w:
                raise ValueError("Invalid Logicle/Hyperlog parameters")
            func = getattr(transforms, self.kind)
            return func(x.copy(), None, t=self.t, m=self.m, w=self.w, a=self.a)
        if self.kind == "biexponential":
            import flowkit as fk

            return fk.transforms.WSPBiexTransform().apply(x)
        raise ValueError(f"Unknown transform: {self.kind}")


@dataclass
class Gate:
    name: str
    kind: str
    axes: list[str] = field(default_factory=list)
    transforms: list[dict] = field(default_factory=list)
    geometry: dict = field(default_factory=dict)
    parent: str = "root"
    id: str = field(default_factory=uid)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Sample:
    name: str
    raw: np.ndarray
    raw_channels: list[str]
    raw_markers: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    source: str = ""
    id: str = field(default_factory=uid)
    group: str = "Samples"
    well: str = ""
    plate: str = "Plate 1"
    state: str = "unknown"
    data: np.ndarray | None = None
    channels: list[str] = field(default_factory=list)
    markers: list[str] = field(default_factory=list)
    gates: list[Gate] = field(default_factory=list)
    processing: list[dict] = field(default_factory=list)
    results: list[dict] = field(default_factory=list)
    revision: int = 0

    def __post_init__(self):
        self.raw = np.asarray(self.raw, dtype=np.float64)
        if self.raw.ndim != 2 or self.raw.shape[1] != len(self.raw_channels):
            raise ValueError("Event array and channel count do not match")
        if len(set(self.raw_channels)) != len(self.raw_channels):
            raise ValueError("Duplicate channel identifiers")
        if not self.raw_markers:
            self.raw_markers = [""] * len(self.raw_channels)
        if not self.channels:
            self.channels = list(self.raw_channels)
        if not self.markers:
            self.markers = list(self.raw_markers)
        if self.data is None:
            self.data = self.raw
        self.data = np.asarray(self.data, dtype=np.float64)
        if self.data.shape != (len(self.raw), len(self.channels)):
            raise ValueError("Processed array and channel count do not match")
        self.raw.setflags(write=False)
        self.data.setflags(write=False)

    def column(self, channel: str) -> np.ndarray:
        if channel not in self.channels:
            raise ValueError(f"Missing channel: {channel}")
        return self.data[:, self.channels.index(channel)]

    def label(self, channel: str) -> str:
        i = self.channels.index(channel)
        marker = self.markers[i] if i < len(self.markers) else ""
        return f"{channel} · {marker}" if marker and marker != channel else channel

    def replace_data(self, data: np.ndarray, channels: list[str], record: dict, state: str):
        data = np.asarray(data, dtype=np.float64)
        if data.shape != (len(self.raw), len(channels)) or len(set(channels)) != len(channels):
            raise ValueError("Invalid processed event data")
        if not np.isfinite(data).all():
            raise ValueError("Processing produced non-finite event values")
        previous_markers = dict(zip(self.channels, self.markers))
        self.data = data
        self.data.setflags(write=False)
        self.channels = list(channels)
        self.markers = [previous_markers.get(c, "") for c in channels]
        self.state = state
        self.processing.append({"timestamp": now(), **record})
        self.results = []
        self.revision += 1


@dataclass
class Project:
    name: str = "Untitled"
    samples: list[Sample] = field(default_factory=list)
    layouts: list[dict] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    id: str = field(default_factory=uid)

    def record(self, action: str, **details):
        self.history.append({"timestamp": now(), "action": action, **details})

    def sample(self, sample_id: str) -> Sample:
        return next(s for s in self.samples if s.id == sample_id)
