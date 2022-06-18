# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022  Philipp Emanuel Weidmann <pew@worldwidemann.com>

import os

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    Date,
    Text,
    ARRAY,
    Index,
    func,
)
from sqlalchemy.orm import sessionmaker, declarative_base


WIKIPEDIA_URL = "https://en.wikipedia.org"


engine = create_engine(os.environ["DATABASE_URL"])

Session = sessionmaker(engine, autoflush=False, autocommit=False)

Base = declarative_base()


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)

    date = Column(Date, nullable=False, index=True)
    description = Column(Text, nullable=False)
    context = Column(ARRAY(Text))
    category = Column(Text, index=True)

    search_text = Column(Text, nullable=False)

    __table_args__ = (
        Index(
            "search_index",
            func.to_tsvector("english", search_text),
            postgresql_using="gin",
        ),
    )
