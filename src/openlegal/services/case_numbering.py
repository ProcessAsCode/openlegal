"""Case-number allocation.

Format: `{ORG_SLUG}-{YEAR}-{NNNNN}` where NNNNN is a 5-digit, zero-padded,
monotonic counter resetting each calendar year.

Phase 1 implementation: read the highest existing case_number for (org, year),
parse the counter, return the next. This is *not* concurrency-safe; two parallel
inserts will fight on the unique `(org_id, case_number)` constraint and one
will retry. That's acceptable for the sandbox PoC volume (≤ ~300 incidents/month
at the org). Phase 2 will replace this with a per-org/year sequence.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openlegal.models.case import Case
from openlegal.models.organization import Organization


_NUMBER_RE = re.compile(r"^(?P<prefix>.+)-(?P<year>\d{4})-(?P<seq>\d{5,})$")


async def allocate_case_number(
    session: AsyncSession,
    org: Organization,
    now: datetime | None = None,
) -> str:
    """Return the next case number for `org` in the current year.

    Reserves nothing — the caller must INSERT with the returned number and
    handle the UniqueViolation on race via a retry of this function.
    """
    now = now or datetime.now(timezone.utc)
    year = now.year
    prefix = org.slug.upper()

    stmt = (
        select(Case.case_number)
        .where(Case.org_id == org.id)
        .where(Case.case_number.like(f"{prefix}-{year}-%"))
        .order_by(Case.case_number.desc())
        .limit(1)
    )
    last = (await session.execute(stmt)).scalar_one_or_none()

    if last is None:
        next_seq = 1
    else:
        m = _NUMBER_RE.match(last)
        if not m:
            # Schema invariant broken; fail loudly so it surfaces in tests.
            raise RuntimeError(f"Cannot parse case_number {last!r}")
        next_seq = int(m.group("seq")) + 1

    return f"{prefix}-{year}-{next_seq:05d}"


__all__ = ["allocate_case_number"]
