"""Visible dcli-owned login helper for PipelinePilot."""

from __future__ import annotations

import argparse
import ctypes
import os
import subprocess


def _clean_environment() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("DASHLANE_SERVICE_DEVICE_KEYS", None)
    env.pop("DASHLANE_ENROLLED_TEAM_DEVICE_KEYS", None)
    return env


def _set_title() -> None:
    try:
        ctypes.windll.kernel32.SetConsoleTitleW("Unlock agent vault")
    except (AttributeError, OSError):
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", required=True)
    parser.add_argument("--state", choices=("locked", "not-logged-in"), required=True)
    parser.add_argument("--dcli-path", default="dcli")
    args = parser.parse_args(argv)

    _set_title()
    print("Unlock agent vault", flush=True)
    print(f"Agent account: {args.account}", flush=True)
    if args.state == "locked":
        print("Enter the agent vault master password when dcli asks.", flush=True)
    else:
        print("Login steps:", flush=True)
        print("1. Enter the agent account email shown above.", flush=True)
        print("2. Open the dashlane.com device-registration link.", flush=True)
        print("3. Paste the registration token.", flush=True)
        print("4. Enter the email or authenticator one-time code.", flush=True)
        print("5. Enter the agent vault master password.", flush=True)
    print("", flush=True)

    try:
        result = subprocess.run(
            [args.dcli_path, "sync"],
            shell=False,
            env=_clean_environment(),
        )
        return_code = result.returncode
    except OSError:
        return_code = 1

    if return_code == 0:
        return 0
    print(
        "Login did not complete. Close this window, then try the operation again.",
        flush=True,
    )
    input()
    return return_code or 1


if __name__ == "__main__":
    raise SystemExit(main())
