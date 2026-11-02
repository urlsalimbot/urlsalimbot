"""Refresh the GitHub stats baked into the profile SVGs."""

import json
import os
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from config import BIRTHDATE, USER_NAME

ROOT = Path(__file__).resolve().parent.parent
TOKEN = os.environ.get("ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN")
ENDPOINT = "https://api.github.com/graphql"

USER_QUERY = """
query($login: String!) {
  user(login: $login) {
    createdAt
    followers { totalCount }
    repositories(ownerAffiliations: OWNER, first: 100) {
      totalCount
      nodes { stargazerCount isFork }
    }
    contributed: repositories(
      ownerAffiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER], first: 1
    ) { totalCount }
  }
}
"""

CONTRIB_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar { totalContributions }
    }
  }
}
"""


def gql(query: str, variables: dict) -> dict:
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": USER_NAME,
        },
    )
    with urllib.request.urlopen(request) as response:
        payload = json.load(response)
    if "errors" in payload:
        raise SystemExit(f"GitHub API error: {payload['errors']}")
    return payload["data"]


def total_contributions(created_at: datetime) -> int:
    now = datetime.now(timezone.utc)
    total = 0
    for year in range(created_at.year, now.year + 1):
        start = max(datetime(year, 1, 1, tzinfo=timezone.utc), created_at)
        end = min(datetime(year + 1, 1, 1, tzinfo=timezone.utc), now)
        if start < end:
            data = gql(CONTRIB_QUERY, {"login": USER_NAME, "from": start.isoformat(), "to": end.isoformat()})
            total += int(data["user"]["contributionsCollection"]["contributionCalendar"]["totalContributions"])
    return total


def _plural(count: int, unit: str) -> str:
    return f"{count} {unit}" + ("" if count == 1 else "s")


def age_string(birth: date, today: date) -> str:
    years = today.year - birth.year
    if (today.month, today.day) < (birth.month, birth.day):
        years -= 1
    return _plural(years, "year")


def collect() -> dict:
    user = gql(USER_QUERY, {"login": USER_NAME})["user"]
    owned = user["repositories"]["nodes"]
    return {
        "age_data": age_string(BIRTHDATE, datetime.now(timezone.utc).date()),
        "repo_data": int(user["repositories"]["totalCount"]),
        "contrib_data": int(user["contributed"]["totalCount"]),
        "commit_data": total_contributions(datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00"))),
        "follower_data": int(user["followers"]["totalCount"]),
        "star_data": sum(int(repo["stargazerCount"]) for repo in owned if not repo["isFork"]),
    }


def build_dots(total: int) -> str:
    if total <= 0:
        return ""
    if total == 1:
        return "\u00a0"
    return "\u00a0" + "." * (total - 2) + "\u00a0"


def update_svg(path: Path, stats: dict) -> None:
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    tree = ET.parse(path)
    root = tree.getroot()
    for key, value in stats.items():
        element = root.find(f".//*[@id='{key}']")
        if element is None:
            continue
        new_text = f"{value:,}" if isinstance(value, int) else str(value)
        dots = root.find(f".//*[@id='{key}_dots']")
        if dots is not None:
            width = len(dots.text or "") + len(element.text or "")
            dots.text = build_dots(width - len(new_text))
        element.text = new_text
    tree.write(path, encoding="utf-8", xml_declaration=True)


def main() -> None:
    if not TOKEN:
        raise SystemExit("Set ACCESS_TOKEN (or GITHUB_TOKEN) first.")
    stats = collect()
    for name, value in stats.items():
        shown = f"{value:,}" if isinstance(value, int) else value
        print(f"{name:<14} {shown}")
    for svg in ("dark_mode.svg", "light_mode.svg"):
        update_svg(ROOT / svg, stats)


if __name__ == "__main__":
    main()
