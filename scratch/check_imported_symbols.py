import sys
import os
sys.path.insert(0, os.getcwd())

import bot
import handlers.premium
import handlers.saas
import handlers.referral

print("premium dir:", [x for x in dir(handlers.premium) if "handler" in x])
print("saas dir:", [x for x in dir(handlers.saas) if "handler" in x])
print("referral dir:", [x for x in dir(handlers.referral) if "handler" in x])
