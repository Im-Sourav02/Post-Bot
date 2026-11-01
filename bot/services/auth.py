from bot import config
from bot.db import admins


def is_owner(user_id: int | None) -> bool:
    return user_id == config.OWNER_ID


async def is_authorized(user_id: int | None) -> bool:
    if user_id is None:
        return False
    return is_owner(user_id) or await admins.is_admin(user_id)
