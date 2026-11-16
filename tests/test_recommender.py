from src.recommender import Song, UserProfile, Recommender, load_songs, recommend_songs

def make_small_recommender() -> Recommender:
    songs = [
        Song(
            id=1,
            title="Test Pop Track",
            artist="Test Artist",
            genre="pop",
            mood="happy",
            energy=0.8,
            tempo_bpm=120,
            valence=0.9,
            danceability=0.8,
            acousticness=0.2,
        ),
        Song(
            id=2,
            title="Chill Lofi Loop",
            artist="Test Artist",
            genre="lofi",
            mood="chill",
            energy=0.4,
            tempo_bpm=80,
            valence=0.6,
            danceability=0.5,
            acousticness=0.9,
        ),
    ]
    return Recommender(songs)


def test_recommend_returns_songs_sorted_by_score():
    user = UserProfile(
        favorite_genre="pop",
        favorite_mood="happy",
        target_energy=0.8,
        likes_acoustic=False,
    )
    rec = make_small_recommender()
    results = rec.recommend(user, k=2)

    assert len(results) == 2
    # Starter expectation: the pop, happy, high energy song should score higher
    assert results[0].genre == "pop"
    assert results[0].mood == "happy"


def test_explain_recommendation_returns_non_empty_string():
    user = UserProfile(
        favorite_genre="pop",
        favorite_mood="happy",
        target_energy=0.8,
        likes_acoustic=False,
    )
    rec = make_small_recommender()
    song = rec.songs[0]

    explanation = rec.explain_recommendation(user, song)
    assert isinstance(explanation, str)
    assert explanation.strip() != ""


def test_recommender_ranks_matching_song_first_for_profile_data():
    user = UserProfile(
        favorite_genre="pop",
        favorite_mood="happy",
        target_energy=0.8,
        likes_acoustic=False,
    )
    rec = make_small_recommender()

    results = rec.recommend(user, k=2)

    assert results[0].title == "Test Pop Track"
    assert results[0].genre == "pop"
    assert results[1].title == "Chill Lofi Loop"


def test_explain_recommendation_mentions_specific_matching_features():
    user = UserProfile(
        favorite_genre="pop",
        favorite_mood="happy",
        target_energy=0.8,
        likes_acoustic=False,
    )
    rec = make_small_recommender()

    explanation = rec.explain_recommendation(user, rec.songs[0])

    assert "genre match" in explanation.lower()
    assert "mood match" in explanation.lower()


def test_likes_acoustic_preference_affects_recommendation_order():
    rec = make_small_recommender()
    user = UserProfile(likes_acoustic=True)

    results = rec.recommend(user, k=2)

    assert results[0].title == "Chill Lofi Loop"


def test_spotify_csv_is_normalized_and_missing_mood_is_derived(tmp_path):
    csv_path = tmp_path / "spotify.csv"
    csv_path.write_text(
        "track_id,track_name,track_artist,playlist_genre,energy,tempo,valence,"
        "danceability,acousticness\n"
        "abc,Acoustic Song,Artist,pop,0.2,90,0.6,0.4,0.9\n"
        "def,Electric Song,Artist,rock,0.9,140,0.8,0.9,0.1\n"
        "abc,Acoustic Song,Artist,pop,0.2,90,0.6,0.4,0.9\n",
        encoding="utf-8",
    )

    songs = load_songs(str(csv_path))

    assert len(songs) == 2
    assert songs[0]["id"] == 1
    assert songs[0]["title"] == "Acoustic Song"
    assert songs[0]["genre"] == "pop"
    assert songs[0]["mood"] == "calm"
    results = recommend_songs(
        {
            "favorite_genre": "pop",
            "favorite_mood": "happy",
            "target_energy": 0.2,
        },
        songs,
        k=2,
    )
    assert results[0][0]["title"] == "Acoustic Song"


def test_spotify_csv_uses_manual_language_labels_and_derives_era(tmp_path):
    csv_path = tmp_path / "spotify.csv"
    csv_path.write_text(
        "track_id,track_name,track_artist,track_album_release_date,playlist_genre,"
        "energy,tempo,valence,danceability,acousticness\n"
        "abc,Song,Artist,2017-05-01,pop,0.5,100,0.5,0.5,0.5\n",
        encoding="utf-8",
    )
    labels_path = tmp_path / "language_labels.csv"
    labels_path.write_text(
        "track_id,language\nabc,Spanish\n",
        encoding="utf-8",
    )

    song = load_songs(str(csv_path), str(labels_path))[0]

    assert song["language"] == "Spanish"
    assert song["era"] == "2010s"
    recommender = Recommender([Song(**song)])
    ranked = recommender.recommend(
        UserProfile(favorite_genre="pop", target_energy=0.5),
        k=1,
    )
    assert ranked[0].track_id == "abc"
