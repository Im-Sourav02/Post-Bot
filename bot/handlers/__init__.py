from pyrogram import Client, filters
from pyrogram.handlers import CallbackQueryHandler, MessageHandler

from bot import config
from bot.handlers import guard, myposts, newpost, owner, resend, router, settings, start  # noqa: F401 (registers callbacks)

OWNER_COMMANDS = {
    "addadmin": owner.addadmin_cmd,
    "dltadmin": owner.dltadmin_cmd,
    "admins": owner.admins_cmd,
    "addchannel": owner.addchannel_cmd,
    "removechannel": owner.removechannel_cmd,
}
ADMIN_COMMANDS = {
    "start": start.start_cmd,
    "help": start.help_cmd,
    "cancel": start.cancel_cmd,
    "newpost": newpost.newpost_cmd,
    "myposts": myposts.myposts_cmd,
    "settings": settings.settings_cmd,
}


def register(app: Client) -> None:
    private = filters.private

    # Group -1 runs first and stops propagation for anyone who isn't the owner or an admin.
    app.add_handler(MessageHandler(guard.deny_message, private & guard.unauthorized), group=-1)
    app.add_handler(CallbackQueryHandler(guard.deny_callback, guard.unauthorized), group=-1)

    # Within a group only the first matching handler runs, so order matters.
    owner_only = filters.user(config.OWNER_ID)
    for name, fn in OWNER_COMMANDS.items():
        app.add_handler(MessageHandler(fn, filters.command(name) & owner_only))
    app.add_handler(MessageHandler(owner.owner_only_cmd, filters.command(list(OWNER_COMMANDS)) & private))
    for name, fn in ADMIN_COMMANDS.items():
        app.add_handler(MessageHandler(fn, filters.command(name) & private))

    app.add_handler(CallbackQueryHandler(router.on_callback))
    app.add_handler(MessageHandler(router.on_message, private))
