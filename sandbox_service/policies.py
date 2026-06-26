from __future__ import annotations

from microsandbox import Action, Direction, Network, NetworkPolicy, Protocol, Rule


def build_network(mode: str, allowed_hosts: list[str]) -> Network:
    normalized_mode = mode.strip().lower()
    if normalized_mode in {"disabled", "none"}:
        return Network.none()
    if normalized_mode == "public":
        return Network.public_only()
    if normalized_mode != "allowlist":
        raise ValueError(f"Unsupported network mode: {mode}")

    hosts = tuple(
        sorted({normalize_host(host) for host in allowed_hosts if host.strip()})
    )
    if not hosts:
        raise ValueError(
            "allowed_hosts must contain at least one host when network is allowlist"
        )
    rules = [
        Rule.allow(
            direction=Direction.EGRESS,
            destination=host,
            protocol=Protocol.TCP,
            port=80,
        )
        for host in hosts
    ]
    rules.extend(
        Rule.allow(
            direction=Direction.EGRESS,
            destination=host,
            protocol=Protocol.TCP,
            port=443,
        )
        for host in hosts
    )
    rules.extend(
        [
            Rule.allow(
                direction=Direction.EGRESS,
                destination="*",
                protocol=Protocol.UDP,
                port=53,
            ),
            Rule.allow(
                direction=Direction.EGRESS,
                destination="*",
                protocol=Protocol.TCP,
                port=53,
            ),
            Rule.deny(direction=Direction.EGRESS, destination="metadata"),
            Rule.deny(direction=Direction.EGRESS, destination="private"),
        ]
    )
    return Network(policy=NetworkPolicy(default_action=Action.DENY, rules=tuple(rules)))


def normalize_host(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError("allowed_hosts cannot contain empty values")
    return normalized
