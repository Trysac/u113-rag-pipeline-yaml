# rag-pipeline-yaml

Declarative RAG pipelines in YAML: registered components, typed variable interpolation, static checks before any step runs, alias-free safe loading and content-free traces.

## The Problem

RAG prototypes often hard-code retrieval, prompt building, and generation in monolithic scripts. This couples logic, makes configuration changes like step order or template modification difficult to audit, and obscures execution performance or failure points. This library provides a declarative alternative that loads YAML definitions, enforces static structure, and tracks performance without leaking sensitive data.

## Installation

```bash
pip install trysac-rag-pipeline-yaml
```

## Usage Example

```python
from rag_pipeline_yaml import Registry, RecordedLLM, load_pipeline, run

reg = Registry()
reg.register("retriever", lambda p: ["doc1"])
llm = RecordedLLM(["42"])
pipe = load_pipeline(
    "pipeline: q\nversion: 1\ninputs: [q]\nsteps:\n  - id: a\n    use: llm\n    with: {prompt: '${q}'}\n    output: ans"
)
res = run(pipe, {"q": "hi"}, registry=reg, llm=llm)
print(res.outputs["ans"])  # 42
```

## API Summary

- `load_pipeline(text: str, *, max_bytes: int = 65_536) -> Pipeline`: Load and statically validate a YAML pipeline.
- `Registry`: Component registry for custom functions. Supports `.register(name, fn)` and `.get(name)`.
- `run(pipeline, inputs, *, registry, llm=None, clock=time.monotonic) -> RunResult`: Execute the pipeline.
- `Pipeline`, `Step`, `RunResult`, `StepTrace`: Frozen dataclasses defining the execution model.
- `PipelineError`: Raised with specific codes: `invalid_yaml`, `alias_forbidden`, `too_large`, `invalid_pipeline`, `undefined_variable`, `unknown_component`, `step_failed`, `missing_input`.

## Why not LangChain/Haystack?

Unlike large frameworks, this library has zero runtime dependencies, strictly validates variable references at load time, and enforces safe YAML parsing by default. It is designed for small, reviewable, and deterministic pipeline definitions.

## Security

See [docs/SECURITY.md](docs/SECURITY.md).