import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup
import requests
import re
from datetime import datetime

st.set_page_config(page_title="Flashscore Odds Movers", page_icon="📈", layout="wide")
st.title("Flashscore Odds Movers (≥ 10%)")
st.caption("Games where the odds have moved at least 10% since the opening line")

SPORTS = {
    "Football": "https://www.flashscore.com/football/",
    "Tennis": "https://www.flashscore.com/tennis/",
    "Darts": "https://www.flashscore.com/darts/",
    "NBA": "https://www.flashscore.com/basketball/usa/nba/",
    "NFL": "https://www.flashscore.com/american-football/usa/nfl/",
    "MLB": "https://www.flashscore.com/baseball/usa/mlb/",
    "NHL": "https://www.flashscore.com/hockey/usa/nhl/",
}

THRESHOLD = 10.0  # percent

def scrape_spider(url: str) -> str:
    """Keyless Spider scrape."""
    api = "https://api.spider.cloud/scrape"
    payload = {
        "url": url,
        "return_format": "html",
        "request": "browser",
        "proxy_enabled": True,
    }
    try:
        r = requests.post(api, json=payload, timeout=90)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list) and data:
            return data[0].get("content", "")
        return ""
    except Exception as e:
        st.warning(f"Spider error for {url}: {e}")
        return ""


def percent_move(opening: float, current: float) -> float:
    if not opening or opening == 0:
        return 0.0
    return abs((current - opening) / opening) * 100


def parse_match_odds(html: str, sport: str, match_url: str):
    """Very basic parser – looks for decimal odds pairs that could be opening/current.
    Flashscore structure varies; this is a starting point you will need to refine.
    """
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    results = []

    # Look for common odds-related text or numbers
    # This is intentionally simple – real Flashscore match pages need more specific selectors
    text = soup.get_text(" ", strip=True)
    numbers = re.findall(r"\b(\d+\.\d{2})\b", text)

    # Heuristic: if we find at least 4 decimal odds, treat first half as opening, second as current
    if len(numbers) >= 4:
        mid = len(numbers) // 2
        openings = [float(n) for n in numbers[:mid]]
        currents = [float(n) for n in numbers[mid:mid + len(openings)]]
        for o, c in zip(openings, currents):
            move = percent_move(o, c)
            if move >= THRESHOLD:
                results.append({
                    "Sport": sport,
                    "Match": match_url.split("/")[-2] if match_url else "Unknown",
                    "Opening": o,
                    "Current": c,
                    "Move %": round(move, 1),
                    "URL": match_url,
                })
    return results


def get_match_links(html: str) -> list:
    """Extract possible match links from a fixtures page."""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/match/" in href and href.startswith("/"):
            full = "https://www.flashscore.com" + href
            if full not in links:
                links.append(full)
    return links[:8]  # Limit to avoid free-tier rate limits


# ---------- UI ----------
selected_sports = st.multiselect(
    "Select sports",
    list(SPORTS.keys()),
    default=["Football", "Tennis"]
)

if st.button("Scan for movers", type="primary"):
    all_movers = []
    progress = st.progress(0)
    status = st.empty()

    for idx, sport in enumerate(selected_sports):
        status.text(f"Scanning {sport}...")
        fixtures_html = scrape_spider(SPORTS[sport])
        match_links = get_match_links(fixtures_html)

        for m_url in match_links:
            match_html = scrape_spider(m_url)
            movers = parse_match_odds(match_html, sport, m_url)
            all_movers.extend(movers)

        progress.progress((idx + 1) / len(selected_sports))

    status.empty()
    progress.empty()

    if all_movers:
        df = pd.DataFrame(all_movers)
        df = df.sort_values("Move %", ascending=False)
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "URL": st.column_config.LinkColumn("Match"),
                "Move %": st.column_config.NumberColumn(format="%.1f%%"),
            }
        )
        csv = df.to_csv(index=False).encode()
        st.download_button("Download CSV", csv, "odds_movers.csv", "text/csv")
    else:
        st.info("No games found with ≥ 10% movement (or free-tier limit reached).")

st.caption("Note: Free Spider tier is rate-limited. Opening/current odds parsing is heuristic and may need refinement for production use.")
