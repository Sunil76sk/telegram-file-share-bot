import asyncio
from pyrogram import filters

async def test_func(flt, client, message):
    return False

f = filters.create(test_func)
not_f = ~f

async def run():
    try:
        res_f = f(None, None)
        if asyncio.iscoroutine(res_f):
            res_f = await res_f
        print("f result:", res_f)
    except Exception as e:
        print("f error:", e)

    try:
        res_not_f = not_f(None, None)
        if asyncio.iscoroutine(res_not_f):
            res_not_f = await res_not_f
        print("not_f result:", res_not_f)
    except Exception as e:
        print("not_f error:", e)

asyncio.run(run())
