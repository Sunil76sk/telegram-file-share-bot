import inspect
import pyrogram.filters as filters

# Inspect AndFilter and NotFilter if they exist in pyrogram.filters
for name in dir(filters):
    cls = getattr(filters, name)
    if isinstance(cls, type) and issubclass(cls, filters.Filter):
        if name in ("AndFilter", "OrFilter", "NotFilter", "InvertFilter"):
            print(f"--- {name} ---")
            try:
                print(inspect.getsource(cls))
            except Exception as e:
                print(f"Error getting source: {e}")
