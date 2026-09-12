"""Stand-ins for the two online dictionaries, so a build can be tested without one.

It answers both calls a build makes -- a word asked of the free online
dictionary, and a word asked of Wiktionary -- and keeps every request it was
sent, which is what the tests assert on: that a word the offline dictionary
knows was never asked about at all, that the second service is asked when the
first has nothing, and that a service which failed is not asked once per word
for the rest of a run.

What it answers with is what a test lays out: a transcription per word for the
dictionary, and a page of wikitext per word for Wiktionary, since that is where
that service's pronunciation is written. A word the test did not lay out is one
the service answers that it has nothing for -- which is not the same thing as a
service that will not answer at all, and is what `fail` is for.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping
from urllib.parse import parse_qs, unquote

# Where the stub listens: the loopback address, as the services are reached.
LOOPBACK = "127.0.0.1"

# The two services under the one address: the free dictionary takes the word as
# the last part of its path, and Wiktionary takes its own query.
DICTIONARY = "/dictionary"
WIKTIONARY = "/wiktionary"


class StubDictionary:
    """Two dictionaries answering whatever a test says they answer."""

    def __init__(
        self,
        dictionary: Mapping[str, str] | None = None,
        wiktionary: Mapping[str, str] | None = None,
    ) -> None:
        # Each word against the transcription the free dictionary has for it,
        # and against the page wikitext Wiktionary has for it.
        self.dictionary = dict(dictionary or {})
        self.wiktionary = dict(wiktionary or {})
        # Every request, as (service, word, what the caller called itself).
        self.requests: list[tuple[str, str, str]] = []
        # The status to answer everything with, when a test wants a service that
        # is there but will not answer.
        self.failure: int | None = None
        self._server = ThreadingHTTPServer((LOOPBACK, 0), _handler(self))
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        return f"http://{LOOPBACK}:{self._server.server_port}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def fail(self, status: int = 500) -> None:
        """Make every request answer with a status rather than a word."""
        self.failure = status

    def asked(self, service: str | None = None) -> list[str]:
        """The words one service was asked about, in the order it was asked."""
        return [word for asked, word, _ in self.requests if service in (None, asked)]

    def caller(self, service: str) -> list[str]:
        """What the tool called itself when it asked one service."""
        return [agent for asked, _, agent in self.requests if asked == service]

    def answer(self, service: str, word: str) -> tuple[int, dict[str, Any]]:
        """One service's answer about one word, as the service would write it."""
        if self.failure is not None:
            return self.failure, {}
        if service == DICTIONARY:
            text = self.dictionary.get(word)
            if text is None:
                return 404, {"title": "No Definitions Found"}
            return 200, self._entry(word, text)
        page = self.wiktionary.get(word)
        if page is None:
            # What MediaWiki answers about a page that is not there: not a
            # refusal, an answer that the page does not exist.
            return 200, {"error": {"code": "missingtitle", "info": "The page you specified doesn't exist."}}
        return 200, {"parse": {"title": word, "wikitext": page}}

    def _entry(self, word: str, text: str) -> list[dict[str, Any]]:
        """One word's entry, laid out the way the dictionary lays its answer out.

        A pronunciation comes twice in it, once as the word's own and once among
        the recordings, and the recording without a transcription beside it is
        what the real service sends for a word whose audio it has and whose
        symbols it does not.
        """
        return [
            {
                "word": word,
                "phonetic": text,
                "phonetics": [{"audio": f"https://example.invalid/{word}.mp3"}, {"text": text}],
                "meanings": [],
            }
        ]


def _handler(stub: StubDictionary) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 -- the name http.server calls
            asked, _, query = self.path.partition("?")
            service = WIKTIONARY if asked == WIKTIONARY else DICTIONARY
            word = (
                parse_qs(query).get("page", [""])[0]
                if service == WIKTIONARY
                else unquote(asked.removeprefix(DICTIONARY + "/"))
            )
            stub.requests.append((service, word, self.headers.get("User-Agent", "")))
            status, reply = stub.answer(service, word)
            encoded = json.dumps(reply).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: Any) -> None:
            """Keep the test output to the assertions."""

    return Handler
