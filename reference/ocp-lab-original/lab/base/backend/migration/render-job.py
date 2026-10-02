#!/usr/bin/env python3
"""Render one approved Seokpan backend migration Job without handling secrets."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from string import Template

ACTIONS = ("current", "stamp-baseline", "upgrade-head")
MUTATING_ACTIONS = {"stamp-baseline", "upgrade-head"}

IMAGE_RE = re.compile(
    r"^harbor\.seokpan\.soldesk\.store/seokpan/backend@sha256:[0-9a-f]{64}$"
)

APPROVAL_REF_RE = re.compile(
    r"^seokpan/[a-z0-9._-]+#[1-9][0-9]*:issuecomment-[1-9][0-9]*$"
)

EXPECTED_HOST = "db.seokpan.soldesk.store"
EXPECTED_PORT = "3306"
EXPECTED_DATABASE = "stone_game"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Render a new approved one-shot backend migration Job."
    )
    p.add_argument("action", choices=ACTIONS)
    p.add_argument("--image", required=True)
    p.add_argument("--approval-ref")
    p.add_argument(
        "--template",
        type=Path,
        default=Path(__file__).with_name("job-template.yaml"),
    )
    p.add_argument("--output", type=Path)
    return p


def validate(args: argparse.Namespace) -> None:
    if not IMAGE_RE.fullmatch(args.image):
        raise ValueError(
            "image must be the approved Harbor Backend image pinned by sha256 digest"
        )

    if args.approval_ref is not None:
        if not args.approval_ref.strip():
            raise ValueError("approval-ref must not be blank")
        if "\n" in args.approval_ref or "\r" in args.approval_ref:
            raise ValueError("approval-ref must be a single line")
        if not APPROVAL_REF_RE.fullmatch(args.approval_ref):
            raise ValueError(
                "approval-ref must use "
                "seokpan/<repo>#<issue>:issuecomment-<comment-id>"
            )

    if args.action in MUTATING_ACTIONS and args.approval_ref is None:
        raise ValueError(f"{args.action} requires --approval-ref")

    if args.action == "current" and args.approval_ref is not None:
        raise ValueError("current does not use --approval-ref")


def yaml_arg(value: str) -> str:
    return f"            - {json.dumps(value)}"


def migration_args(args: argparse.Namespace) -> list[str]:
    values = [
        args.action,
        "--expect-host",
        EXPECTED_HOST,
        "--expect-port",
        EXPECTED_PORT,
        "--expect-database",
        EXPECTED_DATABASE,
    ]

    if args.action in MUTATING_ACTIONS:
        values.extend(
            [
                "--execute",
                "--approval-ref",
                args.approval_ref,
            ]
        )

    return values


def render(args: argparse.Namespace) -> str:
    template_text = args.template.read_text(encoding="utf-8")

    args_yaml = "\n".join(yaml_arg(value) for value in migration_args(args))

    rendered = Template(template_text).substitute(
        BACKEND_IMAGE=args.image,
        MIGRATION_ARGS=args_yaml,
    )

    if "${" in rendered:
        raise ValueError("rendered Job contains an unresolved template variable")

    return rendered


def main() -> int:
    args = parser().parse_args()

    try:
        validate(args)
        result = render(args)
    except (OSError, ValueError, KeyError) as exc:
        print(f"render refused: {exc}", file=sys.stderr)
        return 2

    if args.output:
        args.output.write_text(result, encoding="utf-8")
    else:
        sys.stdout.write(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
