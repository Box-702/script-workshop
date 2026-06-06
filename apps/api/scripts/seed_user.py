"""Seed 2 projects and 1 active model key for the real Supabase user.

Run from the repo root:
    cd apps/api && .venv/Scripts/python.exe scripts/seed_user.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from app.db import SessionLocal, Project, UserModelKey  # noqa: E402
from app.ids import gen_id  # noqa: E402

USER_UUID = "9d928dc2-c744-4a5f-802e-f59a42bc254b"


def main() -> None:
    with SessionLocal() as db:
        # Skip if already seeded.
        existing = (
            db.query(Project)
            .filter_by(owner_id=USER_UUID)
            .count()
        )
        if existing:
            print(f"Already have {existing} projects for user; skipping seed.")
            return

        p1 = Project(
            id=gen_id("proj"),
            owner_id=USER_UUID,
            title="雨夜来客",
            adaptation_type="short_drama",
            language="zh-CN",
            status="created",
        )
        p2 = Project(
            id=gen_id("proj"),
            owner_id=USER_UUID,
            title="消失的她",
            adaptation_type="film",
            language="zh-CN",
            status="created",
        )
        db.add_all([p1, p2])
        db.flush()

        # 1 active model key — encrypted_api_key is just a placeholder here
        # so we don't need KEY_ENCRYPTION_KEY set for this seed step.
        # The real /settings endpoint encrypts properly.
        key = UserModelKey(
            id=gen_id("key"),
            user_id=USER_UUID,
            provider="openai",
            base_url="https://api.openai.com/v1",
            default_model="gpt-4o-mini",
            encrypted_api_key="placeholder-not-encrypted-seed",
            key_last4="0000",
            status="active",
        )
        db.add(key)
        db.commit()
        print(f"Seeded 2 projects + 1 model key for user {USER_UUID}")


if __name__ == "__main__":
    main()
