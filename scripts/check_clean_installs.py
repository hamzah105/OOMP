"""Install each built artifact into its own new core-only environment and verify it.

Requires package-index access for declared dependencies, never model services.
No environment or artifact is published. Existing output directories are refused.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def run(distributions: Path, output: Path):
    distributions = distributions.resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    artifacts = sorted([*distributions.glob("*.whl"), *distributions.glob("*.tar.gz")])
    if len(artifacts) != 2:
        raise ValueError("exactly one wheel and one source archive are expected")
    verifier = Path(__file__).with_name("verify_install.py").resolve()
    results = []
    for index, artifact in enumerate(artifacts):
        environment = output / f"environment-{index}"
        subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        with (output / f"install-{index}.txt").open("w", encoding="utf-8") as log:
            for command in ([str(python), "-m", "pip", "install", "--upgrade", "pip>=26.2.2,<27"],
                            [str(python), "-m", "pip", "install", str(artifact)],
                            [str(python), "-m", "pip", "check"]):
                subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
        subprocess.run([str(python), "-I", str(verifier), "--core-only", "--output", str(output / f"checks-{index}")], check=True, cwd=output)
        results.append({"artifact": artifact.name, "core_only_install": "passed", "CLI_and_source_flow": "passed"})
    (output / "clean-installs.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(run(args.dist, args.output), indent=2))


if __name__ == "__main__":
    main()
