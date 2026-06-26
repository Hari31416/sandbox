# Nexus Sandbox Service

Standalone compute-plane service for sandbox lifecycle, execution, filesystem, and artifact export.

## Quick start

```bash
pip install -e ".[dev]"
sandbox-service
```

## Configuration

Set `SANDBOX_DEFAULT_BACKEND=local` for development or `microsandbox` for isolated microVM execution (requires `msb`).

See `sandbox_service_plan.md` for the full API contract.
