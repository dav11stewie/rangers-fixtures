#!/usr/bin/env python3
"""
Fetch Glasgow Rangers FC fixtures for a calendar year from BBC Sport, merge in
UK TV channel info from live-footballontv.com, and write data/fixtures.json.

Data sources (both scraped, not official APIs -- see README for risk notes):
  - BBC Sport's fixtures JSON endpoint: complete season, every competition,
    but no broadcast info.
  - live-footballontv.com/rangers-on-tv.html: UK TV channels, but only for
    the handful of currently-known upcoming televised games.

Standard library only. No pip installs required.

Usage:
    python3 scripts/update_fixtures.py [--year YYYY] [--dry-run] [--verbose] [--force]
"""
import argparse
import calendar
import html
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_URL = "https://github.com/dav11stewie/rangers-fixtures"
USER_AGENT_API = f"rangers-fixtures/1.0 (+{REPO_URL})"
USER_AGENT_HTML = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)

BBC_TEAM_URN = "urn:bbc:sportsdata:football:team:rangers"
BBC_API = "https://web-cdn.api.bbci.co.uk/wc-poll-data/container/sport-data-scores-fixtures"
TV_URL = "https://www.live-footballontv.com/rangers-on-tv.html"

UK_TZ = ZoneInfo("Europe/London")

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "fixtures.json"

# --- name normalisation -----------------------------------------------------

# Characters unicodedata's NFKD decomposition does NOT split into base+mark
# (verified: "Białystok" survives NFKD + combining-mark-strip untouched).
# Must be applied BEFORE NFKD.
_CHAR_TRANSLATE = str.maketrans({
    "ł": "l", "Ł": "l",
    "ø": "o", "Ø": "o",
    "đ": "d", "Đ": "d",
    "ß": "ss",
    "æ": "ae", "Æ": "ae",
    "œ": "oe", "Œ": "oe",
    "þ": "th", "Þ": "th",
    "ð": "d", "Ð": "d",
    "ı": "i", "İ": "i",
})

_NOISE_WORDS = re.compile(r"\b(fc|afc|cf|sc|the)\b")
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
_SAINT = re.compile(r"\bsaint\b")
_WHITESPACE = re.compile(r"\s+")

# Hand-maintained aliases for names that are genuinely different strings
# between BBC and the TV listings site, not just spelling/punctuation
# variants (those are handled by normalisation above).
ALIAS = {
    "heart of midlothian": "hearts",
    "dundee united": "dundee utd",
    "queen s park": "queens park",
    "ludogorets razgrad": "ludogorets",
    "annan athletic": "annan",
    "inverness caledonian thistle": "inverness ct",
    "west ham united": "west ham",
    "saint etienne": "st etienne",
}


def norm(name):
    """Normalise a team name so BBC and TV-site spellings converge."""
    s = name.translate(_CHAR_TRANSLATE)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("&", " and ")
    s = _NON_ALNUM.sub(" ", s)
    s = _SAINT.sub("st", s)
    s = _NOISE_WORDS.sub(" ", s)
    s = _WHITESPACE.sub(" ", s).strip()
    return ALIAS.get(s, s)


# --- HTTP helpers ------------------------------------------------------------

def fetch(url, user_agent, timeout=30, retries=1):
    """GET a URL with a UA header, one retry on 5xx/timeout, raise otherwise."""
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": user_agent})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last_err = e
            if attempt < retries:
                time.sleep(5)
    raise last_err


# --- Stage 1: BBC fixtures ----------------------------------------------------

def walk_events(obj):
    """Recursively find match-record dicts anywhere in the decoded JSON tree."""
    if isinstance(obj, dict):
        if "startDateTime" in obj and "home" in obj and "away" in obj:
            yield obj
        for v in obj.values():
            yield from walk_events(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_events(v)


def fetch_bbc_month(year, month, verbose=False):
    last_day = calendar.monthrange(year, month)[1]
    start = f"{year}-{month:02d}-01"
    end = f"{year}-{month:02d}-{last_day:02d}"
    today = date.today().isoformat()
    url = (
        f"{BBC_API}?selectedStartDate={start}&selectedEndDate={end}"
        f"&todayDate={today}&urn={urllib.parse.quote(BBC_TEAM_URN)}"
    )
    if verbose:
        print(f"  fetching {start}..{end}", file=sys.stderr)
    raw = fetch(url, USER_AGENT_API)
    data = json.loads(raw)
    return list(walk_events(data))


def parse_bbc_datetime(s):
    """Return (aware_datetime_or_None, time_tbc: bool)."""
    if "T" in s:
        # e.g. "2026-08-13T18:30:00Z"
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt, False
    # date-only, e.g. "2026-07-16" -- postponed/cancelled fixtures sometimes
    # drop the kickoff time entirely.
    dt = datetime.fromisoformat(s).replace(tzinfo=UK_TZ)
    return dt, True


def split_competition(label):
    """'Scotland - League Cup - 2nd Round' -> ('League Cup', '2nd Round')."""
    if not label:
        return "Unknown", ""
    parts = [p.strip() for p in label.split(" - ")]
    # First element is a region ("Scotland"/"Europe"/"World") -- drop it if
    # there's more than one part.
    if len(parts) > 1:
        parts = parts[1:]
    competition = parts[0]
    stage = " - ".join(parts[1:])
    return competition, stage


def is_rangers_first_team(name):
    n = norm(name)
    return n == "rangers"


def fetch_all_bbc_fixtures(year, verbose=False):
    events_by_id = {}
    warnings = []
    for month in range(1, 13):
        try:
            events = fetch_bbc_month(year, month, verbose=verbose)
        except Exception as e:
            msg = f"BBC fetch failed for {year}-{month:02d}: {e}"
            print(f"WARNING: {msg}", file=sys.stderr)
            warnings.append(msg)
            time.sleep(1.0)
            continue
        for e in events:
            eid = e.get("id")
            if eid:
                events_by_id[eid] = e
        time.sleep(1.0)

    fixtures = []
    for e in events_by_id.values():
        home = e.get("home", {})
        away = e.get("away", {})
        home_name = home.get("fullName", "")
        away_name = away.get("fullName", "")

        # Only first-team Rangers fixtures -- filters out any Rangers B /
        # youth fixtures that might surface via this feed.
        if not (is_rangers_first_team(home_name) or is_rangers_first_team(away_name)):
            continue

        is_home = is_rangers_first_team(home_name)
        opponent = away_name if is_home else home_name

        start_raw = e.get("startDateTime", "")
        try:
            dt, time_tbc = parse_bbc_datetime(start_raw)
        except Exception:
            if verbose:
                print(f"  skipping event with unparseable date: {start_raw!r}", file=sys.stderr)
            continue

        competition, stage = split_competition(e.get("eventGroupingLabel", ""))

        score = None
        if home.get("score") is not None and away.get("score") is not None:
            score = f"{home.get('score')}-{away.get('score')}"

        fixtures.append({
            "id": e.get("id"),
            "kickoff_utc": dt.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z"),
            "time_tbc": time_tbc,
            "home": home_name,
            "away": away_name,
            "is_home": is_home,
            "opponent": opponent,
            "competition": competition,
            "stage": stage,
            "status": e.get("status", ""),
            "score": score,
            "channels": [],
        })

    fixtures.sort(key=lambda f: f["kickoff_utc"])
    return fixtures, warnings


# --- Stage 2: TV channels -----------------------------------------------------

_DATE_HEADER_RE = re.compile(
    r'class="fixture-date">([^<]+)</div>'
)
_FIXTURE_BLOCK_RE = re.compile(
    r'fixture__time">([^<]*)<.*?fixture__teams">([^<]*)<'
    r'.*?fixture__competition">(.*?)</div>(.*?)(?=<div class="fixture"|\Z)',
    re.S,
)
_CHANNEL_RE = re.compile(r'channel-pill[^>]*>([^<]+)<')
_ORDINAL_RE = re.compile(r"(\d+)(st|nd|rd|th)")


def fetch_tv_fixtures(verbose=False):
    """Returns list of dicts: {date, opponent, is_home, channels: [...]}."""
    raw = fetch(TV_URL, USER_AGENT_HTML)

    # Split the doc into (date_heading, following_html) segments so we know
    # which date each fixture block belongs to.
    segments = []
    headers = list(_DATE_HEADER_RE.finditer(raw))
    for i, m in enumerate(headers):
        seg_start = m.end()
        seg_end = headers[i + 1].start() if i + 1 < len(headers) else len(raw)
        segments.append((m.group(1), raw[seg_start:seg_end]))

    results = []
    for date_text, segment in segments:
        date_clean = _ORDINAL_RE.sub(r"\1", html.unescape(date_text)).strip()
        try:
            d = datetime.strptime(date_clean, "%A %d %B %Y").date()
        except ValueError:
            if verbose:
                print(f"  TV: unparseable date heading: {date_text!r}", file=sys.stderr)
            continue

        for m in _FIXTURE_BLOCK_RE.finditer(segment):
            _time_text, teams_text, competition_text, rest = m.groups()
            teams_text = html.unescape(teams_text).replace("\xa0", " ").strip()
            competition_text = html.unescape(competition_text).replace("\xa0", " ").strip()

            if " v " not in teams_text:
                continue
            home_name, away_name = [t.strip() for t in teams_text.split(" v ", 1)]

            # Drop non-first-team rows (e.g. "Queen of the South v Rangers B").
            if not (is_rangers_first_team(home_name) or is_rangers_first_team(away_name)):
                continue

            is_home = is_rangers_first_team(home_name)
            opponent = away_name if is_home else home_name

            channels = [html.unescape(c).strip() for c in _CHANNEL_RE.findall(rest)]

            results.append({
                "date": d,
                "opponent": opponent,
                "opponent_norm": norm(opponent),
                "is_home": is_home,
                "competition": competition_text,
                "channels": channels,
            })

    return results


# --- Stage 3: merge ------------------------------------------------------------

def merge_channels(bbc_fixtures, tv_fixtures, verbose=False):
    tv_index = {}
    for tv in tv_fixtures:
        tv_index[(tv["date"], tv["opponent_norm"])] = tv

    matched_tv_keys = set()
    for fx in bbc_fixtures:
        kickoff = datetime.fromisoformat(fx["kickoff_utc"].replace("Z", "+00:00"))
        uk_date = kickoff.astimezone(UK_TZ).date()
        opp_norm = norm(fx["opponent"])

        tv = None
        for delta in (0, 1, -1):
            key = (uk_date + timedelta(days=delta), opp_norm)
            if key in tv_index:
                tv = tv_index[key]
                matched_tv_keys.add(key)
                break

        if tv:
            fx["channels"] = tv["channels"]

    if verbose:
        for key, tv in tv_index.items():
            if key not in matched_tv_keys:
                print(
                    f"  TV row not matched to any BBC fixture: "
                    f"{key[0]} vs {tv['opponent']!r} (norm={key[1]!r}) -- "
                    f"check ALIAS map or opponent name drift",
                    file=sys.stderr,
                )

    return bbc_fixtures


# --- Stage 4: write safely ------------------------------------------------------

def load_existing():
    if DATA_PATH.exists():
        try:
            return json.loads(DATA_PATH.read_text())
        except Exception:
            return None
    return None


def carry_forward_channels(new_fixtures, old_data):
    if not old_data:
        return
    old_by_id = {f["id"]: f for f in old_data.get("fixtures", [])}
    for fx in new_fixtures:
        old = old_by_id.get(fx["id"])
        if old and not fx["channels"] and old.get("channels"):
            fx["channels"] = old["channels"]


def fixtures_equal(a, b):
    def strip(fixtures):
        return [{k: v for k, v in f.items()} for f in fixtures]
    return json.dumps(strip(a), sort_keys=True) == json.dumps(strip(b), sort_keys=True)


def write_output(year, fixtures, warnings, tv_source_ok, dry_run=False, force=False):
    old_data = load_existing()

    if len(fixtures) == 0:
        print("ERROR: zero fixtures parsed -- refusing to write empty data.", file=sys.stderr)
        sys.exit(1)

    if old_data and not force:
        old_count = len(old_data.get("fixtures", []))
        if old_count > 0 and len(fixtures) < 0.5 * old_count:
            print(
                f"ERROR: new fixture count ({len(fixtures)}) is less than half of "
                f"existing ({old_count}). Looks like a partial scrape failure. "
                f"Re-run with --force to override.",
                file=sys.stderr,
            )
            sys.exit(1)

    if not tv_source_ok:
        carry_forward_channels(fixtures, old_data)

    output = {
        "generated_at": datetime.now(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z"),
        "year": year,
        "source_warnings": warnings,
        "tv_source_ok": tv_source_ok,
        "fixtures": fixtures,
    }

    if old_data and fixtures_equal(fixtures, old_data.get("fixtures", [])):
        print("No change in fixtures data; leaving file untouched.")
        if dry_run:
            print(json.dumps(output, indent=2, ensure_ascii=False, sort_keys=True))
        return

    text = json.dumps(output, indent=2, ensure_ascii=False, sort_keys=True) + "\n"

    if dry_run:
        print(text)
        print(f"[dry-run] would write {len(fixtures)} fixtures to {DATA_PATH}", file=sys.stderr)
        return

    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(text)
    print(f"Wrote {len(fixtures)} fixtures to {DATA_PATH}")


# --- main -----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=date.today().year)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    print(f"Fetching BBC fixtures for {args.year}...", file=sys.stderr)
    bbc_fixtures, warnings = fetch_all_bbc_fixtures(args.year, verbose=args.verbose)
    print(f"  {len(bbc_fixtures)} first-team fixtures found.", file=sys.stderr)

    print("Fetching TV channel listings...", file=sys.stderr)
    tv_source_ok = True
    tv_fixtures = []
    try:
        tv_fixtures = fetch_tv_fixtures(verbose=args.verbose)
        print(f"  {len(tv_fixtures)} televised fixtures found.", file=sys.stderr)
    except Exception as e:
        print(f"WARNING: TV listings fetch failed: {e}", file=sys.stderr)
        tv_source_ok = False
        warnings.append(f"TV listings fetch failed: {e}")

    merge_channels(bbc_fixtures, tv_fixtures, verbose=args.verbose)

    matched = sum(1 for f in bbc_fixtures if f["channels"])
    print(f"  {matched} fixtures matched to a TV channel.", file=sys.stderr)

    write_output(
        args.year, bbc_fixtures, warnings, tv_source_ok,
        dry_run=args.dry_run, force=args.force,
    )


if __name__ == "__main__":
    main()
