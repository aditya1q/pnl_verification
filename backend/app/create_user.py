"""Create a login user from the command line (use it for the first admin).

    python -m app.create_user admin --role admin            # asks for the password
    python -m app.create_user ravi --role viewer
    python -m app.create_user admin --reset                 # new password, re-enable, sign out everywhere

Roles: admin (everything + users), operator (view + imports / LTP), viewer (view only).
After the first admin exists, manage users from the app (Users page) instead.
"""
from __future__ import annotations

import argparse
import getpass

from fastapi import HTTPException

from .auth import ROLES, create_user, find_user, get_db, update_user


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create or reset a login user.")
    parser.add_argument("username")
    parser.add_argument("--role", choices=ROLES, help="default: viewer for a new user, unchanged for --reset")
    parser.add_argument("--password", help="omit to be asked (safer: not kept in shell history)")
    parser.add_argument("--reset", action="store_true", help="the user exists: set a new password and re-enable it")
    args = parser.parse_args(argv)

    password = args.password
    if password is None:
        password = getpass.getpass(f"Password for {args.username}: ")
        if getpass.getpass("Repeat password: ") != password:
            raise SystemExit("Passwords do not match.")

    db = get_db()
    try:
        if args.reset:
            if not find_user(db, args.username):
                raise SystemExit(f"User '{args.username}' not found.")
            user = update_user(db, args.username, password=password, role=args.role, active=True)
            print(f"Reset '{user['username']}' (role {user['role']}); all its sessions were signed out.")
        else:
            user = create_user(db, args.username, password, args.role or "viewer", created_by="cli")
            print(f"Created '{user['username']}' with role {user['role']}.")
    except HTTPException as exc:
        raise SystemExit(exc.detail) from exc


if __name__ == "__main__":
    main()
