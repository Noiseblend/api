from addict import Dict

PRIORITY = Dict(
    {
        "request": {
            "cors": 0,
            "camelcase_to_snakecase": 1,
            "add_redis_pool": 2,
            "add_db_pool": 2,
            "add_spotify_client": 3,
            "authorize_request": 4,
            "add_arq_actors": 5,
            "check_etag": 7,
        },
        "response": {
            "snakecase_to_camelcase": 0,
            "close_spotify_client": 1,
            "cache_response": 2,
        },
    }
)
