from datetime import datetime
from hashlib import sha256
from uuid import UUID, uuid4

from pony.orm import Json, Optional, PrimaryKey, Required, Set, composite_key
from spfy.cache import db
from spfy.sql import SQL_DEFAULT

from . import config

# pylint: disable=too-few-public-methods


def gentoken():
    return sha256(uuid4().bytes).hexdigest()


def cap(val, _min, _max):
    return min(max(val, _min), _max)


class Blend(db.Entity):
    _table_ = "blends"
    token = PrimaryKey(str, default=gentoken)
    name = Required(str, index=True)
    user = Required("AppUser")
    composite_key(user, name)


class Token(db.Entity):
    _table_ = "tokens"
    # pylint: disable=redefined-builtin
    id = PrimaryKey(UUID, default=uuid4, sql_default=SQL_DEFAULT.uuid4)
    user = Required("AppUser")
    expires_at = Optional(
        datetime, sql_default=f"{SQL_DEFAULT.now} + '1 hour'", index=True
    )
    valid = Optional(bool, sql_default=SQL_DEFAULT.bool_true, index=True)


class AppUser(db.Entity):
    _table_ = "app_users"

    # pylint: disable=redefined-builtin
    id = PrimaryKey(UUID, default=uuid4, sql_default=SQL_DEFAULT.uuid4)
    artist_time_range = Optional(str, sql_default="''")
    genre_time_range = Optional(str, sql_default="''")
    email_confirmed = Required(bool, default=False, sql_default=SQL_DEFAULT.bool_false)
    email_token = Optional(str, sql_default="''")
    auth_token = Required(
        UUID, default=uuid4, index=True, sql_default=SQL_DEFAULT.uuid4
    )
    device_mapping = Required(Json, default=dict, volatile=True, sql_default="'{}'")
    blends = Set(Blend)

    first_blend = Required(bool, default=True, sql_default=SQL_DEFAULT.bool_true)
    first_play = Required(bool, default=True, sql_default=SQL_DEFAULT.bool_true)
    first_login = Required(bool, default=True, sql_default=SQL_DEFAULT.bool_true)
    first_dislike = Required(bool, default=True, sql_default=SQL_DEFAULT.bool_true)
    first_playlist = Required(bool, default=True, sql_default=SQL_DEFAULT.bool_true)
    first_genre_click = Required(bool, default=True, sql_default=SQL_DEFAULT.bool_true)
    first_country_click = Required(
        bool, default=True, sql_default=SQL_DEFAULT.bool_true
    )
    second_discover = Required(bool, default=True, sql_default=SQL_DEFAULT.bool_true)
    second_playlist = Required(bool, default=True, sql_default=SQL_DEFAULT.bool_true)
    blend_hint_hidden = Required(
        bool, default=False, sql_default=SQL_DEFAULT.bool_false
    )
    donate_button_hidden = Required(
        bool, default=False, sql_default=SQL_DEFAULT.bool_false
    )
    drift_message_hidden = Required(
        bool, default=False, sql_default=SQL_DEFAULT.bool_false
    )
    oauth_tokens = Set(Token)
    oauth_code = Optional(UUID, index=True)
    oauth_refresh_token = Required(
        UUID, default=uuid4, index=True, sql_default=SQL_DEFAULT.uuid4
    )

    def to_dict(self, *args, **kwargs):  # pylint: disable=arguments-differ
        _dict = super().to_dict(*args, **kwargs)
        if "id" in _dict:
            _dict["id"] = str(_dict["id"])
        if "auth_token" in _dict:
            _dict["auth_token"] = str(_dict["auth_token"])
        return _dict

    def reset_token(self):
        self.auth_token = uuid4()


db.generate_mapping(
    create_tables=str(config.db.create_tables).lower() in ["true", "1", "yes"]
)
db.disconnect()
