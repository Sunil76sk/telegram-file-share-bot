import asyncio
from collections import defaultdict

# Global lock for broadcasting safely
broadcast_lock = asyncio.Lock()

# Per-user locks for uploads, edit UI operations, and password setting/entry sessions
user_locks = defaultdict(asyncio.Lock)

# Active processing counts per user to track concurrent album/file uploads
processing_counts = defaultdict(int)
