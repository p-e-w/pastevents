# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022  Philipp Emanuel Weidmann <pew@worldwidemann.com>

from flask import Flask, request, render_template
from sqlalchemy import func
from sqlalchemy.orm import scoped_session

from common import Session, Base, Event, WIKIPEDIA_URL

# From the Flask-SQLAlchemy source code.
try:
    from greenlet import getcurrent as _ident_func
except ImportError:
    from threading import get_ident as _ident_func


app = Flask(__name__)


session = scoped_session(Session, scopefunc=_ident_func)

Base.query = session.query_property()


@app.teardown_appcontext
def remove_session(exception):
    session.remove()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/events")
def events():
    page = int(request.args["page"])
    size = int(request.args["size"])

    sort_field = request.args["sort[0][field]"]
    sort_dir = request.args["sort[0][dir]"]

    if sort_field == "date":
        sort = Event.date

    if sort_dir == "desc":
        sort = sort.desc()

    search = request.args.get("filter[0][value]")

    categories = []
    i = 0

    while True:
        category = request.args.get(f"filter[1][value][{i}]")
        if not category:
            break
        categories.append(category)
        i += 1

    min_date = request.args.get("filter[2][value]")
    max_date = request.args.get("filter[3][value]")

    query = Event.query

    if search:
        query = query.filter(
            func.to_tsvector("english", Event.search_text).op("@@")(
                func.websearch_to_tsquery("english", search)
            )
        )

    if categories:
        query = query.filter(Event.category.in_(categories))

    if min_date and max_date:
        query = query.filter(Event.date.between(min_date, max_date))

    query = query.order_by(sort, Event.id).limit(size).offset((page - 1) * size)

    events = []

    for event in query:
        date_url = f"{WIKIPEDIA_URL}/wiki/Portal:Current_events/{event.date:%-Y_%B_%-d}"

        events.append(
            {
                "date": f'<a href="{date_url}">{event.date:%Y-%m-%d}</a>',
                "description": event.description,
                "context": "<br>".join(event.context),
                "category": event.category,
            }
        )

    # Counting the total number of matching rows is expensive,
    # so this trick is used to make pagination continue
    # until the query returns fewer rows than requested.
    last_page = page if len(events) < size else 1000000000

    return {
        "last_page": last_page,
        "data": events,
    }
