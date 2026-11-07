"""CLI entry point for rag-pipeline-yaml."""

from __future__ import annotations

import os
import sys

from rag_pipeline_yaml import PipelineError, load_pipeline


def main(argv: list[str] | None = None) -> int:
    """Run CLI commands.

    Exit codes:
      0: ok
      1: findings or domain failure (PipelineError)
      2: usage, IO or parse error
    """
    if argv is None:
        argv = sys.argv[1:]

    if not argv or argv[0] not in ("check", "--help", "-h"):
        sys.stderr.write("usage: rag-pipeline-yaml check <pipeline.yaml>\n")
        return 2

    if argv[0] in ("--help", "-h"):
        sys.stdout.write("usage: rag-pipeline-yaml check <pipeline.yaml>\n")
        return 0

    if len(argv) < 2:
        sys.stderr.write("usage: rag-pipeline-yaml check <pipeline.yaml>\n")
        return 2

    file_path = argv[1]
    if not os.path.exists(file_path):
        sys.stderr.write(f"error: file not found: {file_path}\n")
        return 2

    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
    except Exception as exc:
        sys.stderr.write(f"error: failed to read file: {exc}\n")
        return 2

    try:
        pipe = load_pipeline(content)
        sys.stdout.write(f"ok: {pipe.name} ({len(pipe.steps)} steps)\n")
        return 0
    except PipelineError as exc:
        sys.stdout.write(f"error: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
