# Testing Strategy

The library utilizes `pytest` to cover the following areas:

- **Acceptance Tests**: Verifies pipeline execution outputs, variable resolution, and trace generation in `tests/test_rag_pipeline_yaml.py`.
- **Static Analysis**: Ensures `load_pipeline` correctly rejects undefined variables, shadowed outputs, and illegal YAML structures.
- **Safety & Error Handling**: Tests `alias_forbidden`, `too_large`, and other `PipelineError` code paths.
- **Component Logic**: Validates `FakeLLM` and `RecordedLLM` behavior, including `RecordingExhaustedError`.
- **CLI Tool**: Validates exit codes and output messages for valid and invalid pipeline files.