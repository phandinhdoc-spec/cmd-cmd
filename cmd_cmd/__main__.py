"""JSON policy CLI. Does not change native Command Code configuration."""
import argparse
import json
import sys
import time
from pathlib import Path
from .pool import PolicyError, discover, route


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    listing = sub.add_parser("discover")
    listing.add_argument("--provider", required=True)
    listing.add_argument("--base-url", required=True, help="API root, usually ending /v1")
    listing.add_argument("--key-env", help="environment variable name, never a literal key")
    select = sub.add_parser("route")
    select.add_argument("--policy", required=True)
    select.add_argument("--catalog", required=True, help="JSON array of fresh provider snapshots")
    select.add_argument("--request", required=True)
    select.add_argument("--native-catalog", required=True, help="fresh snapshot of exact cmd --list-models IDs")
    select.add_argument("--overrides", default=".cmd/model-overrides.json")
    args = parser.parse_args()
    try:
        if args.action == "discover":
            ids = discover(args.base_url, args.key_env)
            result = {"provider": args.provider, "observed_at": time.time(),
                      "data": [{"id": model} for model in ids]}
        else:
            def read(path):
                return json.loads(Path(path).read_text())
            request = read(args.request)
            overrides = Path(args.overrides)
            if overrides.exists():
                roles = read(overrides)["roles"]
                if not isinstance(roles, dict):
                    raise PolicyError("invalid override roles")
                selection = roles.get(request["role"])
                if selection == "session" and request["role"] == "controller":
                    result = {"status": "MANUAL_SESSION", "reason": "use the current native session model; auto controller switching disabled"}
                    print(json.dumps(result))
                    return 0
                if selection is not None:
                    request["manual_native_id"] = selection
            result = route(read(args.policy), read(args.catalog), request,
                           native_catalog=read(args.native_catalog))
        print(json.dumps(result, indent=2, allow_nan=False))
        return 2 if result.get("status") == "BLOCKED" else 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        # Transport exceptions may contain endpoints, headers or secret values.
        print(json.dumps({"status": "BLOCKED", "reason": "discovery or policy validation failed"}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
