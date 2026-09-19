#!/usr/bin/env python3
"""Inspect local prospect history or record explicit user feedback/outcomes."""

import argparse
import json
from pathlib import Path

from prospect_data import FEEDBACK, STATUSES, atomic_json, read_state, state_lock, timestamp


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("show")
    feedback = commands.add_parser("feedback")
    feedback.add_argument("id")
    feedback.add_argument("verdict", choices=FEEDBACK)
    feedback.add_argument("--reason", required=True)
    status = commands.add_parser("status")
    status.add_argument("id")
    status.add_argument("value", choices=STATUSES)
    profile = commands.add_parser("profile")
    for field in ("prefer", "avoid"):
        group = profile.add_mutually_exclusive_group()
        group.add_argument(f"--{field}", action="append")
        group.add_argument(f"--clear-{field}", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "show":
            print(json.dumps(read_state(args.state), indent=2, ensure_ascii=False))
            return
        with state_lock(args.state):
            state = read_state(args.state)
            if args.command == "profile":
                for field in ("prefer", "avoid"):
                    values = getattr(args, field)
                    if values is not None:
                        if any(not x.strip() for x in values):
                            raise ValueError("Search preferences cannot be empty")
                        state["profile"][field] = list(dict.fromkeys(x.strip() for x in values))
                    elif getattr(args, f"clear_{field}"):
                        state["profile"][field] = []
            else:
                if args.id not in state["prospects"]:
                    raise ValueError("Unknown prospect ID; resolve it from the relevant report")
                record = state["prospects"][args.id]
                if args.command == "feedback":
                    if not args.reason.strip():
                        raise ValueError("Feedback reason cannot be empty")
                    record.update(feedback=args.verdict, feedback_reason=args.reason.strip(), feedback_at=timestamp())
                else:
                    record.update(status=args.value, status_updated_at=timestamp())
            state["updated_at"] = timestamp()
            atomic_json(args.state, state)
        print(f"Updated local {args.command}: {args.state.resolve()}. No message was sent.")
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
