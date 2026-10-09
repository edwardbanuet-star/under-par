#!/usr/bin/env python3
"""Rank golf instruction YouTube channels and write channels_ranked.json.

Factors: subscribers, number of videos, time on platform (channel age), and comment sentiment.
Cheap on quota: channels.list, playlistItems.list and commentThreads.list cost about 1 unit each.
The only expensive call is search.list (100 units), used once per channel to find its ID; IDs are
cached in channel_ids.json. Needs: pip install vaderSentiment

Usage:
  YOUTUBE_API_KEY=your_key python scripts/rank_channels.py [--debug]
"""
import json, math, os, sys, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG, IDS, OUT = ROOT / "channels.json", ROOT / "channel_ids.json", ROOT / "channels_ranked.json"
API = "https://www.googleapis.com/youtube/v3/"
KEY = os.environ.get("YOUTUBE_API_KEY", "")


class QuotaError(Exception):
    pass


def api(path, **p):
    p["key"] = KEY
    try:
        with urllib.request.urlopen(API + path + "?" + urllib.parse.urlencode(p), timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        if "quotaExceeded" in body:
            raise QuotaError(body[:200])
        raise RuntimeError(f"{e.code} on {path}: {body[:200]}")


def resolve(seeds, ids):
    """Find each channel's ID once (search.list, 100 units) and cache it."""
    for s in seeds:
        name = s["name"]
        if s.get("id"):
            ids[name] = s["id"]
        if name in ids:
            continue
        items = api("search", part="snippet", type="channel", q=name, maxResults=1).get("items", [])
        if not items:
            print("  not found:", name)
            continue
        ids[name] = items[0]["snippet"]["channelId"]
        print(f"  resolved {name!r} -> {items[0]['snippet']['title']!r} (check this is right)")


def analyzer():
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    a = SentimentIntensityAnalyzer()
    # Golf-flavoured words the general lexicon misses
    a.lexicon.update({"fixed": 2.0, "lifesaver": 3.0, "striping": 2.5, "pure": 1.5, "crushed": 2.0, "gamechanger": 3.0})
    return a


def comments_for(channel_uploads, n_videos):
    vids = [i["contentDetails"]["videoId"] for i in
            api("playlistItems", part="contentDetails", playlistId=channel_uploads, maxResults=n_videos).get("items", [])]
    out = []
    for v in vids:
        try:
            r = api("commentThreads", part="snippet", videoId=v, maxResults=100, order="time", textFormat="plainText")
        except RuntimeError:
            continue  # comments disabled on this video
        out += [i["snippet"]["topLevelComment"]["snippet"]["textDisplay"][:300] for i in r.get("items", [])]
    return out


def sentiment(texts, an):
    n = len(texts)
    if not n:
        return {"score": 0.0, "pos": 0.0, "neg": 0.0, "n": 0}
    s = [an.polarity_scores(t)["compound"] for t in texts]
    mean = sum(s) / n
    return {"score": round(mean * n / (n + 50), 3),  # few comments -> pulled toward neutral
            "pos": round(sum(x > .05 for x in s) / n, 2), "neg": round(sum(x < -.05 for x in s) / n, 2), "n": n}


def minmax(vals):
    lo, hi = min(vals), max(vals)
    return [(v - lo) / (hi - lo) if hi > lo else .5 for v in vals]


def main():
    if not KEY:
        sys.exit("Set the YOUTUBE_API_KEY environment variable first.")
    cfg = json.loads(CFG.read_text())
    ids = json.loads(IDS.read_text()) if IDS.exists() else {}
    try:
        resolve(cfg["seeds"], ids)
        IDS.write_text(json.dumps(ids, indent=1) + "\n")
        wanted = [ids[s["name"]] for s in cfg["seeds"] if s["name"] in ids]
        raw = []
        for i in range(0, len(wanted), 50):
            raw += api("channels", part="snippet,statistics,contentDetails", id=",".join(wanted[i:i + 50])).get("items", [])
        now, rows = datetime.now(timezone.utc), []
        for c in raw:
            st = c["statistics"]
            if st.get("hiddenSubscriberCount"):
                continue
            since = datetime.fromisoformat(c["snippet"]["publishedAt"].replace("Z", "+00:00"))
            age = (now - since).days / 365.25
            subs, vids = int(st.get("subscriberCount", 0)), int(st.get("videoCount", 0))
            if subs < cfg["min_subscribers"] or vids < cfg["min_videos"] or age < cfg["min_age_years"]:
                print("  below thresholds, skipped:", c["snippet"]["title"])
                continue
            rows.append({"id": c["id"], "title": c["snippet"]["title"], "handle": c["snippet"].get("customUrl", ""),
                         "thumbnail": c["snippet"]["thumbnails"].get("default", {}).get("url", ""),
                         "subscribers": subs, "videos": vids, "since": since.date().isoformat(),
                         "age_years": round(age, 1), "_up": c["contentDetails"]["relatedPlaylists"]["uploads"]})
        an = analyzer()
        for r in rows:  # comments only for channels that passed the thresholds
            r["sentiment"] = sentiment(comments_for(r.pop("_up"), cfg["videos_per_channel"]), an)
            print(f"  {r['title']}: {r['subscribers']:,} subs, sentiment {r['sentiment']['score']} ({r['sentiment']['n']} comments)")
    except QuotaError as e:
        sys.exit("YouTube quota exceeded; nothing written. Try again tomorrow. " + str(e))

    if not rows:
        sys.exit("No channels passed the thresholds; nothing written.")
    w = cfg["weights"]; tot = sum(w.values())
    parts = {"subscribers": minmax([math.log1p(r["subscribers"]) for r in rows]),
             "videos": minmax([math.log1p(r["videos"]) for r in rows]),
             "age": [min(r["age_years"], 10) / 10 for r in rows],
             "sentiment": minmax([r["sentiment"]["score"] for r in rows])}
    for i, r in enumerate(rows):
        r["score"] = round(100 * sum(w[k] / tot * parts[k][i] for k in parts), 1)
    rows.sort(key=lambda r: -r["score"])
    for n, r in enumerate(rows, 1):
        r["rank"] = n
    OUT.write_text(json.dumps({"updated_at": now.isoformat(timespec="seconds"), "weights": w, "channels": rows}, indent=1) + "\n")
    print("Wrote", OUT.name, "with", len(rows), "channels.")


if __name__ == "__main__":
    main()
