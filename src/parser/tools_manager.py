"""OCR tool registry and dispatch layer.

The manager keeps OCR backends behind one small interface so parser code can
ask for layout, table, figure, or text work without knowing which library is
doing the work.
"""

from __future__ import annotations

import importlib
import json
from abc import ABC
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .models import CuratedPage, LayoutRegion, PageLayoutGraph, ParsedElement


DEFAULT_TOOL_LIBRARY_PATH = Path(__file__).with_name("tool_library.json")


class OCRToolError(RuntimeError):
    """Base error raised by OCR tool management."""


class OCRToolUnavailableError(OCRToolError):
    """Raised when a configured OCR backend cannot be loaded or used."""


class UnsupportedOCRCapabilityError(OCRToolError):
    """Raised when a tool is asked to perform a capability it does not expose."""


@dataclass(frozen=True)
class OCRToolContext:
    """Common execution context passed to OCR tools."""

    session_id: str
    page: CuratedPage
    region: LayoutRegion | None = None
    options: Mapping[str, Any] = field(default_factory=dict)


class OCRTool(ABC):
    """Template every OCR backend should follow.

    Backends can implement any subset of the methods, but their configured
    capabilities in ``tool_library.json`` must match what they support.
    """

    name = "ocr-tool"
    capabilities: frozenset[str] = frozenset()

    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        self.config = dict(config or {})

    def analyze_layout(self, context: OCRToolContext) -> PageLayoutGraph:
        """Detect page-level layout regions."""

        raise UnsupportedOCRCapabilityError(f"{self.name} does not support analyze_layout")

    def detect_table(self, context: OCRToolContext) -> ParsedElement:
        """Recognize a table region and return structured table output."""

        raise UnsupportedOCRCapabilityError(f"{self.name} does not support detect_table")

    def detect_figure(self, context: OCRToolContext) -> ParsedElement:
        """Recognize a figure/chart region and return grounded visual output."""

        raise UnsupportedOCRCapabilityError(f"{self.name} does not support detect_figure")

    def recognize_text(self, context: OCRToolContext) -> ParsedElement:
        """Recognize text in a page or layout region."""

        raise UnsupportedOCRCapabilityError(f"{self.name} does not support recognize_text")


@dataclass(frozen=True)
class OCRToolSpec:
    """Configuration entry from the JSON OCR tool library."""

    name: str
    class_path: str
    capabilities: tuple[str, ...]
    enabled: bool = True
    priority: int = 100
    config: Mapping[str, Any] = field(default_factory=dict)
    description: str = ""

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "OCRToolSpec":
        missing = {"name", "class_path", "capabilities"} - data.keys()
        if missing:
            raise ValueError(f"OCR tool spec missing required keys: {sorted(missing)}")

        capabilities = data["capabilities"]
        if not isinstance(capabilities, list) or not all(isinstance(item, str) for item in capabilities):
            raise ValueError(f"OCR tool '{data['name']}' capabilities must be a list of strings")

        return cls(
            name=str(data["name"]),
            class_path=str(data["class_path"]),
            capabilities=tuple(capabilities),
            enabled=bool(data.get("enabled", True)),
            priority=int(data.get("priority", 100)),
            config=dict(data.get("config", {})),
            description=str(data.get("description", "")),
        )


class OCRToolLibrary:
    """Read and validate the JSON-backed OCR tool library."""

    def __init__(self, path: str | Path = DEFAULT_TOOL_LIBRARY_PATH) -> None:
        self.path = Path(path)
        self._specs = self._load()

    @property
    def specs(self) -> tuple[OCRToolSpec, ...]:
        return self._specs

    def get(self, name: str) -> OCRToolSpec:
        for spec in self._specs:
            if spec.name == name:
                return spec
        raise KeyError(f"OCR tool is not configured: {name}")

    def enabled_for(self, capability: str) -> list[OCRToolSpec]:
        return sorted(
            [spec for spec in self._specs if spec.enabled and capability in spec.capabilities],
            key=lambda spec: (spec.priority, spec.name),
        )

    def _load(self) -> tuple[OCRToolSpec, ...]:
        if not self.path.exists():
            raise FileNotFoundError(f"OCR tool library not found: {self.path}")

        with self.path.open("r", encoding="utf-8") as library_file:
            payload = json.load(library_file)

        tools = payload.get("tools")
        if not isinstance(tools, list):
            raise ValueError(f"OCR tool library must contain a 'tools' list: {self.path}")

        specs = tuple(OCRToolSpec.from_mapping(item) for item in tools)
        names = [spec.name for spec in specs]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"Duplicate OCR tool names in {self.path}: {duplicates}")
        return specs


class OCRToolManager:
    """Instantiate OCR tools from JSON config and dispatch capability calls."""

    def __init__(self, library_path: str | Path = DEFAULT_TOOL_LIBRARY_PATH) -> None:
        self.library = OCRToolLibrary(library_path)
        self._instances: dict[str, OCRTool] = {}

    def list_tools(self, include_disabled: bool = True) -> list[OCRToolSpec]:
        specs = self.library.specs if include_disabled else tuple(spec for spec in self.library.specs if spec.enabled)
        return sorted(specs, key=lambda spec: (spec.priority, spec.name))

    def get_tool(self, name: str) -> OCRTool:
        if name not in self._instances:
            spec = self.library.get(name)
            if not spec.enabled:
                raise OCRToolUnavailableError(f"OCR tool is disabled in the library: {name}")
            self._instances[name] = self._build_tool(spec)
        return self._instances[name]

    def get_tool_for(self, capability: str, preferred_tool: str | None = None) -> OCRTool:
        if preferred_tool:
            spec = self.library.get(preferred_tool)
            if capability not in spec.capabilities:
                raise UnsupportedOCRCapabilityError(f"OCR tool '{preferred_tool}' does not support {capability}")
            return self.get_tool(preferred_tool)

        candidates = self.library.enabled_for(capability)
        if not candidates:
            raise OCRToolUnavailableError(f"No enabled OCR tool supports {capability}")
        return self.get_tool(candidates[0].name)

    def analyze_layout(
        self,
        *,
        session_id: str,
        page: CuratedPage,
        tool_name: str | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> PageLayoutGraph:
        tool = self.get_tool_for("analyze_layout", tool_name)
        return tool.analyze_layout(OCRToolContext(session_id=session_id, page=page, options=options or {}))

    def detect_table(
        self,
        *,
        session_id: str,
        page: CuratedPage,
        region: LayoutRegion | None = None,
        tool_name: str | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> ParsedElement:
        tool = self.get_tool_for("detect_table", tool_name)
        return tool.detect_table(
            OCRToolContext(session_id=session_id, page=page, region=region, options=options or {})
        )

    def detect_figure(
        self,
        *,
        session_id: str,
        page: CuratedPage,
        region: LayoutRegion | None = None,
        tool_name: str | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> ParsedElement:
        tool = self.get_tool_for("detect_figure", tool_name)
        return tool.detect_figure(
            OCRToolContext(session_id=session_id, page=page, region=region, options=options or {})
        )

    def recognize_text(
        self,
        *,
        session_id: str,
        page: CuratedPage,
        region: LayoutRegion | None = None,
        tool_name: str | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> ParsedElement:
        tool = self.get_tool_for("recognize_text", tool_name)
        return tool.recognize_text(
            OCRToolContext(session_id=session_id, page=page, region=region, options=options or {})
        )

    def _build_tool(self, spec: OCRToolSpec) -> OCRTool:
        module_name, _, class_name = spec.class_path.rpartition(".")
        if not module_name or not class_name:
            raise OCRToolUnavailableError(f"Invalid OCR tool class path: {spec.class_path}")

        try:
            module = importlib.import_module(module_name)
            tool_class = getattr(module, class_name)
            tool = tool_class(config=spec.config)
        except Exception as exc:  # pragma: no cover - exact import errors vary by optional backend.
            raise OCRToolUnavailableError(f"Could not load OCR tool '{spec.name}' from {spec.class_path}: {exc}") from exc

        if not isinstance(tool, OCRTool):
            raise OCRToolUnavailableError(f"OCR tool '{spec.name}' must inherit from OCRTool")
        if not set(spec.capabilities).issubset(tool.capabilities):
            raise OCRToolUnavailableError(
                f"OCR tool '{spec.name}' is missing configured capabilities: "
                f"{sorted(set(spec.capabilities) - tool.capabilities)}"
            )
        return tool


__all__ = [
    "DEFAULT_TOOL_LIBRARY_PATH",
    "OCRTool",
    "OCRToolContext",
    "OCRToolError",
    "OCRToolLibrary",
    "OCRToolManager",
    "OCRToolSpec",
    "OCRToolUnavailableError",
    "UnsupportedOCRCapabilityError",
]
