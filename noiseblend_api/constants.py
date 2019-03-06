BLEND_PLAYLIST_NAME = "Noiseblend: Placeholder"
BLEND_PLAYLIST_DESCRIPTION = """\
This playlist will be overwritten at the next blend usage. \
You can save the playlist by simply renaming it."""

PLAYLIST_DESCRIPTIONS = {
    "city": "The music that people from {city} are listening to right now",
    "country": {
        "pine_needle": "Emerging Christmas music from {country}",
        "needle": {
            "all": "Scattered outbursts of {country}'s love, collected by Spotify's curious machine",
            "current": "The electric pulse of {country}'s love, detected by Spotify's curious machine",
            "emerging": "The hopes and futures of {country}'s love, detected by Spotify's curious machine",
            "underground": "The most secret glimmerings of {country}'s love, detected by Spotify's curious machine",
        },
    },
    "genre": {
        "meta": {
            "year": "Songs that fans of {genre} were listening to in {year}",
            "pulse": "Emerging songs that fans of {genre} are listening to right now",
            "edge": "Less known songs that fans of {genre} are listening to right now",
        },
        "normal": {
            "intro": "An attempted algorithmic introduction to {genre} based on math and listening data from the Large Genre Collider",
            "year": "Most listened {genre} songs in {year}",
            "sound": "Most popular songs from the {genre} genre",
            "pulse": "Emerging songs from the {genre} genre",
            "edge": "Less-known songs from the {genre} genre",
        },
    },
}

APP_USER_FLAGS = {
    "first_blend",
    "first_play",
    "first_login",
    "first_dislike",
    "first_playlist",
    "first_genre_click",
    "first_country_click",
    "second_discover",
    "second_playlist",
    "blend_hint_hidden",
    "donate_button_hidden",
    "drift_message_hidden",
}


USER_FIELDS = {"created_at", "preferred_country", "spotify_premium"}

APP_USER_FIELDS = {
    "artist_time_range",
    "genre_time_range",
    "images",
    "country_name",
    *APP_USER_FLAGS,
}
FULL_USER_FIELDS = USER_FIELDS | {
    "email",
    "username",
    "country",
    "display_name",
    "birthdate",
}
FULL_APP_USER_FIELDS = APP_USER_FIELDS | {"email_token", "auth_token"}
BLEND_ALLOWED_FIELDS = USER_FIELDS | APP_USER_FIELDS
ALL_FIELDS = FULL_USER_FIELDS | FULL_APP_USER_FIELDS
