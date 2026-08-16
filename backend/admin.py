"""Vibetube admin CLI -- create and manage event showrooms.

Run from the backend directory:

    python admin.py create-event --name "Summit 2026" \
        --opens "2026-09-01 09:00" --closes "2026-09-01 18:00" --tz America/Los_Angeles
    python admin.py list-events
    python admin.py set-window --code SUMMIT --closes "2026-09-01 20:00" --tz America/Los_Angeles
    python admin.py purge-event --code SUMMIT

Times are entered in the event's local timezone and stored as UTC.
"""

import argparse
import secrets
import sys
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from database import (
    SANDBOX_EVENT_CODE, create_event, get_db_conn, get_event, init_db,
    normalize_row, query_placeholder, scalar, list_ads, set_ads_active,
)
from events import parse_iso, upload_state

# Ambiguous glyphs removed: codes get read aloud and typed off a slide.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

def generate_code(length: int = 6) -> str:
    """Builds a non-sequential event code.

    Codes are shareable by design, so sequential ones would let anyone walk
    from their own room into every other room.
    """
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))

def parse_local_time(value: str, tz_name: str) -> str:
    """Converts 'YYYY-MM-DD HH:MM' in the given timezone to a stored UTC string."""
    if not value:
        return None
    try:
        zone = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise SystemExit(f"Unknown timezone: {tz_name}")

    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            naive = datetime.strptime(value, fmt)
            break
        except ValueError:
            continue
    else:
        raise SystemExit(f"Could not parse time {value!r}. Use 'YYYY-MM-DD HH:MM'.")

    return naive.replace(tzinfo=zone).astimezone(ZoneInfo("UTC")).isoformat()

def describe_window(event: dict) -> str:
    state = upload_state(event)
    opens = parse_iso(event.get("uploadOpensAt"))
    closes = parse_iso(event.get("uploadClosesAt"))
    span = " -> ".join([
        opens.strftime("%Y-%m-%d %H:%M UTC") if opens else "always",
        closes.strftime("%Y-%m-%d %H:%M UTC") if closes else "always",
    ])
    return f"{state['uploadState']:<7} {span}"

def cmd_create_event(args):
    code = (args.code or generate_code()).strip()
    opens_at = parse_local_time(args.opens, args.tz)
    closes_at = parse_local_time(args.closes, args.tz)

    if opens_at and closes_at and closes_at <= opens_at:
        raise SystemExit("--closes must be after --opens.")

    with get_db_conn() as conn:
        cursor = conn.cursor()
        if get_event(cursor, code):
            raise SystemExit(f"Event {code!r} already exists.")
        seeded = create_event(
            cursor, code, args.name, opens_at, closes_at,
            with_seed=not args.no_seed,
        )
        conn.commit()

    print(f"Created event {code}")
    print(f"  name    : {args.name}")
    print(f"  opens   : {opens_at or 'always'}")
    print(f"  closes  : {closes_at or 'always'}")
    print(f"  seeded  : {seeded} videos")
    print(f"  url     : /e/{code}")

def cmd_list_events(args):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM events ORDER BY createdAt")
        events = [normalize_row(row) for row in cursor.fetchall()]

        print(f"{'CODE':<12} {'VIDEOS':<7} {'UPLOADS':<7} WINDOW")
        for event in events:
            cursor.execute(query_placeholder(
                "SELECT COUNT(*) FROM videos WHERE eventId = ?"
            ), (event["code"],))
            count = scalar(cursor.fetchone())
            print(f"{event['code']:<12} {count:<7} {describe_window(event)}  {event['name']}")

def cmd_list_ads(args):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        if not get_event(cursor, args.code):
            raise SystemExit(f"No event with code {args.code!r}.")
        ads = list_ads(cursor, args.code)

    if not ads:
        print(f"No ads in {args.code}.")
        return

    print(f"{'PROJECT':<20} {'STATE':<9} {'IMAGE':<6} MESSAGE")
    for ad in ads:
        state = "active" if ad.get("active") else "disabled"
        has_image = "yes" if ad.get("imageUrl") else "-"
        message = (ad.get("message") or "").replace("\n", " ")
        if len(message) > 60:
            message = message[:57] + "..."
        print(f"{ad['projectId']:<20} {state:<9} {has_image:<6} {message}")


def cmd_set_ads(args):
    """Closes ads for an event, or switches them all off outright."""
    closes_at = parse_local_time(args.closes, args.tz)

    with get_db_conn() as conn:
        cursor = conn.cursor()
        event = get_event(cursor, args.code)
        if not event:
            raise SystemExit(f"No event with code {args.code!r}.")

        if args.disable or args.enable:
            changed = set_ads_active(cursor, args.code, active=bool(args.enable))
            conn.commit()
            print(f"{'Enabled' if args.enable else 'Disabled'} {changed} ad(s) in {args.code}.")
            return

        new_closes = None if args.clear_closes else (closes_at or event.get("adsClosesAt"))
        cursor.execute(query_placeholder(
            "UPDATE events SET adsClosesAt = ? WHERE code = ?"
        ), (new_closes, args.code))
        conn.commit()

    if new_closes:
        print(f"Ad submissions for {args.code} close at {new_closes}. "
              "Existing ads keep playing.")
    else:
        print(f"Ad submissions for {args.code} are open indefinitely.")


def cmd_set_window(args):
    opens_at = parse_local_time(args.opens, args.tz)
    closes_at = parse_local_time(args.closes, args.tz)

    with get_db_conn() as conn:
        cursor = conn.cursor()
        event = get_event(cursor, args.code)
        if not event:
            raise SystemExit(f"No event with code {args.code!r}.")

        # Omitted bounds are left alone; --clear-opens/--clear-closes remove them.
        new_opens = None if args.clear_opens else (opens_at or event.get("uploadOpensAt"))
        new_closes = None if args.clear_closes else (closes_at or event.get("uploadClosesAt"))

        if new_opens and new_closes and new_closes <= new_opens:
            raise SystemExit("Close time must be after open time.")

        cursor.execute(query_placeholder(
            "UPDATE events SET uploadOpensAt = ?, uploadClosesAt = ? WHERE code = ?"
        ), (new_opens, new_closes, args.code))
        conn.commit()
        event = get_event(cursor, args.code)

    print(f"Updated {args.code}: {describe_window(event)}")

def cmd_purge_event(args):
    if args.code == SANDBOX_EVENT_CODE:
        raise SystemExit("Refusing to purge the sandbox event.")

    with get_db_conn() as conn:
        cursor = conn.cursor()
        event = get_event(cursor, args.code)
        if not event:
            raise SystemExit(f"No event with code {args.code!r}.")
        cursor.execute(query_placeholder(
            "SELECT COUNT(*) FROM videos WHERE eventId = ?"
        ), (args.code,))
        count = scalar(cursor.fetchone())

        if not args.yes:
            confirm = input(f"Delete event {args.code} and its {count} videos? [y/N] ")
            if confirm.strip().lower() not in ("y", "yes"):
                raise SystemExit("Aborted.")

        cursor.execute(query_placeholder("DELETE FROM ads WHERE eventId = ?"), (args.code,))
        cursor.execute(query_placeholder("DELETE FROM videos WHERE eventId = ?"), (args.code,))
        cursor.execute(query_placeholder("DELETE FROM events WHERE code = ?"), (args.code,))
        conn.commit()

    print(f"Deleted event {args.code} and {count} videos.")
    print(f"Note: transcoded media under gs://<public-bucket>/{args.code}/ is not removed.")
    print(f"Remove it with: gsutil -m rm -r gs://<public-bucket>/{args.code}/")

def main():
    parser = argparse.ArgumentParser(description="Vibetube event administration")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-event", help="Create a showroom and seed it")
    create.add_argument("--name", required=True, help="Human readable event name")
    create.add_argument("--code", help="Event code (generated if omitted)")
    create.add_argument("--opens", help="Upload window opens, 'YYYY-MM-DD HH:MM' local")
    create.add_argument("--closes", help="Upload window closes, 'YYYY-MM-DD HH:MM' local")
    create.add_argument("--tz", default="UTC", help="Timezone for --opens/--closes (default UTC)")
    create.add_argument("--no-seed", action="store_true", help="Create the event empty")
    create.set_defaults(func=cmd_create_event)

    listing = sub.add_parser("list-events", help="List every showroom")
    listing.set_defaults(func=cmd_list_events)

    window = sub.add_parser("set-window", help="Change an event's upload window")
    window.add_argument("--code", required=True)
    window.add_argument("--opens")
    window.add_argument("--closes")
    window.add_argument("--tz", default="UTC")
    window.add_argument("--clear-opens", action="store_true", help="Remove the open bound")
    window.add_argument("--clear-closes", action="store_true", help="Remove the close bound")
    window.set_defaults(func=cmd_set_window)

    ads_list = sub.add_parser("list-ads", help="List a showroom's pre-roll ads")
    ads_list.add_argument("--code", required=True)
    ads_list.set_defaults(func=cmd_list_ads)

    ads_set = sub.add_parser(
        "set-ads",
        help="Close ad submissions for a showroom, or switch ads off entirely",
    )
    ads_set.add_argument("--code", required=True)
    ads_set.add_argument("--closes",
                         help="Stop accepting new or replacement ads after this "
                              "local time. Existing ads keep playing.")
    ads_set.add_argument("--tz", default="UTC", help="Timezone for --closes")
    ads_set.add_argument("--clear-closes", action="store_true",
                         help="Remove the deadline; submissions stay open")
    ads_set.add_argument("--disable", action="store_true",
                         help="Stop every ad in the showroom from playing")
    ads_set.add_argument("--enable", action="store_true",
                         help="Reactivate every ad in the showroom")
    ads_set.set_defaults(func=cmd_set_ads)

    purge = sub.add_parser("purge-event", help="Delete an event, its videos and its ads")
    purge.add_argument("--code", required=True)
    purge.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    purge.set_defaults(func=cmd_purge_event)

    args = parser.parse_args()
    init_db()
    args.func(args)

if __name__ == "__main__":
    sys.exit(main())
