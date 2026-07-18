"""Fail-closed startup checks for non-demo sandbox deploy profiles (H1)."""

from __future__ import annotations

SECURE_PROFILES = frozenset({"staging", "saas-prod", "selfhost"})


class SecureDefaultsError(RuntimeError):
    """Raised when a secure deploy profile is missing required controls."""

    def __init__(self, profile: str, problems: list[str]) -> None:
        self.profile = profile
        self.problems = problems
        bullets = "\n".join(f"  - {item}" for item in problems)
        super().__init__(
            f"SANDBOX_DEPLOY_PROFILE={profile!r} refused to start:\n{bullets}"
        )


def is_secure_profile(deploy_profile: str) -> bool:
    return (deploy_profile or "").strip().lower() in SECURE_PROFILES


def validate_sandbox_secure_defaults(
    *,
    deploy_profile: str,
    auth_token: str | None,
) -> None:
    profile = (deploy_profile or "local").strip().lower() or "local"
    if profile not in SECURE_PROFILES:
        return
    problems: list[str] = []
    if not (auth_token or "").strip():
        problems.append("SANDBOX_AUTH_TOKEN is required (non-empty bearer token)")
    if problems:
        raise SecureDefaultsError(profile, problems)
