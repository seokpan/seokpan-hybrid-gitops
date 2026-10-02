"""Build with Kustomize and withhold unresolved draft output.

This is a source input gate, not a deployment tool or Runtime readiness proof.
No cluster, registry, AWS or GitHub API calls are made by this script.
"""

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("environment", choices=("lab", "cloud", "recovery"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--kustomize", default=os.environ.get("KUSTOMIZE", "kustomize"))
    args = parser.parse_args()
    try:
        version = subprocess.run([args.kustomize, "version"], check=True,
                                 capture_output=True, text=True).stdout.strip()
        if version != "v5.7.1":
            print("release withheld: expected Kustomize v5.7.1", file=sys.stderr)
            return 2
        result = subprocess.run(
            [args.kustomize, "build", str(ROOT / "apps/overlays" / args.environment)],
            check=True, capture_output=True, text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        print("release withheld: Kustomize version/build failed", file=sys.stderr)
        return 2
    blockers = []
    for label, pattern in (
        ("INPUT_REQUIRED", r"INPUT_REQUIRED"),
        ("reserved .invalid endpoint", r"\.invalid(?:[:/\s\"']|$)"),
        ("input-required draft marker", r"input-required"),
        ("zero-replica activation hold", r"(?m)^\s*replicas:\s*0\s*$"),
    ):
        if re.search(pattern, result.stdout):
            blockers.append(label)
    if not result.stdout.strip():
        blockers.append("empty manifest")
    if blockers:
        print("release withheld: " + ", ".join(blockers), file=sys.stderr)
        return 2
    # Commit the output atomically without replacing an existing artifact.
    # link() also refuses an existing symlink, including a dangling one.
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=args.output.parent, delete=False) as tmp:
            temp_path = Path(tmp.name)
            tmp.write(result.stdout)
        os.link(temp_path, args.output)
    except FileExistsError:
        print("release withheld: output already exists", file=sys.stderr)
        return 2
    except OSError:
        print("release withheld: could not write output", file=sys.stderr)
        return 2
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    print("source input gate passed; Runtime/owner acceptance remains separate", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
