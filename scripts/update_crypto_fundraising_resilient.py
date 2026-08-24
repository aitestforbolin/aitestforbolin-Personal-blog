#!/usr/bin/env python3
"""Refresh crypto fundraising with an official /deal-flow/ fallback."""

from __future__ import annotations

import time
from urllib.error import URLError
from urllib.request import Request, urlopen

import update_crypto_fundraising as base


DEAL_FLOW_URL = "https://crypto-fundraising.info/deal-flow/"


def fetch_text(url: str) -> str:
    request = Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": (
                "personal-site-crypto-fundraising/1.1 "
                "(+https://github.com/aitestforbolin/aitestforbolin-Personal-blog)"
            ),
        },
    )
    last_error: Exception | None = None
    for attempt in range(1, base.FETCH_RETRIES + 1):
        try:
            with urlopen(request, timeout=base.FETCH_TIMEOUT) as response:
                body = response.read()
                encoding = response.headers.get_content_charset() or "utf-8"
            return body.decode(encoding, errors="replace")
        except (TimeoutError, URLError) as error:
            last_error = error
            if attempt < base.FETCH_RETRIES:
                time.sleep(attempt * 2)
    raise RuntimeError(f"Could not fetch {url}") from last_error


def build_from_deal_flow(previous: dict[str, object] | None) -> dict[str, object]:
    html = fetch_text(DEAL_FLOW_URL)
    # The existing parser deliberately reads rows only inside the homepage's
    # recently-launched section.  The official deal-flow page uses the same row
    # markup but not that wrapper, so provide the wrapper locally rather than
    # weakening the validated parser for every page.
    wrapped = f'<section class="recently-launched dealflow">\n{html}\n</section>'
    return base.build_payload(wrapped, previous_payload=previous)


def main() -> None:
    previous = base.load_previous_payload()
    try:
        payload = base.build_payload(previous_payload=previous)
        source = "homepage"
    except Exception as primary_error:  # noqa: BLE001 - fallback covers fetch and structure changes.
        print(f"Primary Crypto-Fundraising homepage failed: {primary_error}")
        payload = build_from_deal_flow(previous)
        source = "deal-flow fallback"

    if not base.project_data_changed(payload, previous):
        print(f"Latest Crypto-Fundraising projects are unchanged ({source}).")
        return

    base.write_payload(payload)
    print(f"Updated {base.OUTPUT} with {len(payload['projects'])} projects via {source}.")


if __name__ == "__main__":
    main()
