import logging


SETTING = {
    "studying": (.3, 85, .6), "workout": (.9, 130, .1),
    "night drive": (.55, 100, .3), "party": (.85, 120, .1),
    "relaxing": (.25, 75, .8),
}
MOOD_TARGETS = {
    "sad/mellow": (.25, .25), "intense/angry": (.75, .25),
    "chill/peaceful": (.25, .75), "happy/hype": (.75, .75),
}
WEIGHTS = {
    "era": .3, "mood": .2, "genre_tags": .2, "energy": .12,
    "tempo": .07, "valence": .04, "danceability": .03,
    "acousticness": .03, "speechiness": .01,
}


def score_song(song, profile):
    mood = profile["mood"]["value"]
    setting = profile["setting"]["value"]
    energy, valence = MOOD_TARGETS[mood]
    setting_energy, tempo, acoustic = SETTING[setting]
    targets = {
        "energy": profile["energy_hint"]["value"] if profile["energy_hint"]["value"] is not None else (energy + setting_energy) / 2,
        "tempo": profile["tempo_hint"]["value"] if profile["tempo_hint"]["value"] is not None else tempo,
        "valence": valence,
        "danceability": .85 if setting in {"party", "workout"} else .35,
        "acousticness": profile["acoustic_hint"]["value"] if profile["acoustic_hint"]["value"] is not None else acoustic,
        "speechiness": .05,
    }
    similarities = {
        "era": float(profile["era"]["value"] == "any" or song["era"] == profile["era"]["value"]),
        "mood": float(song["mood"] == mood),
        "genre_tags": float(
            not profile["genre_tags"]["value"]
            or bool(set(song["genre_tags"]) & set(profile["genre_tags"]["value"]))
        ),
    }
    for feature, target in targets.items():
        scale = 160 if feature == "tempo" else 1
        similarities[feature] = max(0, 1 - abs(song[feature] - target) / scale)
    available = sum(WEIGHTS[key] for key in similarities)
    breakdown = {
        key: round(100 * WEIGHTS[key] * value / available, 2)
        for key, value in similarities.items()
    }
    return sum(breakdown.values()), breakdown


def _valid(song, profile):
    if profile["era"]["value"] != "any" and song["era"] != profile["era"]["value"]:
        return False
    tags = set(song["genre_tags"])
    included = set(profile["genre_tags"]["value"])
    excluded = set(profile["excluded_tags"]["value"])
    return (not included or bool(tags & included)) and not bool(tags & excluded)


def verify(tracks, catalog, profile):
    issues = []
    catalog_ids = {song["track_id"] for song in catalog}
    ids = [song["track_id"] for song in tracks]
    if any(track_id not in catalog_ids for track_id in ids):
        issues.append("A selected track is not in the catalog.")
    if len(ids) != len(set(ids)):
        issues.append("Duplicate tracks are present.")
    if any(not _valid(song, profile) for song in tracks):
        issues.append("Era or genre tag filters are not respected.")
    duration = sum(song["duration_ms"] for song in tracks) / 60000
    target = profile["length_minutes"]["value"]
    if not target * .9 <= duration <= target * 1.1:
        issues.append(f"Duration {duration:.1f} min is outside 10% of {target} min.")
    return issues


def _select(ranked, profile, excluded):
    target = profile["length_minutes"]["value"]
    total, selected = 0, []
    for song in ranked:
        if song["track_id"] in excluded:
            continue
        duration = song["duration_ms"] / 60000
        if total + duration > target * 1.1:
            continue
        if total >= target * .9 and abs(total + duration - target) > abs(total - target):
            continue
        selected.append(song)
        total += duration
        if total >= target or len(selected) == 50:
            break
    return selected


def build_playlist(catalog, profile, logger=None):
    logger = logger or logging.getLogger(__name__)
    scored = []
    for song in catalog:
        score, breakdown = score_song(song, profile)
        scored.append({**song, "score": round(score, 2), "breakdown": breakdown})
    scored.sort(key=lambda song: song["score"], reverse=True)
    matching = [song for song in scored if _valid(song, profile)]
    candidates = matching or scored
    excluded, best, best_issues = set(), [], ["No tracks selected."]

    for attempt in range(1, 4):
        selected = _select(candidates, profile, excluded)
        issues = verify(selected, catalog, profile)
        error = abs(sum(s["duration_ms"] for s in selected) / 60000 - profile["length_minutes"]["value"])
        best_error = abs(sum(s["duration_ms"] for s in best) / 60000 - profile["length_minutes"]["value"])
        if (not best or (len(issues), error) < (len(best_issues), best_error)):
            best, best_issues = selected, issues
        logger.info("playlist attempt=%d selected=%d valid=%s", attempt, len(selected), not issues)
        if not issues:
            break
        if selected:
            excluded.add(selected[-1]["track_id"])
    average = sum(song["score"] for song in best) / (100 * len(best)) if best else 0
    verifier_score = max(0, 1 - len(best_issues) / 4)
    meta = profile.get("_meta", {})
    coverage = 0 if meta.get("unmatched_terms") else 1
    retry_score = (4 - attempt) / 3
    confidence = round(max(0, min(1, .4 * average + .3 * verifier_score + .2 * coverage + .1 * retry_score)), 3)
    logger.info("playlist_confidence score=%.3f attempts=%d", confidence, attempt)
    return {
        "tracks": best, "issues": best_issues, "attempts": attempt,
        "confidence": confidence,
        "label": "high" if confidence >= .8 else "medium" if confidence >= .6 else "low",
    }
