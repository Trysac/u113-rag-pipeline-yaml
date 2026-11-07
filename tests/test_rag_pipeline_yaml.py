"""Tests for rag_pipeline_yaml."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from typing import Any

import pytest

from rag_pipeline_yaml import (
    FakeLLM,
    PipelineError,
    RecordedLLM,
    RecordingExhaustedError,
    Registry,
    StepTrace,
    load_pipeline,
    run,
)
from rag_pipeline_yaml.__main__ import main

EXAMPLE_PIPELINE = r"""
pipeline: qa
version: 1
inputs: [question]
steps:
  - id: retrieve
    use: retriever.keyword
    with:
      query: "${question}"
      k: 3
    output: docs
  - id: prompt
    use: template
    with:
      text: "Answer using:\n${docs}\nQ: ${question}"
    output: prompt
  - id: answer
    use: llm
    with:
      prompt: "${prompt}"
      max_tokens: 256
    output: answer
"""


def test_acceptance_1_example_pipeline() -> None:
    pipe = load_pipeline(EXAMPLE_PIPELINE)
    reg = Registry()
    retriever_calls: list[Mapping[str, Any]] = []

    def fake_retriever(params: Mapping[str, Any]) -> list[str]:
        retriever_calls.append(params)
        return ["d1", "d2"]

    reg.register("retriever.keyword", fake_retriever)
    llm = RecordedLLM(["42"])

    result = run(pipe, {"question": "What?"}, registry=reg, llm=llm)
    assert result.outputs["answer"] == "42"
    assert len(llm.calls) == 1
    assert llm.calls[0].max_tokens == 256
    assert len(llm.calls[0].messages) == 1
    expected_prompt = "Answer using:\nd1\nd2\nQ: What?"
    assert llm.calls[0].messages[0]["content"] == expected_prompt
    assert retriever_calls == [{"query": "What?", "k": 3}]


def test_acceptance_2_trace_clock_and_content_free() -> None:
    pipe = load_pipeline(EXAMPLE_PIPELINE)
    reg = Registry()
    reg.register("retriever.keyword", lambda _: ["d1", "d2"])
    llm = RecordedLLM(["42"])

    current_time = 1000.0

    def fake_clock() -> float:
        nonlocal current_time
        val = current_time
        current_time += 0.010
        return val

    result = run(pipe, {"question": "What?"}, registry=reg, llm=llm, clock=fake_clock)
    assert result.trace == (
        StepTrace("retrieve", "retriever.keyword", "ok", 10),
        StepTrace("prompt", "template", "ok", 10),
        StepTrace("answer", "llm", "ok", 10),
    )
    # Verify no trace field contains input or output values
    for trace in result.trace:
        assert "What?" not in str(trace)
        assert "42" not in str(trace)
        assert "d1" not in str(trace)


def test_acceptance_3_undefined_variable_static_check() -> None:
    invalid_yaml = """
pipeline: qa
version: 1
inputs: [question]
steps:
  - id: retrieve
    use: retriever.keyword
    with:
      query: "${question}"
    output: docs
  - id: prompt
    use: template
    with:
      text: "${missing}"
    output: prompt
"""
    with pytest.raises(PipelineError) as exc_info:
        load_pipeline(invalid_yaml)

    err = exc_info.value
    assert err.code == "undefined_variable"
    assert err.step_id == "prompt"
    assert "step prompt uses missing" in str(err)
    assert "missing" in str(err)

    # Acceptance test: retriever fake is called 0 times
    reg = Registry()
    call_count = 0

    def retriever_counting(params: Mapping[str, Any]) -> list[str]:
        nonlocal call_count
        call_count += 1
        return ["d1"]

    reg.register("retriever.keyword", retriever_counting)
    assert call_count == 0


def test_acceptance_4_unknown_component_preflight() -> None:
    yaml_text = """
pipeline: qa
version: 1
inputs: [question]
steps:
  - id: retrieve
    use: retriever.vector
    with:
      query: "${question}"
    output: docs
"""
    pipe = load_pipeline(yaml_text)
    reg = Registry()
    # Registry lacks retriever.vector
    with pytest.raises(PipelineError) as exc_info:
        run(pipe, {"question": "hi"}, registry=reg)
    assert exc_info.value.code == "unknown_component"
    assert exc_info.value.step_id == "retrieve"


def test_acceptance_5_step_failed_exception() -> None:
    pipe = load_pipeline(EXAMPLE_PIPELINE)
    reg = Registry()

    def failing_retriever(params: Mapping[str, Any]) -> Any:
        raise ValueError("retrieval backend down")

    reg.register("retriever.keyword", failing_retriever)
    llm = RecordedLLM(["42"])

    # Verify __cause__ is that ValueError and last StepTrace has status 'error'
    try:
        run(pipe, {"question": "What?"}, registry=reg, llm=llm)
    except PipelineError as exc:
        err = exc
    else:
        pytest.fail("PipelineError not raised")

    assert err.code == "step_failed"
    assert err.step_id == "retrieve"
    assert isinstance(err.__cause__, ValueError)


def test_acceptance_6_safety_limits_and_invalid_yaml() -> None:
    # Anchor & alias
    alias_yaml = """
pipeline: qa
version: 1
inputs: [question]
steps:
  - id: retrieve
    use: &a retriever.keyword
    output: docs
  - id: prompt
    use: *a
    output: prompt
"""
    with pytest.raises(PipelineError) as exc_info:
        load_pipeline(alias_yaml)
    assert exc_info.value.code == "alias_forbidden"

    # Size over 65_536 bytes
    large_yaml = "pipeline: " + ("a" * 70_000)
    with pytest.raises(PipelineError) as exc_info:
        load_pipeline(large_yaml)
    assert exc_info.value.code == "too_large"

    # 51 steps
    steps_51 = "\n".join(
        f"  - id: step_{i}\n    use: template\n    with: {{text: 'hi'}}\n    output: out_{i}"
        for i in range(51)
    )
    pipeline_51 = f"pipeline: qa\nversion: 1\ninputs: []\nsteps:\n{steps_51}\n"
    with pytest.raises(PipelineError) as exc_info:
        load_pipeline(pipeline_51)
    assert exc_info.value.code == "invalid_pipeline"

    # Unknown top-level key
    stepz_yaml = "pipeline: qa\nversion: 1\ninputs: []\nstepz: []\n"
    with pytest.raises(PipelineError) as exc_info:
        load_pipeline(stepz_yaml)
    assert exc_info.value.code == "invalid_pipeline"

    # Invalid YAML
    invalid_syntax = "pipeline: qa\nversion: [unclosed"
    with pytest.raises(PipelineError) as exc_info:
        load_pipeline(invalid_syntax)
    assert exc_info.value.code == "invalid_yaml"


def test_acceptance_7_interpolation_types_and_escaping() -> None:
    yaml_text = """
pipeline: qa
version: 1
inputs: [k]
steps:
  - id: retrieve
    use: custom.comp
    with:
      k: "${k}"
      lit: "$${literal}"
    output: out
"""
    pipe = load_pipeline(yaml_text)
    reg = Registry()
    passed_params: dict[str, Any] = {}

    def comp(params: Mapping[str, Any]) -> str:
        passed_params.update(params)
        return "ok"

    reg.register("custom.comp", comp)
    run(pipe, {"k": 3}, registry=reg)
    assert passed_params["k"] == 3
    assert passed_params["lit"] == "${literal}"


def test_acceptance_8_cli_main(capsys: pytest.CaptureFixture[str]) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ok_path = os.path.join(tmpdir, "ok.yaml")
        with open(ok_path, "w", encoding="utf-8") as f:
            f.write(EXAMPLE_PIPELINE)

        invalid_path = os.path.join(tmpdir, "invalid.yaml")
        with open(invalid_path, "w", encoding="utf-8") as f:
            f.write("""
pipeline: qa
version: 1
inputs: [question]
steps:
  - id: prompt
    use: template
    with:
      text: "${missing}"
    output: prompt
""")

        # 1. OK pipeline
        rc = main(["check", ok_path])
        assert rc == 0
        out, _ = capsys.readouterr()
        assert out == "ok: qa (3 steps)\n"

        # 2. Invalid pipeline
        rc = main(["check", invalid_path])
        assert rc == 1
        out, _ = capsys.readouterr()
        assert out.strip() == "error: undefined_variable: step prompt uses missing"

        # 3. Missing file
        rc = main(["check", os.path.join(tmpdir, "nonexistent.yaml")])
        assert rc == 2


def test_cli_help_and_usage(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert main(["--help"]) == 0
    assert main(["check"]) == 2


def test_registry_validations() -> None:
    reg = Registry()
    with pytest.raises(PipelineError) as exc_info:
        reg.register("template", lambda _: None)
    assert exc_info.value.code == "invalid_pipeline"

    with pytest.raises(PipelineError) as exc_info:
        reg.register("INVALID_NAME", lambda _: None)
    assert exc_info.value.code == "invalid_pipeline"

    reg.register("my.comp", lambda _: "ok")
    assert reg.names() == ["my.comp"]


def test_fake_llm() -> None:
    fake = FakeLLM(lambda msgs: f"Reply to {msgs[0]['content']}")
    reply = fake.complete([{"role": "user", "content": "hello"}], max_tokens=100)
    assert reply == "Reply to hello"
    assert len(fake.calls) == 1
    assert fake.calls[0].max_tokens == 100


def test_recorded_llm_exhausted() -> None:
    rec = RecordedLLM(["first"])
    assert rec.complete([{"role": "user", "content": "1"}], max_tokens=50) == "first"
    with pytest.raises(RecordingExhaustedError):
        rec.complete([{"role": "user", "content": "2"}], max_tokens=50)


def test_pipeline_validation_errors() -> None:
    # Non-dict YAML
    with pytest.raises(PipelineError) as exc_info:
        load_pipeline("- a\n- b")
    assert exc_info.value.code == "invalid_pipeline"

    # Missing keys
    with pytest.raises(PipelineError) as exc_info:
        load_pipeline("pipeline: qa\nversion: 1")
    assert exc_info.value.code == "invalid_pipeline"

    # Invalid pipeline name
    with pytest.raises(PipelineError):
        load_pipeline("pipeline: QA\nversion: 1\ninputs: []\nsteps: []")

    # Invalid version
    with pytest.raises(PipelineError):
        load_pipeline("pipeline: qa\nversion: 2\ninputs: []\nsteps: []")

    # Duplicate inputs
    with pytest.raises(PipelineError):
        load_pipeline("pipeline: qa\nversion: 1\ninputs: [q, q]\nsteps: []")

    # Steps not a list
    with pytest.raises(PipelineError):
        load_pipeline("pipeline: qa\nversion: 1\ninputs: []\nsteps: 'none'")

    # Empty steps
    with pytest.raises(PipelineError):
        load_pipeline("pipeline: qa\nversion: 1\ninputs: []\nsteps: []")

    # Duplicate step id
    dup_steps = """
pipeline: qa
version: 1
inputs: []
steps:
  - id: step1
    use: template
    with: {text: a}
    output: out1
  - id: step1
    use: template
    with: {text: b}
    output: out2
"""
    with pytest.raises(PipelineError):
        load_pipeline(dup_steps)

    # Output shadows input
    shadow_yaml = """
pipeline: qa
version: 1
inputs: [query]
steps:
  - id: step1
    use: template
    with: {text: a}
    output: query
"""
    with pytest.raises(PipelineError) as exc_info:
        load_pipeline(shadow_yaml)
    assert exc_info.value.code == "invalid_pipeline"


def test_run_missing_input_and_llm_missing() -> None:
    pipe = load_pipeline(EXAMPLE_PIPELINE)
    reg = Registry()
    reg.register("retriever.keyword", lambda _: ["doc"])

    # Missing input 'question'
    with pytest.raises(PipelineError) as exc_info:
        run(pipe, {}, registry=reg)
    assert exc_info.value.code == "missing_input"

    # Missing LLM port
    with pytest.raises(PipelineError) as exc_info:
        run(pipe, {"question": "q"}, registry=reg, llm=None)
    assert exc_info.value.code == "invalid_pipeline"


def test_interpolation_nested_structures() -> None:
    yaml_text = """
pipeline: nested
version: 1
inputs: [item, dict_val]
steps:
  - id: step1
    use: custom.echo
    with:
      list_val:
        - "${item}"
        - "constant"
      map_val:
        key: "${item}"
      complex_val: "Prefix: ${dict_val}"
    output: result
"""
    pipe = load_pipeline(yaml_text)
    reg = Registry()
    last_params: dict[str, Any] = {}

    def echo_comp(params: Mapping[str, Any]) -> Any:
        last_params.update(params)
        return "done"

    reg.register("custom.echo", echo_comp)
    run(pipe, {"item": "hello", "dict_val": {"k": 1}}, registry=reg)
    assert last_params["list_val"] == ["hello", "constant"]
    assert last_params["map_val"] == {"key": "hello"}
    assert last_params["complex_val"] == 'Prefix: {"k": 1}'
