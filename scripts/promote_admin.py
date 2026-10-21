"""Promote an existing, verified WeShare! account to administrator.

Run from the project root:

    python scripts/promote_admin.py

The command is interactive on purpose: it requires the account email, the
account password and an explicit ``PROMOTE`` confirmation, so an administrator
cannot be created by a single accidental keystroke.
"""

import getpass
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select  # noqa: E402
from argon2 import PasswordHasher  # noqa: E402
from argon2.exceptions import Argon2Error  # noqa: E402

from backend.app.database import SessionLocal  # noqa: E402
from backend.app.models import User  # noqa: E402


def main() -> int:
    email = input("Verified account email to promote: ").strip().lower()
    if not email:
        print("No email supplied.")
        return 1
    confirmation = input("Type PROMOTE to continue: ").strip()
    if confirmation != "PROMOTE":
        print("Confirmation did not match.")
        return 1
    password = getpass.getpass("Confirm the account password: ")
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == email))
        if not user:
            print("No account found for that email.")
            return 1
        if not user.email_verified:
            print("That account has not completed email verification.")
            return 1
        try:
            PasswordHasher().verify(user.password_hash, password)
        except Argon2Error:
            print("Password confirmation failed.")
            return 1
        user.role = "admin"
        session.commit()
    print(f"Account {user.username} <{user.email}> promoted to administrator.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
