"""
Layer 14 -- Sustainability & ESG Signal Extraction

Scans existing data layers (news, filings, GDELT, Reddit) for ESG signals.
No new APIs -- extracts sustainability context from data already fetched.
Surfaces climate risk, governance red flags, and social controversies
so the LLM can factor ESG into thesis evaluation.
"""


# -- ESG keyword sets ----------------------------------------------------------

ENVIRONMENTAL_KEYWORDS = {
    "climate", "carbon", "emission", "greenhouse", "renewable", "solar",
    "wind energy", "clean energy", "net zero", "sustainability", "esg",
    "pollution", "waste", "recycling", "water usage", "deforestation",
    "environmental", "green bond", "carbon neutral", "scope 1", "scope 2",
    "scope 3", "paris agreement", "climate risk", "wildfire", "drought",
    "flood", "hurricane", "extreme weather", "fossil fuel",
}

SOCIAL_KEYWORDS = {
    "diversity", "inclusion", "labor", "workplace safety", "human rights",
    "supply chain ethics", "child labor", "whistleblower", "discrimination",
    "harassment", "data privacy", "data breach", "consumer protection",
    "community", "employee satisfaction", "layoffs", "union",
    "health and safety", "wage", "working conditions",
}

GOVERNANCE_KEYWORDS = {
    "board independence", "executive compensation", "ceo pay", "audit",
    "accounting fraud", "sec investigation", "insider trading",
    "shareholder rights", "proxy fight", "activist investor",
    "corporate governance", "transparency", "conflict of interest",
    "bribery", "corruption", "lobbying", "political donation",
    "class action", "securities fraud", "restatement", "delisting",
    "auditor change", "material weakness",
}

# Negative ESG signals (controversies, risks)
ESG_RED_FLAGS = {
    "oil spill", "toxic", "carcinogen", "osha violation", "epa fine",
    "sec fine", "ftc fine", "antitrust", "monopoly", "price fixing",
    "forced labor", "sweatshop", "environmental disaster",
    "greenwashing", "accounting irregularity", "ponzi",
}


def _scan_text(text, keyword_set):
    """
    Count keyword matches in text.

    Args:
        text:        Input text to scan.
        keyword_set: Set of keyword strings to look for.

    Returns:
        List of matched keyword strings.
    """
    text_lower = text.lower()
    return [kw for kw in keyword_set if kw in text_lower]


def _score_category(matches):
    """
    Simple signal strength classification.

    Returns:
        One of 'none', 'low', 'moderate', or 'high'.
    """
    count = len(matches)
    if count == 0:
        return "none"
    elif count <= 2:
        return "low"
    elif count <= 5:
        return "moderate"
    return "high"


def extract_sustainability_signals(data, portfolio):
    """
    Scan already-fetched data from other layers for ESG signals.

    Args:
        data:      Dict of all layer results (from the main analyzer).
        portfolio: Parsed portfolio config (stocks.yaml).

    Returns:
        Dict with per-ticker ESG signals and a portfolio-level summary.
        Each ticker entry contains:
        - environmental: Signal strength and matched keywords.
        - social:        Signal strength and matched keywords.
        - governance:    Signal strength and matched keywords.
        - red_flags:     List of controversy keywords detected.
        - esg_headlines: Headlines with ESG content.
        - has_esg_signal: True if any ESG keywords were found.

        The '__global_esg__' key contains portfolio-level GDELT events
        with sustainability relevance.
    """
    tickers = [s["ticker"] for s in portfolio["portfolio"]]
    results = {}

    for ticker in tickers:
        env_matches = []
        social_matches = []
        gov_matches = []
        red_flags = []
        esg_headlines = []

        # -- Scan news RSS headlines -------------------------------------------
        news = data.get("news_rss", {})
        ticker_news = news.get(ticker, [])
        for item in ticker_news:
            title = item.get("title", "")
            e = _scan_text(title, ENVIRONMENTAL_KEYWORDS)
            s = _scan_text(title, SOCIAL_KEYWORDS)
            g = _scan_text(title, GOVERNANCE_KEYWORDS)
            r = _scan_text(title, ESG_RED_FLAGS)
            env_matches.extend(e)
            social_matches.extend(s)
            gov_matches.extend(g)
            red_flags.extend(r)
            if e or s or g or r:
                category = "E" if e else ("S" if s else "G")
                esg_headlines.append(f"[{category}] {title[:120]}")

        # -- Scan press releases / 8-K ----------------------------------------
        prs = data.get("press_releases", {})
        ticker_prs = prs.get(ticker, [])
        for pr in ticker_prs:
            title = pr.get("title", "")
            summary = pr.get("summary", "")
            text = f"{title} {summary}"
            e = _scan_text(text, ENVIRONMENTAL_KEYWORDS)
            s = _scan_text(text, SOCIAL_KEYWORDS)
            g = _scan_text(text, GOVERNANCE_KEYWORDS)
            r = _scan_text(text, ESG_RED_FLAGS)
            env_matches.extend(e)
            social_matches.extend(s)
            gov_matches.extend(g)
            red_flags.extend(r)
            if e or s or g or r:
                category = "E" if e else ("S" if s else "G")
                esg_headlines.append(f"[{category}] {title[:120]}")

        # -- Scan Reddit for ESG discussion ------------------------------------
        reddit = data.get("reddit", {})
        ticker_reddit = reddit.get(ticker, {})
        if isinstance(ticker_reddit, dict) and not ticker_reddit.get("error"):
            for post in ticker_reddit.get("top_posts", []):
                title = post.get("title", "")
                r = _scan_text(title, ESG_RED_FLAGS)
                g = _scan_text(title, GOVERNANCE_KEYWORDS)
                red_flags.extend(r)
                gov_matches.extend(g)

        # -- Check thesis risks for ESG angle ----------------------------------
        stock = next(
            (s for s in portfolio["portfolio"] if s["ticker"] == ticker), {}
        )
        for risk in stock.get("thesis_risks", []):
            g = _scan_text(risk, GOVERNANCE_KEYWORDS)
            r = _scan_text(risk, ESG_RED_FLAGS)
            gov_matches.extend(g)
            red_flags.extend(r)

        # -- Deduplicate and summarize -----------------------------------------
        env_unique = sorted(set(env_matches))
        social_unique = sorted(set(social_matches))
        gov_unique = sorted(set(gov_matches))
        red_unique = sorted(set(red_flags))

        results[ticker] = {
            "environmental": {
                "signal":   _score_category(env_unique),
                "keywords": env_unique[:5],
            },
            "social": {
                "signal":   _score_category(social_unique),
                "keywords": social_unique[:5],
            },
            "governance": {
                "signal":   _score_category(gov_unique),
                "keywords": gov_unique[:5],
            },
            "red_flags":      red_unique[:5] if red_unique else [],
            "esg_headlines":  esg_headlines[:3],
            "has_esg_signal": bool(env_unique or social_unique or gov_unique or red_unique),
        }

    # -- Portfolio-level GDELT sustainability context --------------------------
    world = data.get("world_news", {})
    global_esg = []
    for event in world.get("top_events", []):
        matches = _scan_text(event, ENVIRONMENTAL_KEYWORDS | SOCIAL_KEYWORDS)
        if matches:
            global_esg.append(event)

    results["__global_esg__"] = global_esg[:5]

    return results
