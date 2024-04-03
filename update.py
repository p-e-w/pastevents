# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022  Philipp Emanuel Weidmann <pew@worldwidemann.com>

import re
from copy import copy
from datetime import datetime, date
from argparse import ArgumentParser

import requests
from dateutil.relativedelta import relativedelta
from bs4 import BeautifulSoup

from countries import FLAG_DATA
from common import Session, Base, Event, engine, WIKIPEDIA_URL


MIN_DATE = date(2003, 1, 1)


country_names = list(FLAG_DATA)

# Sort names by descending length to ensure that if the name of one country
# contains the name of another, the longer name is matched wherever it occurs.
country_names.sort(key=len, reverse=True)

country_names = map(re.escape, country_names)

country_name_regex = re.compile(r"(?<!\w)(?:" + "|".join(country_names) + r")(?!\w)")

used_flags = set()


def insert_flags(html):
    def replace(match):
        country_name = match.group(0)
        flag = FLAG_DATA[country_name]

        if flag in used_flags:
            return country_name
        else:
            used_flags.add(flag)
            # A non-breaking space between flag and country name
            # prevents them from being wrapped into separate lines.
            return f"{flag}\xa0{country_name}"

    document = BeautifulSoup(html, "html.parser")

    for string in document.find_all(string=True):
        string.replace_with(country_name_regex.sub(replace, str(string)))

    return str(document)


def normalize_category(category):
    if category is None:
        return None

    category = category.lower()

    if "conflict" in category or "attack" in category:
        return "Armed conflicts and attacks"
    elif "art" in category or "cultur" in category:
        return "Arts and culture"
    elif "business" in category or "econom" in category:
        return "Business and economy"
    elif "disaster" in category or "accident" in category:
        return "Disasters and accidents"
    elif "health" in category or "environment" in category:
        return "Health and environment"
    elif "international" in category or "relation" in category:
        return "International relations"
    elif "law" in category or "crim" in category:
        return "Law and crime"
    elif "politic" in category or "election" in category:
        return "Politics and elections"
    elif "scien" in category or "tech" in category:
        return "Science and technology"
    elif "sport" in category and "transport" not in category:
        return "Sports"
    else:
        return None


def get_event_elements(list_element, context_elements=[]):
    for item_element in list_element.find_all("li", recursive=False):
        sublist_element = item_element.find("ul", recursive=False)

        if sublist_element is None:
            # Terminal list item.
            if item_element.get_text().strip():
                yield item_element, context_elements

        else:
            context_element = BeautifulSoup("<li></li>", "html.parser").li

            for node in item_element.children:
                if node.name == "ul":
                    break
                context_element.append(copy(node))

            yield from get_event_elements(
                sublist_element,
                [*context_elements, context_element],
            )


def get_events(html):
    document = BeautifulSoup(html, "html.parser")

    # Turn relative link URLs into absolute ones.
    for link_element in document.find_all("a"):
        if link_element.get("href", "").startswith("/"):
            link_element["href"] = WIKIPEDIA_URL + link_element["href"]

    # Remove image thumbnails.
    for thumbnail_element in document.find_all("figure"):
        thumbnail_element.decompose()

    for day_element in document.find_all("div", class_="current-events-main"):
        content_element = day_element.find("div", class_="current-events-content")

        date_string = day_element["id"]
        date = datetime.strptime(date_string, "%Y_%B_%d").date()
        category = None

        for element in content_element.find_all(True, recursive=False):
            if element.name == "ul":
                for event_element, context_elements in get_event_elements(element):
                    # Reset the used flags tracker before processing each event
                    # so that each flag is inserted at most once into an event's data.
                    used_flags.clear()

                    yield Event(
                        date=date,
                        description=insert_flags(event_element.decode_contents()),
                        context=[
                            insert_flags(context_element.decode_contents())
                            for context_element in context_elements
                        ],
                        category=normalize_category(category),
                        search_text="\n".join(
                            [
                                element.get_text()
                                for element in [
                                    event_element,
                                    *context_elements,
                                ]
                            ]
                        ),
                    )

                category = None

            elif "current-events-content-heading" in element.get("class", []):
                # Old-style category heading.
                category = element.get_text()

            else:
                heading_element = element.find("b")
                if heading_element is not None:
                    # New-style category heading.
                    category = heading_element.get_text()


def update_events(start_date, end_date):
    requests_session = requests.Session()

    parameters = {
        "action": "parse",
        "format": "json",
    }

    with Session.begin() as session:
        session.query(Event).filter(Event.date.between(start_date, end_date)).delete(
            synchronize_session="fetch"
        )

        month = start_date.replace(day=1)

        while month <= end_date:
            parameters["page"] = f"Portal:Current_events/{month:%B_%-Y}"
            response = requests_session.get(
                f"{WIKIPEDIA_URL}/w/api.php", params=parameters
            )

            if response.status_code == 200:
                print(f'Parsing events from page {parameters["page"]} ...')
                for event in get_events(response.json()["parse"]["text"]["*"]):
                    if start_date <= event.date <= end_date:
                        session.add(event)
            else:
                raise RuntimeError(
                    f'Request for page {parameters["page"]} failed with {response.status_code}.'
                )

            month += relativedelta(months=1)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--days", type=int)
    arguments = parser.parse_args()

    Base.metadata.create_all(engine)

    if arguments.days is None:
        start_date = MIN_DATE
        end_date = date.today()
    else:
        start_date = max(
            date.today() - relativedelta(days=arguments.days - 1), MIN_DATE
        )
        end_date = date.today()

    update_events(start_date, end_date)
