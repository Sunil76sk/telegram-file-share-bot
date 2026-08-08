import sys
import os
sys.path.insert(0, os.getcwd())

import bot
from handlers.premium import app as premium_app
from handlers.saas import app as saas_app

print("bot.app id:", id(bot.app))
print("handlers.premium.app id:", id(premium_app))
print("handlers.saas.app id:", id(saas_app))
print("Is premium.app same as bot.app?", bot.app is premium_app)
print("Is saas.app same as bot.app?", bot.app is saas_app)
