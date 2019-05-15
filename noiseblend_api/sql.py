# pylint: disable=too-few-public-methods
class SQL:
    insert_token = """
        INSERT INTO tokens ("user")
        VALUES ($1)
        RETURNING *
    """
    user_tokens = """
        SELECT id FROM tokens
        WHERE
            "user" = $1 AND
            valid AND
            expires_at > (now() at time zone 'utc')
    """
    oauth_token_expired = """
        SELECT (t.expires_at <= (now() at time zone 'utc')) AS expired
        FROM users u
            INNER JOIN tokens t
            ON u.id = t."user"
        WHERE
            t.id = $1 AND
            t.valid
    """
    app_user_by_token = """
        SELECT au.id, u.username
        FROM app_users au
            INNER JOIN tokens t ON au.id = t."user"
            INNER JOIN users u ON u.id = au.id
        WHERE
            t.id = $1 AND
            t.valid AND
            t.expires_at > (now() at time zone 'utc')
    """
    map_device = """
        UPDATE app_users
        SET device_mapping = (device_mapping || $1)
        WHERE id = $2"""
    user_artist_time_range = "SELECT artist_time_range FROM app_users WHERE id = $1"
    user_genre_time_range = "SELECT genre_time_range FROM app_users WHERE id = $1"
    user_country = "SELECT country, preferred_country FROM users WHERE id = $1"
    disliked_artists = """
        SELECT artist
        FROM artist_haters
        WHERE "user" = $1
    """
    disliked_genres = """
        SELECT genre
        FROM genre_haters
        WHERE "user" = $1
    """
    user_data = """
        SELECT u.*, au.*,
               c.name AS country_name,
               json_agg(json_build_object('url', i.url, 'color', i.color)) AS images
        FROM users u
            INNER JOIN countries c ON c.code = u.country
            LEFT OUTER JOIN images i ON i.user = u.id, app_users au
        WHERE u.id = $1 AND au.id = $1
        GROUP BY u.id, au.id, c.name
    """
    app_user = "SELECT * FROM app_users WHERE id = $1"
    app_user_by_code = "SELECT * FROM app_users WHERE oauth_code = $1"
    app_user_by_refresh_token = "SELECT * FROM app_users WHERE oauth_refresh_token = $1"
    app_user_auth = """
        SELECT au.id, u.username
        FROM app_users au
        INNER JOIN users u ON u.id = au.id
        WHERE au.auth_token = $1"""
    app_user_auth_long_lived = """
        SELECT au.id, u.username
        FROM app_users au
        INNER JOIN users u ON u.id = au.id
        WHERE au.long_lived_token IS NOT NULL AND au.long_lived_token = $1"""
    blend_auth = """
        SELECT b.*, u.username
        FROM blends b
        INNER JOIN users u ON u.id = b.user
        WHERE b.token = $1"""
    user = "SELECT * FROM users WHERE id = $1"
    upsert_app_user = """
        INSERT INTO app_users AS au (id)
        VALUES ($1)
        ON CONFLICT (id) DO UPDATE SET email_confirmed = $2
        RETURNING *
    """
    smallest_image = """
        SELECT DISTINCT
            {0}, color,
            first_value(url) OVER (PARTITION BY {0} ORDER BY width) AS url
        FROM images
        WHERE {0} = ANY($1::text[])
    """
    blend_token = """
        SELECT token FROM blends
        WHERE "user" = $1 AND "name" = $2
    """
    upsert_blend = """
        INSERT INTO blends AS b ("user", name, token)
        VALUES ($1, $2, $3)
        ON CONFLICT DO NOTHING
        RETURNING token
    """
    genre_playlists = """
        SELECT p.*
        FROM playlists p
        WHERE p.genre = ANY($1::text[])
    """
    country_playlists = """
        SELECT p.*
        FROM playlists p
        WHERE
            p.country = ANY($1::text[]) AND
            p.city IS NULL AND
            p.date IS NULL
    """
    city_playlists = """
        SELECT p.*
        FROM playlists p
        WHERE
            p.country = $2 AND
            p.city IS NOT NULL AND
            p.city = ANY($1::text[])
    """
    country_playlists_ignore = """
        SELECT p.*
        FROM playlists p
        WHERE
            p.country <> ALL($1::text[]) AND
            p.city IS NULL AND
            p.date IS NULL AND
            p.country NOT IN (
                SELECT country
                FROM country_haters
                WHERE "user" = $4
            )
    """
    city_playlists_ignore = """
        SELECT p.*
        FROM playlists p
        WHERE
            p.country = $4 AND
            p.city IS NOT NULL AND
            p.city <> ALL($1::text[]) AND
            p.city NOT IN (
                SELECT city
                FROM city_haters
                WHERE "user" = $5
            )
    """
    item_playlists = """
        WITH
            {singular}_playlists AS ({playlist_query}),
            wanted_{plural} AS (
                SELECT {singular}
                FROM {singular}_playlists pls
                GROUP BY {singular}
                ORDER BY random()
                LIMIT {limit}),
            {singular}_images AS (
                SELECT i.url, i.color, i.{singular},
                    i.unsplash_user_fullname, i.unsplash_user_username
                FROM images i
                WHERE i.{singular} IN (SELECT {singular} FROM wanted_{plural}) AND (
                        (i.width >= $2) OR
                        (i.height >= $3)
                    ))
        SELECT DISTINCT ON (pls.id) pls.*,
            json_build_object(
                'url', gi.url, 'color', gi.color,
                'unsplash_user_fullname', gi.unsplash_user_fullname,
                'unsplash_user_username', gi.unsplash_user_username
            ) AS image
        FROM {singular}_playlists pls
        LEFT OUTER JOIN {singular}_images gi ON gi.{singular} = pls.{singular}
        WHERE pls.{singular} IN (SELECT {singular} FROM wanted_{plural})
        ORDER BY pls.id
    """
    all_item_playlists = """
        WITH
            {singular}_playlists AS ({playlist_query}),
            wanted_{plural} AS (
                SELECT {singular}
                FROM {singular}_playlists pls
                GROUP BY {singular}),
            {singular}_images AS (
                SELECT i.url, i.color, i.{singular},
                    i.unsplash_user_fullname, i.unsplash_user_username
                FROM images i
                WHERE i.{singular} IN (SELECT {singular} FROM wanted_{plural}) AND (
                        (i.width >= $2) OR
                        (i.height >= $3)
                    ))
        SELECT DISTINCT ON (pls.id) pls.*,
            json_build_object(
                'url', gi.url, 'color', gi.color,
                'unsplash_user_fullname', gi.unsplash_user_fullname,
                'unsplash_user_username', gi.unsplash_user_username
            ) AS image
        FROM {singular}_playlists pls
        LEFT OUTER JOIN {singular}_images gi ON gi.{singular} = pls.{singular}
        WHERE pls.{singular} IN (SELECT {singular} FROM wanted_{plural})
        ORDER BY pls.id
    """
