"""Operator commands. There is no public sign-up (spec section 2); admins create users.

uv run python -m app.cli create-user --name "…" --mobile 0912… --role admin
"""

import argparse
import sys

from sqlalchemy import or_, select

from app.core.normalize import normalize_email, normalize_mobile
from app.db.session import SessionLocal
from app.modules.identity.models import Role, User


def create_user(name: str, mobile: str | None, email: str | None, role: Role) -> int:
    norm_mobile = normalize_mobile(mobile) if mobile else None
    norm_email = normalize_email(email) if email else None
    if mobile and norm_mobile is None:
        print("Invalid mobile number", file=sys.stderr)
        return 1
    if email and norm_email is None:
        print("Invalid email address", file=sys.stderr)
        return 1
    if not (norm_mobile or norm_email):
        print("Provide --mobile and/or --email", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        conditions = []
        if norm_mobile:
            conditions.append(User.mobile == norm_mobile)
        if norm_email:
            conditions.append(User.email == norm_email)
        if db.scalar(select(User).where(or_(*conditions))):
            print("A user with this mobile or email already exists", file=sys.stderr)
            return 1
        user = User(full_name=name, mobile=norm_mobile, email=norm_email, role=role)
        db.add(user)
        db.commit()
        print(f"Created {role.value} {user.id} ({norm_mobile or ''} {norm_email or ''})".strip())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    cu = sub.add_parser("create-user", help="Create a staff user")
    cu.add_argument("--name", required=True)
    cu.add_argument("--mobile")
    cu.add_argument("--email")
    cu.add_argument("--role", choices=[r.value for r in Role], default=Role.SALES_REP.value)
    args = parser.parse_args(argv)

    if args.command == "create-user":
        return create_user(args.name, args.mobile, args.email, Role(args.role))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
