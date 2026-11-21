"""Load static reference data. Idempotent: safe to run repeatedly.

Usage: ``python -m app.seed``
"""

import logging

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import get_sessionmaker
from app.models import Currency, Exchange, Sector
from app.reference_data import CURRENCIES, EXCHANGES, SECTORS

log = logging.getLogger(__name__)


def seed_reference_data(session: Session) -> None:
    session.execute(
        insert(Currency)
        .values([{"code": code, "name": name} for code, name in CURRENCIES.items()])
        .on_conflict_do_update(
            index_elements=["code"], set_={"name": insert(Currency).excluded.name}
        )
    )

    stmt = insert(Exchange).values(list(EXCHANGES))
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=["mic"],
            set_={
                col: stmt.excluded[col]
                for col in ("name", "country_code", "timezone", "currency_code", "yahoo_suffix")
            },
        )
    )

    session.execute(
        insert(Sector).values([{"name": name} for name in SECTORS]).on_conflict_do_nothing()
    )
    session.commit()
    log.info(
        "Seeded %d currencies, %d exchanges, %d sectors",
        len(CURRENCIES),
        len(EXCHANGES),
        len(SECTORS),
    )


def main() -> None:
    configure_logging(get_settings().log_level)
    with get_sessionmaker()() as session:
        seed_reference_data(session)


if __name__ == "__main__":
    main()
