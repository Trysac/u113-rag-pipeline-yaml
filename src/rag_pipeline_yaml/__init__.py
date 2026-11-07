"""Declarative RAG pipelines in YAML.

Registered components, typed variable interpolation, static checks before any
step runs, alias-free safe loading and content-free traces.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypedDict

import yaml  # type: ignore[import-untyped]

__all__ = [
    "ErrorCode",
    "FakeLLM",
    "LLMPort",
    "Message",
    "Pipeline",
    "PipelineError",
    "RecordedLLM",
    "RecordingExhaustedError",
    "Registry",
    "RunResult",
    "Step",
    "StepTrace",
    "__version__",
    "load_pipeline",
    "run",
]

__version__ = "0.1.0"

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

ErrorCode = Literal[
    "invalid_yaml",
    "alias_forbidden",
    "too_large",
    "invalid_pipeline",
    "undefined_variable",
    "unknown_component",
    "step_failed",
    "missing_input",
]

NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
REGISTRY_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
BUILTIN_COMPONENTS = frozenset({"template", "llm"})
VAR_INTERPOLATION_REGEX = re.compile(r"(?<!\$)\${([a-zA-Z0-9_-]+)}")
EXACT_VAR_REGEX = re.compile(r"^\${([a-zA-Z0-9_-]+)}$")


class PipelineError(Exception):
    """Base error for pipeline loading and execution failures."""

    def __init__(self, code: ErrorCode, detail: str = "", step_id: str | None = None) -> None:
        # Limit detail size to 200 chars
        detail_snippet = detail[:200]
        msg = f"{code}: {detail_snippet}" if detail_snippet else code
        super().__init__(msg)
        self.code: ErrorCode = code
        self.detail: str = detail_snippet
        self.step_id: str | None = step_id


class RecordingExhaustedError(RuntimeError):
    """Raised when RecordedLLM has exhausted all prepared replies."""


class Message(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMPort(Protocol):
    """Protocol for LLM integrations."""

    def complete(self, messages: Sequence[Message], *, max_tokens: int) -> str:
        """Complete the prompt with the LLM."""
        ...


@dataclass(frozen=True)
class LLMCall:
    """Recorded invocation of an LLM."""

    messages: tuple[Message, ...]
    max_tokens: int


class RecordedLLM:
    """Recorded LLM returning replies sequentially."""

    def __init__(self, replies: Sequence[str]) -> None:
        self._replies: list[str] = list(replies)
        self._index: int = 0
        self.calls: list[LLMCall] = []

    def complete(self, messages: Sequence[Message], *, max_tokens: int) -> str:
        if self._index >= len(self._replies):
            raise RecordingExhaustedError("Recorded LLM replies exhausted")
        reply = self._replies[self._index]
        self._index += 1
        self.calls.append(LLMCall(tuple(messages), max_tokens))
        return reply


class FakeLLM:
    """Fake LLM delegating completion generation to a callable."""

    def __init__(self, fn: Callable[[Sequence[Message]], str]) -> None:
        self._fn = fn
        self.calls: list[LLMCall] = []

    def complete(self, messages: Sequence[Message], *, max_tokens: int) -> str:
        self.calls.append(LLMCall(tuple(messages), max_tokens))
        return self._fn(messages)


@dataclass(frozen=True)
class Step:
    """A single pipeline execution step."""

    id: str
    use: str
    params: Mapping[str, Any]
    output: str


@dataclass(frozen=True)
class Pipeline:
    """Declarative definition of a RAG pipeline."""

    name: str
    version: int
    inputs: tuple[str, ...]
    steps: tuple[Step, ...]


@dataclass(frozen=True)
class StepTrace:
    """Execution trace for a step, containing no inputs or outputs."""

    step_id: str
    component: str
    status: Literal["ok", "error"]
    duration_ms: int


@dataclass(frozen=True)
class RunResult:
    """Results and trace of a pipeline execution."""

    outputs: dict[str, Any]
    trace: tuple[StepTrace, ...]


class Registry:
    """Component registry mapping component names to executable functions."""

    def __init__(self) -> None:
        self._components: dict[str, Callable[[Mapping[str, Any]], Any]] = {}

    def register(self, name: str, fn: Callable[[Mapping[str, Any]], Any]) -> None:
        if not REGISTRY_NAME_PATTERN.match(name):
            raise PipelineError("invalid_pipeline", f"invalid component name format: {name!r}")
        if name in BUILTIN_COMPONENTS:
            raise PipelineError("invalid_pipeline", f"component name shadows builtin: {name!r}")
        self._components[name] = fn

    def names(self) -> list[str]:
        return sorted(self._components.keys())

    def get(self, name: str) -> Callable[[Mapping[str, Any]], Any] | None:
        return self._components.get(name)


def _scan_tokens_for_alias_and_anchor(text: str) -> None:
    try:
        for event in yaml.parse(text, Loader=yaml.SafeLoader):
            if isinstance(event, yaml.AliasEvent):
                raise PipelineError("alias_forbidden", "YAML aliases are forbidden")
            if getattr(event, "anchor", None) is not None:
                raise PipelineError("alias_forbidden", "YAML anchors are forbidden")
    except yaml.YAMLError as exc:
        raise PipelineError("invalid_yaml", f"YAML parsing failed: {exc}") from exc


def _extract_vars(value: Any, depth: int = 0) -> list[str]:
    if depth > 16:
        return []
    vars_found: list[str] = []
    if isinstance(value, str):
        cleaned = re.sub(r"\$\${[a-zA-Z0-9_-]+}", "", value)
        for m in VAR_INTERPOLATION_REGEX.finditer(cleaned):
            vars_found.append(m.group(1))
    elif isinstance(value, Mapping):
        for v in value.values():
            vars_found.extend(_extract_vars(v, depth + 1))
    elif isinstance(value, (list, tuple)):
        for item in value:
            vars_found.extend(_extract_vars(item, depth + 1))
    return vars_found


def load_pipeline(text: str, *, max_bytes: int = 65_536) -> Pipeline:
    """Load and statically validate a YAML pipeline specification."""
    raw_bytes = text.encode("utf-8")
    if len(raw_bytes) > max_bytes:
        raise PipelineError(
            "too_large", f"pipeline exceeds max bytes ({len(raw_bytes)} > {max_bytes})"
        )

    _scan_tokens_for_alias_and_anchor(text)

    try:
        data = yaml.load(text, Loader=yaml.SafeLoader)
    except yaml.YAMLError as exc:
        raise PipelineError("invalid_yaml", f"YAML load failed: {exc}") from exc

    if not isinstance(data, dict):
        raise PipelineError("invalid_pipeline", "top-level YAML must be a mapping")

    allowed_top_keys = {"pipeline", "version", "inputs", "steps"}
    extra_keys = set(data.keys()) - allowed_top_keys
    if extra_keys:
        raise PipelineError(
            "invalid_pipeline", f"unknown top-level key(s): {', '.join(sorted(extra_keys))}"
        )
    missing_keys = allowed_top_keys - set(data.keys())
    if missing_keys:
        raise PipelineError(
            "invalid_pipeline", f"missing top-level key(s): {', '.join(sorted(missing_keys))}"
        )

    name = data["pipeline"]
    if not isinstance(name, str) or not NAME_PATTERN.match(name):
        raise PipelineError("invalid_pipeline", f"invalid pipeline name: {name!r}")

    version = data["version"]
    if not isinstance(version, int) or version != 1 or isinstance(version, bool):
        raise PipelineError(
            "invalid_pipeline", f"invalid pipeline version: {version!r}, expected 1"
        )

    inputs = data["inputs"]
    if not isinstance(inputs, list):
        raise PipelineError("invalid_pipeline", "inputs must be a list of variable names")

    input_names: list[str] = []
    for item in inputs:
        if not isinstance(item, str) or not NAME_PATTERN.match(item):
            raise PipelineError("invalid_pipeline", f"invalid input name: {item!r}")
        if item in input_names:
            raise PipelineError("invalid_pipeline", f"duplicate input name: {item!r}")
        input_names.append(item)

    steps_raw = data["steps"]
    if not isinstance(steps_raw, list):
        raise PipelineError("invalid_pipeline", "steps must be a list")
    if not (1 <= len(steps_raw) <= 50):
        raise PipelineError(
            "invalid_pipeline", f"steps count must be between 1 and 50, got {len(steps_raw)}"
        )

    known_variables = set(input_names)
    seen_step_ids: set[str] = set()
    parsed_steps: list[Step] = []

    for step_dict in steps_raw:
        if not isinstance(step_dict, dict):
            raise PipelineError("invalid_pipeline", "step definition must be a mapping")
        allowed_step_keys = {"id", "use", "with", "output"}
        extra_step_keys = set(step_dict.keys()) - allowed_step_keys
        if extra_step_keys:
            raise PipelineError(
                "invalid_pipeline", f"unknown step keys: {', '.join(sorted(extra_step_keys))}"
            )
        for req in ("id", "use", "output"):
            if req not in step_dict:
                raise PipelineError("invalid_pipeline", f"step missing required key: {req!r}")

        step_id = step_dict["id"]
        if not isinstance(step_id, str) or not NAME_PATTERN.match(step_id):
            raise PipelineError("invalid_pipeline", f"invalid step id: {step_id!r}")
        if step_id in seen_step_ids:
            raise PipelineError("invalid_pipeline", f"duplicate step id: {step_id!r}")
        seen_step_ids.add(step_id)

        use = step_dict["use"]
        if not isinstance(use, str) or not REGISTRY_NAME_PATTERN.match(use):
            raise PipelineError(
                "invalid_pipeline", f"invalid component use in step '{step_id}': {use!r}"
            )

        output = step_dict["output"]
        if not isinstance(output, str) or not NAME_PATTERN.match(output):
            raise PipelineError(
                "invalid_pipeline", f"invalid output variable in step '{step_id}': {output!r}"
            )
        if output in known_variables:
            raise PipelineError(
                "invalid_pipeline",
                f"step '{step_id}' output shadows existing input or output variable '{output}'",
                step_id=step_id,
            )

        params = step_dict.get("with", {})
        if params is None:
            params = {}
        if not isinstance(params, Mapping):
            raise PipelineError(
                "invalid_pipeline", f"'with' parameters in step '{step_id}' must be a mapping"
            )

        # Check variables statically
        used_vars = _extract_vars(params)
        for var in used_vars:
            if var not in known_variables:
                raise PipelineError(
                    "undefined_variable",
                    f"step {step_id} uses {var}",
                    step_id=step_id,
                )

        known_variables.add(output)
        parsed_steps.append(Step(id=step_id, use=use, params=dict(params), output=output))

    return Pipeline(
        name=name,
        version=version,
        inputs=tuple(input_names),
        steps=tuple(parsed_steps),
    )


def _format_var_value(val: Any) -> str:
    if isinstance(val, str):
        return val
    if isinstance(val, (list, tuple)) and all(isinstance(x, str) for x in val):
        return "\n".join(val)
    return json.dumps(val)


def _interpolate(value: Any, env: Mapping[str, Any], depth: int = 0) -> Any:
    if depth > 16:
        return value
    if isinstance(value, str):
        exact_m = EXACT_VAR_REGEX.match(value)
        if exact_m:
            var_name = exact_m.group(1)
            if var_name in env:
                return env[var_name]

        # Match $${\w+} (escaped) or ${var}
        # In Python regex: \$\${([a-zA-Z0-9_-]+)} or (?<!\$)\${([a-zA-Z0-9_-]+)}
        pattern = re.compile(r"\$\${([a-zA-Z0-9_-]+)}|(?<!\$)\${([a-zA-Z0-9_-]+)}")

        def token_sub(match: re.Match[str]) -> str:
            if match.group(1) is not None:  # $${var}
                return f"${{{match.group(1)}}}"
            var_name = match.group(2)
            if var_name in env:
                return _format_var_value(env[var_name])
            return match.group(0)

        return pattern.sub(token_sub, value)

    if isinstance(value, Mapping):
        # Variable used in mapping key is NOT interpolated
        return {k: _interpolate(v, env, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(item, env, depth + 1) for item in value]
    if isinstance(value, tuple):
        return tuple(_interpolate(item, env, depth + 1) for item in value)
    return value


def run(
    pipeline: Pipeline,
    inputs: Mapping[str, Any],
    *,
    registry: Registry,
    llm: LLMPort | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> RunResult:
    """Execute a pipeline against the given inputs, registry, and LLM port."""
    # Check missing inputs
    for req_input in pipeline.inputs:
        if req_input not in inputs:
            raise PipelineError("missing_input", f"missing required input: {req_input!r}")

    # Pre-flight check: verify all components exist before running any step
    for step in pipeline.steps:
        if step.use not in BUILTIN_COMPONENTS:
            if registry.get(step.use) is None:
                raise PipelineError(
                    "unknown_component",
                    f"step '{step.id}' uses unknown component: '{step.use}'",
                    step_id=step.id,
                )
        elif step.use == "llm" and llm is None:
            raise PipelineError(
                "invalid_pipeline",
                f"step '{step.id}' uses 'llm' component but no LLM port was provided",
                step_id=step.id,
            )

    env: dict[str, Any] = dict(inputs)
    outputs: dict[str, Any] = {}
    traces: list[StepTrace] = []

    for step in pipeline.steps:
        start_time = clock()
        interpolated_params = _interpolate(step.params, env)

        try:
            if step.use == "template":
                if "text" not in interpolated_params:
                    raise ValueError("template step requires 'text' parameter")
                step_output = interpolated_params["text"]
            elif step.use == "llm":
                if llm is None:
                    raise PipelineError(
                        "invalid_pipeline",
                        f"step '{step.id}' uses 'llm' component but no LLM port was provided",
                        step_id=step.id,
                    )
                if "prompt" not in interpolated_params:
                    raise ValueError("llm step requires 'prompt' parameter")
                max_tokens = interpolated_params.get("max_tokens", 256)
                if not isinstance(max_tokens, int):
                    raise ValueError("llm step 'max_tokens' must be an integer")
                user_message: Message = {
                    "role": "user",
                    "content": str(interpolated_params["prompt"]),
                }
                step_output = llm.complete([user_message], max_tokens=max_tokens)
            else:
                component_fn = registry.get(step.use)
                if component_fn is None:
                    raise RuntimeError(f"component '{step.use}' missing")
                step_output = component_fn(interpolated_params)

            end_time = clock()
            duration_ms = max(0, round((end_time - start_time) * 1000))
            traces.append(
                StepTrace(
                    step_id=step.id,
                    component=step.use,
                    status="ok",
                    duration_ms=duration_ms,
                )
            )
            env[step.output] = step_output
            outputs[step.output] = step_output
        except Exception as exc:
            end_time = clock()
            duration_ms = max(0, round((end_time - start_time) * 1000))
            traces.append(
                StepTrace(
                    step_id=step.id,
                    component=step.use,
                    status="error",
                    duration_ms=duration_ms,
                )
            )
            if isinstance(exc, PipelineError):
                raise
            raise PipelineError(
                "step_failed",
                f"step '{step.id}' execution failed: {exc}",
                step_id=step.id,
            ) from exc

    return RunResult(outputs=outputs, trace=tuple(traces))
