"""Read-only catalog adapter and pure, fail-closed routing policy.

No inference, provider registration, credential persistence or agent loop lives here.
"""
from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
import json
import math
import os
import time
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener


class PolicyError(ValueError):
    """Invalid or insufficient evidence to route safely."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward an authorization header to another endpoint.


def number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PolicyError(f"{name} must be a finite non-negative number")
    if not math.isfinite(value) or value < 0:
        raise PolicyError(f"{name} must be a finite non-negative number")
    return value


def discover(base_url, key_env=None, timeout=5, opener=None):
    """Fetch one complete OpenAI-compatible /models listing; no retry/cache.

    base_url is the API root (normally ending /v1). API listings prove presence
    only; pricing and capabilities are supplied separately by trusted policy.
    """
    parsed = urlsplit(base_url)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise PolicyError("invalid API root")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise PolicyError("remote providers require HTTPS")
    if not 0 < number(timeout, "timeout") <= 30:
        raise PolicyError("timeout must be in (0, 30]")
    headers = {"Accept": "application/json"}
    if key_env:
        key = os.environ.get(key_env)
        if not key:
            raise PolicyError("provider key environment variable is missing")
        headers["Authorization"] = f"Bearer {key}"
    request = Request(base_url.rstrip("/") + "/models", headers=headers)
    transport = opener or build_opener(NoRedirect()).open
    with transport(request, timeout=timeout) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise PolicyError("catalog exceeds 2 MB")
    payload = json.loads(raw)
    return model_ids(payload)


def model_ids(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise PolicyError("catalog must contain data array")
    if payload.get("has_more") or payload.get("next") or payload.get("next_cursor"):
        raise PolicyError("paginated catalog requires a complete native snapshot")
    ids = set()
    for row in payload["data"]:
        if not isinstance(row, dict):
            raise PolicyError("invalid model record")
        model = row.get("id")
        if not isinstance(model, str) or not model or any(c.isspace() for c in model):
            raise PolicyError("invalid model id")
        ids.add(model)
    return sorted(ids)


@dataclass(frozen=True)
class Candidate:
    provider: str
    model: str
    native_id: str
    roles: tuple
    capabilities: tuple
    max_difficulty: int
    escalation_only: bool
    input_cost: float | None
    output_cost: float | None
    context_window: int
    max_output: int

    @property
    def identity(self):
        return f"{self.provider}/{self.model}"


def candidates(policy, snapshots, now=None):
    """Join fresh membership with explicit metadata; unknown models stay unroutable.

    Snapshots contain provider, observed_at (epoch), data:[{id:...}]. Provider
    failure is represented by absence of a snapshot, never a synthetic model.
    """
    now = time.time() if now is None else number(now, "now")
    ttl = number(policy["catalog_ttl_seconds"], "catalog TTL")
    providers = policy["providers"]
    seen_providers = set()
    result = []
    for snapshot in snapshots:
        provider = snapshot["provider"]
        if provider in seen_providers:
            raise PolicyError("duplicate provider snapshot")
        seen_providers.add(provider)
        spec = providers.get(provider)
        if not spec or spec.get("enabled") is not True:
            continue
        age = now - number(snapshot["observed_at"], "observed_at")
        if age < 0 or age > ttl:
            continue
        for model in model_ids(snapshot):
            metadata = {}
            for rule in spec.get("rules", []):
                if fnmatchcase(model, rule["match"]):
                    metadata.update(rule["metadata"])
            metadata.update(spec.get("models", {}).get(model, {}))
            required = {"roles", "capabilities", "max_difficulty", "escalation_only",
                        "context_window", "max_output"}
            if not required <= metadata.keys():
                continue
            if not isinstance(metadata["escalation_only"], bool):
                raise PolicyError("escalation_only must be boolean")
            for name in ("roles", "capabilities"):
                if not isinstance(metadata[name], list) or not all(isinstance(x, str) for x in metadata[name]):
                    raise PolicyError(f"{name} must be a string array")
            difficulty = number(metadata["max_difficulty"], "max_difficulty")
            if difficulty not in (1, 2, 3):
                raise PolicyError("max_difficulty must be 1, 2 or 3")
            cost = metadata.get("cost", {})
            costs = [None if cost.get(k) is None else number(cost[k], k) for k in ("input", "output")]
            native = metadata.get("native_id")
            if native is None and spec.get("native_prefix") is not None:
                native = spec["native_prefix"] + model
            if not isinstance(native, str) or not native or any(c.isspace() for c in native):
                continue
            result.append(Candidate(provider, model, native, tuple(metadata["roles"]),
                                    tuple(metadata["capabilities"]), difficulty,
                                    metadata["escalation_only"], *costs,
                                    number(metadata["context_window"], "context_window"),
                                    number(metadata["max_output"], "max_output")))
    return result


def route(policy, snapshots, request, now=None, native_catalog=None):
    """Return one decision, or BLOCKED; caller owns native execution and health."""
    now = time.time() if now is None else number(now, "now")
    if native_catalog is None:
        return {"status": "BLOCKED", "reason": "fresh native Command Code model list required"}
    age = now - number(native_catalog["observed_at"], "native observed_at")
    if age < 0 or age > number(policy["catalog_ttl_seconds"], "catalog TTL"):
        return {"status": "BLOCKED", "reason": "native model list is stale"}
    allowed = set(model_ids(native_catalog))
    manual = request.get("manual_native_id")
    if manual is not None and (not isinstance(manual, str) or manual not in allowed):
        return {"status": "BLOCKED", "reason": "manual model is unavailable in Command Code; choose again or use auto"}
    role = request["role"]
    if role not in policy["preferences"]:
        raise PolicyError("unknown role")
    difficulty = number(request.get("difficulty", 2), "difficulty")
    if difficulty not in (1, 2, 3):
        raise PolicyError("difficulty must be 1, 2 or 3")
    input_tokens = number(request["input_tokens"], "input_tokens")
    output_tokens = number(request["output_tokens"], "output_tokens")
    budget = number(request["max_cost_usd"], "max_cost_usd")
    attempted = request.get("attempted", [])
    unavailable = request.get("unavailable", [])
    required = request.get("capabilities", ["tools"])
    for value in (attempted, unavailable, required):
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            raise PolicyError("attempted, unavailable and capabilities must be string arrays")
    limit = number(policy["max_attempts"], "max_attempts")
    if limit < 1 or int(limit) != limit:
        raise PolicyError("max_attempts must be a positive integer")
    if len(attempted) >= limit:
        return {"status": "BLOCKED", "reason": "attempt budget exhausted"}
    escalation = difficulty == 3 or request.get("verified_failure") is True or manual is not None
    preferences = policy["preferences"][role]
    if role == "planner" and difficulty == 1:
        preferences = list(dict.fromkeys(policy.get("light_planner_preferences", []) + preferences))
    ranked = []
    for model in candidates(policy, snapshots, now):
        if (model.native_id not in allowed or (manual is not None and model.native_id != manual)
                or model.identity in attempted or model.identity in unavailable
                or model.provider in unavailable or role not in model.roles
                or not set(required) <= set(model.capabilities)
                or difficulty > model.max_difficulty
                or (model.escalation_only and not escalation)
                or input_tokens + output_tokens > model.context_window
                or output_tokens > model.max_output):
            continue
        # Unknown cost is not zero, even for BYOK/subscription access.
        if model.input_cost is None or model.output_cost is None:
            continue
        cost = (input_tokens * model.input_cost + output_tokens * model.output_cost) / 1_000_000
        if cost > budget:
            continue
        preferred = next((i for i, pattern in enumerate(preferences)
                          if fnmatchcase(model.identity, pattern)), len(preferences))
        # Pool order first: GOAT is supplemental even when nominally cheaper.
        pool = policy["providers"][model.provider].get("priority", 100)
        number(pool, "provider priority")
        ranked.append(((pool, preferred, cost, model.identity), model, cost))
    if not ranked:
        return {"status": "BLOCKED", "reason": ("manual model failed capability, health or budget gates; choose again or use auto" if manual else "no fresh, capable, affordable model; refresh or add verified metadata")}
    _, model, cost = min(ranked, key=lambda item: item[0])
    return {"status": "ROUTED", "provider": model.provider, "model": model.model,
            "identity": model.identity, "native_model": model.native_id,
            "estimated_cost_usd": cost, "role": role, "difficulty": difficulty,
            "reason": "capability/budget gates passed; pool priority, role preference, then estimated cost",
            "escalation_allowed": escalation, "manual": manual is not None,
            "attempt": len(attempted) + 1}
