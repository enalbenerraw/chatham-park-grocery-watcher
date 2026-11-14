"""Offline tests: run with `python -m unittest test_watcher -v`.

These use canned responses, so they prove the logic (matching, dedupe,
digest, state) without touching the network or sending email.
"""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest import mock

import yaml

import watcher

NOW = datetime.now(timezone.utc)
RECENT = format_datetime(NOW - timedelta(days=3))
OLD = format_datetime(NOW - timedelta(days=900))
MEETING = (NOW + timedelta(days=5)).strftime("%m%d%Y")


def rss(items):
    body = "".join(
        f"<item><title>{t}</title><link>{link}</link><pubDate>{d}</pubDate>"
        f"<description>{desc}</description><source url='x'>{src}</source></item>"
        for t, link, d, desc, src in items
    )
    return f"<?xml version='1.0'?><rss version='2.0'><channel><title>t</title>{body}</channel></rss>"


def tiny_pdf(text):
    """Build a one-page PDF containing `text`."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, xref)
    return out


GOOGLE = rss([
    ("Chatham Park names YMCA center anchor: Publix coming to Pittsboro - Chapelboro",
     "https://news.google.com/rss/articles/ABC", RECENT,
     "Publix will anchor the mixed-use center near the Chatham Park YMCA.", "Chapelboro"),
    ("Lowes Foods at Northwood Landing celebrates anniversary in Pittsboro - Chatham News + Record",
     "https://news.google.com/rss/articles/LOW", RECENT,
     "The Lowes Foods grocery store at Northwood Landing marks a milestone.", "Chatham News + Record"),
    ("Lowes Foods opens in Pittsboro - WRAL", "https://news.google.com/rss/articles/OLD", OLD,
     "Grocery opens at Chatham Park.", "WRAL"),
])
# Served for a search with no grocery term, so the search cannot vouch for it.
OTHER = rss([
    ("Pittsboro town board talks water - WRAL", "https://news.google.com/rss/articles/W", RECENT,
     "Water and sewer in Pittsboro.", "WRAL"),
])
LOCAL = rss([
    ("Chatham Park names YMCA center anchor: Publix coming to Pittsboro",
     "https://chapelboro.com/news/publix-coming?utm=x", RECENT,
     "Publix will anchor the mixed-use center near the Chatham Park YMCA.", "Chapelboro"),
])
# Mirrors the live CivicPlus markup: board h2, then rows with a date h3 and
# the meeting name as <p><a>.
AGENDA_HTML = f"""
<html><body><h2>6.  Planning Board (PB)</h2><table><tr class="catAgendaRow"><td>
<h3><strong>Oct 27, 2026</strong> \u2014 Posted Oct 20, 2026 9:00 AM</h3>
<p><a href="/AgendaCenter/ViewFile/Agenda/_{MEETING}-501?html=true">Planning Board Regular Meeting-6 p.m.</a></p>
</td><td><a href="/AgendaCenter/ViewFile/Agenda/_{MEETING}-501?packet=true">Packet</a></td></tr></table>
<h2>4.  Parks and Recreation Advisory Board (PARAB)</h2><table><tr class="catAgendaRow"><td>
<h3><strong>Oct 27, 2026</strong></h3>
<p><a href="/AgendaCenter/ViewFile/Agenda/_{MEETING}-502?html=true">Parks Advisory Board-6 p.m.</a></p>
</td></tr></table>
</body></html>"""
PACKET = tiny_pdf("Site plan SP-2026-14 Chatham Park South Village retail. Tenant: Harris Teeter supermarket.")


class FakeResponse:
    def __init__(self, content=b"", status=200, ctype="text/xml"):
        self.content = content if isinstance(content, bytes) else content.encode()
        self.text = self.content.decode("latin-1")
        self.status_code = status
        self.headers = {"Content-Type": ctype, "Content-Length": str(len(self.content))}
        self.encoding = "utf-8"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise watcher.requests.HTTPError(f"{self.status_code}")

    def iter_content(self, n):
        yield self.content

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, **kw):
        self.calls.append(url)
        if "news.google.com" in url:
            if "Publix" in url:
                return FakeResponse(GOOGLE)
            return FakeResponse(OTHER if "site%3Achapelboro" in url else rss([]))
        if "chapelboro.com/feed" in url:
            return FakeResponse(LOCAL)
        if "chathamnewsrecord" in url or "chathamjournal" in url:
            return FakeResponse("blocked", status=403)
        if "RSSFeed.aspx" in url:
            return FakeResponse("not found", status=404)
        if url.endswith("/AgendaCenter") or "/AgendaCenter/Search" in url:
            return FakeResponse(AGENDA_HTML, ctype="text/html")
        if "ViewFile" in url:
            return FakeResponse(PACKET, ctype="application/pdf")
        return FakeResponse("", status=404)


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.cfg = yaml.safe_load((watcher.HERE / "config.yaml").read_text())
        self.m = watcher.Matcher(self.cfg)

    def item(self, title, text=""):
        return watcher.Item(title, "https://x", "test", None, text)

    def test_requires_location_and_grocery(self):
        self.assertIsNotNone(self.m.match(self.item("Publix coming to Pittsboro")))
        self.assertIsNone(self.m.match(self.item("Publix opens in Cary")))
        self.assertIsNone(self.m.match(self.item("Chatham Park adds a park")))

    def test_spelling_variants(self):
        for title in ["Trader Joes eyes Chatham Park", "Trader Joe’s eyes Chatham Park",
                      "Lowe's Foods in Pittsboro", "New supermarkets for Pittsboro"]:
            self.assertIsNotNone(self.m.match(self.item(title)), title)
        self.assertIsNone(self.m.match(self.item("Pittsboro Waldi festival")))

    def test_lowes_alone_is_low_priority(self):
        low = self.m.match(self.item("Lowes Foods at Northwood Landing hosts event in Pittsboro"))
        self.assertTrue(low.low_priority)
        both = self.m.match(self.item("Chatham Park's next grocery store will join Lowes Foods in Pittsboro"))
        self.assertFalse(both.low_priority)
        chain = self.m.match(self.item("Wegmans and Lowes Foods compete in Pittsboro"))
        self.assertFalse(chain.low_priority)

    def test_chain_names_are_proper_nouns(self):
        self.assertIsNone(self.m.match(self.item("Chatham Park meadow", "young sprouts could be nurtured")))
        self.assertIsNotNone(self.m.match(self.item("Sprouts eyes Chatham Park")))
        self.assertIsNotNone(self.m.match(self.item("ALDI eyes Chatham Park")))

    def test_search_vouches_for_grocery_not_location(self):
        def found(title, search):
            return watcher.Item(title, "https://x", "test", None, "", search=search)
        hit = self.m.match(found("Chatham Park maps next growth wave", '"Chatham Park" grocery'))
        self.assertIsNotNone(hit)
        self.assertIn("Google News found this", hit.snippets[0])
        self.assertIsNone(self.m.match(found("Chatham Park maps next growth wave", '"Chatham Park" YMCA retail')))
        self.assertIsNone(self.m.match(found("Cleveland seeks next store", '"Chatham Park" grocery')))

    def test_highlight(self):
        out = self.m.highlight_html("A <Publix> in Pittsboro")
        self.assertIn("&lt;", out)
        self.assertIn("<mark><b>Publix</b></mark>", out)


class ConfigTests(unittest.TestCase):
    """Place names come from config.yaml, never from the code."""

    def test_chain_queries_use_configured_place(self):
        cfg = {"google_news": {"queries": ["q"], "chain_query_place": "Main Street"},
               "grocery_chains": ["Publix", "Aldi"]}
        self.assertEqual(watcher.google_news_queries(cfg), ["q", '"Main Street" Publix', '"Main Street" Aldi'])

    def test_blank_place_skips_chain_queries(self):
        cfg = {"google_news": {"queries": ["q"], "chain_query_place": ""}, "grocery_chains": ["Publix"]}
        self.assertEqual(watcher.google_news_queries(cfg), ["q"])

    def test_missing_agenda_url_is_a_named_failure(self):
        statuses = []
        items = watcher.fetch_agendas(FakeSession(), {"town_agendas": {"name": "Town of Apex"}}, {}, statuses)
        self.assertEqual(items, [])
        self.assertEqual(statuses[0].name, "Town of Apex agendas")
        self.assertFalse(statuses[0].ok)
        self.assertIn("base_url", statuses[0].detail)


class EndToEndTests(unittest.TestCase):
    def run_watcher(self, state, *extra):
        sent = []
        with mock.patch.object(watcher, "make_session", FakeSession), \
             mock.patch.object(watcher, "send_email", lambda cfg, s, h, t: sent.append((s, h, t))), \
             mock.patch.object(watcher.time, "sleep", lambda s: None):
            code = watcher.main(["--state", str(state), *extra])
        return code, sent

    def test_first_run_sends_second_run_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d) / "seen.json"
            code, sent = self.run_watcher(state)
            self.assertEqual(code, 0)
            self.assertEqual(len(sent), 1)
            subject, html_body, text_body = sent[0]
            # Publix story (Google + local copy deduped to one), agenda packet, Lowes as low priority.
            self.assertIn("3 new mentions", subject)
            self.assertIn("Harris Teeter", text_body)
            self.assertIn("Planning Board (PB): Planning Board Regular Meeting-6 p.m.", text_body)
            self.assertNotIn("Posted", text_body)
            self.assertNotIn("Parks Advisory", text_body)
            self.assertNotIn("Lowes Foods opens in Pittsboro", text_body)  # too old
            self.assertNotIn("water", text_body.lower())
            self.assertEqual(text_body.count("Publix coming to Pittsboro\n"), 1)
            self.assertIn("Lower priority", text_body)
            self.assertIn("FAILED Chatham News + Record", text_body)
            self.assertTrue(text_body.startswith("Chatham Park grocery watch\n"))  # heading from subject_prefix
            self.assertIn("Town of Pittsboro Agenda Center", text_body)  # label from town_agendas.name

            code, sent = self.run_watcher(state)
            self.assertEqual(code, 0)
            self.assertEqual(sent, [] if datetime.now(watcher.EASTERN).strftime("%A") != "Monday"
                             else sent)
            if sent:  # Monday: only the heartbeat may go out
                self.assertIn("no new mentions", sent[0][0])

    def test_dry_run_sends_and_saves_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d) / "seen.json"
            code, sent = self.run_watcher(state, "--dry-run")
            self.assertEqual(code, 0)
            self.assertEqual(sent, [])
            self.assertFalse(state.exists())


if __name__ == "__main__":
    unittest.main()
