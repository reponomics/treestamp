"""Environment configuration, read once at startup from uppercase field names."""

from __future__ import annotations

from dataclasses import dataclass, fields
from functools import cached_property
from ipaddress import IPv4Network, IPv6Network, ip_network
from typing import TYPE_CHECKING

from treestamp_web.routing import MAX_REPLAY_BODY, valid_machine_id

if TYPE_CHECKING:
    from collections.abc import Mapping

_LOG_LEVELS = ("debug", "info", "warning", "error")


class ConfigError(ValueError):
    """An environment variable holds a value the service cannot use."""


@dataclass(frozen=True)
class Config:
    port: int = 8000
    github_token: str | None = None
    github_app_client_id: str | None = None
    github_app_installation_id: str | None = None
    github_app_private_key: str | None = None
    github_api_url: str = "https://api.github.com"
    github_rate_reserve: int = 100
    request_timeout_seconds: float = 20.0
    symlink_fetch_limit: int = 32
    cache_max_trees: int = 256
    cache_max_entries: int = 2_000_000
    cache_max_blobs: int = 4096
    cache_max_blob_bytes: int = 64 * 1024 * 1024
    rate_limit_per_minute: int = 20
    op_rate_limit_per_minute: int = 240
    max_state_bytes: int = 262_144
    trust_proxy: bool = False
    client_ip_header: str = "X-Forwarded-For"
    cloudflare_proxy_cidrs: str = ""
    fly_session_routing: bool = False
    fly_machine_id: str | None = None
    public_base_url: str | None = None
    log_level: str = "info"
    build_commit: str = "unknown"

    @property
    def session_machine_id(self) -> str | None:
        if not self.fly_session_routing:
            return None
        machine = valid_machine_id(self.fly_machine_id)
        if machine is None:
            raise ConfigError("FLY_SESSION_ROUTING requires a valid FLY_MACHINE_ID")
        if self.max_state_bytes > MAX_REPLAY_BODY:
            raise ConfigError(
                f"FLY_SESSION_ROUTING requires MAX_STATE_BYTES <= {MAX_REPLAY_BODY}"
            )
        return machine

    @cached_property
    def cloudflare_networks(self) -> tuple[IPv4Network | IPv6Network, ...]:
        """Opt in to Cloudflare visitor headers behind Fly's trusted ingress."""
        if not self.cloudflare_proxy_cidrs:
            return ()
        if not self.trust_proxy or self.client_ip_header.lower() != "fly-client-ip":
            raise ConfigError(
                "CLOUDFLARE_PROXY_CIDRS requires TRUST_PROXY=1 and "
                "CLIENT_IP_HEADER=Fly-Client-IP"
            )
        try:
            networks = tuple(
                ip_network(value.strip())
                for value in self.cloudflare_proxy_cidrs.split(",")
            )
        except ValueError as exc:
            raise ConfigError(
                "CLOUDFLARE_PROXY_CIDRS must contain valid CIDRs"
            ) from exc
        if any(network.prefixlen == 0 for network in networks):
            raise ConfigError("CLOUDFLARE_PROXY_CIDRS must not trust every address")
        return networks

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Config:
        values: dict[str, object] = {}
        for field in fields(cls):
            name = field.name.upper()
            raw = env.get(name)
            if raw is None or raw == "":
                continue
            values[field.name] = _convert(name, raw, field.type)
        config = cls(**values)  # type: ignore[arg-type]
        config.validate()
        return config

    def validate(self) -> None:
        _ = self.cloudflare_networks
        _ = self.session_machine_id
        for name in (
            "port",
            "github_rate_reserve",
            "symlink_fetch_limit",
            "cache_max_trees",
            "cache_max_entries",
            "cache_max_blobs",
            "cache_max_blob_bytes",
            "rate_limit_per_minute",
            "op_rate_limit_per_minute",
            "max_state_bytes",
        ):
            if getattr(self, name) < 0:
                raise ConfigError(f"{name.upper()} must not be negative")
        if self.port > 65535:
            raise ConfigError("PORT must be at most 65535")
        for name in ("request_timeout_seconds",):
            if getattr(self, name) <= 0:
                raise ConfigError(f"{name.upper()} must be positive")
        app = (
            self.github_app_client_id,
            self.github_app_installation_id,
            self.github_app_private_key,
        )
        if any(app) and not all(app):
            raise ConfigError(
                "GITHUB_APP_CLIENT_ID, GITHUB_APP_INSTALLATION_ID, and "
                "GITHUB_APP_PRIVATE_KEY must be set together"
            )
        if self.github_app_private_key is not None and (
            "-----BEGIN" not in self.github_app_private_key
        ):
            raise ConfigError("GITHUB_APP_PRIVATE_KEY must be a PEM private key")
        if self.log_level not in _LOG_LEVELS:
            raise ConfigError(f"LOG_LEVEL must be one of {', '.join(_LOG_LEVELS)}")
        if not self.github_api_url.startswith(("http://", "https://")):
            raise ConfigError("GITHUB_API_URL must be an http or https URL")
        if self.public_base_url is not None and not self.public_base_url.startswith(
            ("http://", "https://")
        ):
            raise ConfigError("PUBLIC_BASE_URL must be an http or https URL")


def _convert(name: str, raw: str, annotation: object) -> object:
    kind = str(annotation)
    try:
        if kind == "int":
            return int(raw)
        if kind == "float":
            return float(raw)
        if kind == "bool":
            if raw in ("1", "true", "yes"):
                return True
            if raw in ("0", "false", "no"):
                return False
            raise ValueError(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} has an invalid value: {raw!r}") from exc
    if name == "LOG_LEVEL":
        return raw.lower()
    if name == "GITHUB_APP_PRIVATE_KEY":
        # Hosts that flatten secrets to one line leave literal "\n" sequences.
        return raw.replace("\\n", "\n")
    return raw.rstrip("/") if name.endswith("_URL") else raw
