import sys
import os
import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.getcwd())

# Setup asyncio event loop
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# ─── IN-MEMORY MONGO MOCKS ───────────────────────────────────────────
class MockMotorCollection:
    def __init__(self, name):
        self.name = name
        self.data = {}

    async def delete_many(self, query):
        self.data.clear()
        return MagicMock(deleted_count=1)

    async def update_one(self, query, update, upsert=False):
        doc_id = query.get("_id")
        set_data = update.get("$set", {})
        if doc_id not in self.data:
            self.data[doc_id] = {"_id": doc_id}
        self.data[doc_id].update(set_data)
        return MagicMock(modified_count=1)

    async def find_one(self, query):
        doc_id = query.get("_id")
        if doc_id is None:
            for doc in self.data.values():
                if doc.get("channel_id") == query.get("channel_id"):
                    return doc
            return None
        return self.data.get(doc_id)

    async def delete_one(self, query):
        doc_id = query.get("_id")
        if doc_id in self.data:
            del self.data[doc_id]
            return MagicMock(deleted_count=1)
        return MagicMock(deleted_count=0)

    def find(self, query):
        user_id = query.get("user_id")
        
        class AsyncCursor:
            def __init__(self, results):
                self.results = results
                self.index = 0
            def __aiter__(self):
                return self
            async def __anext__(self):
                if self.index < len(self.results):
                    val = self.results[self.index]
                    self.index += 1
                    return val
                raise StopAsyncIteration
                
        results = [doc for doc in self.data.values() if doc.get("user_id") == user_id]
        return AsyncCursor(results)

# Create Mock Collections
mock_post_drafts = MockMotorCollection("post_drafts")
mock_channels = MockMotorCollection("channels")
mock_users = MockMotorCollection("users")

# Patch the mongo module before importing other modules
import database.mongo
database.mongo.post_drafts_col = mock_post_drafts
database.mongo.channels_col = mock_channels
database.mongo.users_col = mock_users
database.mongo.init_db = AsyncMock()

import database
database.post_drafts_col = mock_post_drafts
database.channels_col = mock_channels
database.users_col = mock_users

async def is_user_premium(user_id):
    return False

database.is_user_premium = is_user_premium

from pyrogram.types import Message, User, Chat, Photo, Video, Animation, CallbackQuery, InlineKeyboardMarkup
from handlers.post_builder import builder_input_handler, builder_menu_callback_handler

class MockClient:
    def __init__(self):
        self.sent_messages = []
        self.sent_media_groups = []
        self.cached_media_sent = []
        self.pinned_messages = []
        self.me = MagicMock()
        self.me.id = 999999
        self.me.username = "test_file_share_bot"

    async def send_message(self, chat_id, text, reply_markup=None, *args, **kwargs):
        self.sent_messages.append({
            "chat_id": chat_id,
            "text": text,
            "reply_markup": reply_markup,
            "args": args,
            "kwargs": kwargs
        })
        msg = MagicMock(spec=Message)
        msg.id = 7777
        return msg

    async def send_cached_media(self, chat_id, file_id, caption=None, reply_markup=None, *args, **kwargs):
        self.cached_media_sent.append({
            "chat_id": chat_id,
            "file_id": file_id,
            "caption": caption,
            "reply_markup": reply_markup
        })
        msg = MagicMock(spec=Message)
        msg.id = 8888
        return msg

    async def send_media_group(self, chat_id, media, *args, **kwargs):
        self.sent_media_groups.append({
            "chat_id": chat_id,
            "media": media
        })
        return [MagicMock(spec=Message)]

    async def pin_chat_message(self, chat_id, message_id, *args, **kwargs):
        self.pinned_messages.append({
            "chat_id": chat_id,
            "message_id": message_id
        })
        return True

    async def get_chat(self, chat_id, *args, **kwargs):
        chat = MagicMock()
        chat.id = chat_id
        chat.linked_chat_id = None
        chat.username = "testchannel"
        return chat

async def run_tests():
    print("Initializing Database Mocks...")
    await mock_post_drafts.delete_many({})
    await mock_channels.delete_many({})

    # Setup channels for Test Users
    user_a_id = 12345
    user_b_id = 67890
    channel_id = -100123

    await database.add_creator_channel(
        user_id=user_a_id,
        channel_id=channel_id,
        title="Channel A",
        username="channel_a"
    )
    await database.add_creator_channel(
        user_id=user_b_id,
        channel_id=-100456,
        title="Channel B",
        username="channel_b"
    )

    client = MockClient()

    # Helpers to create messages
    def create_mock_message(user_id, text="", photo=None, video=None, animation=None, media_group_id=None, caption=None):
        msg = MagicMock(spec=Message)
        msg.id = 1234
        msg.from_user = User(id=user_id, first_name=f"User{user_id}")
        msg.chat = Chat(id=user_id, type=type('ChatType', (), {'value': 'private'})())
        msg.text = text
        msg.caption = caption
        msg.photo = photo
        msg.video = video
        msg.animation = animation
        msg.document = None
        msg.audio = None
        msg.voice = None
        msg.media_group_id = media_group_id
        
        msg.reply_text = AsyncMock(return_value=msg)
        msg.reply_photo = AsyncMock(return_value=msg)
        msg.edit_text = AsyncMock(return_value=msg)
        msg.delete = AsyncMock()
        
        return msg

    async def init_draft_state(user_id, target_channel_id):
        draft = {
            "draft_id": str(user_id),
            "user_id": user_id,
            "channel_id": target_channel_id,
            "media_type": "text",
            "file_id": None,
            "media_files": [],
            "caption": "",
            "buttons": [],
            "reactions": [],
            "reactions_enabled": False,
            "comments": False,
            "comments_enabled": False,
            "caption_above": False,
            "pin": False,
            "pin_message": False,
            "state": "awaiting_media",
            "created_at": datetime.datetime.now(datetime.timezone.utc),
        }
        await database.save_post_draft(user_id, draft)

    # ==========================================
    # Test 1: Photo Draft
    # ==========================================
    print("\n--- Test 1: Photo Draft ---")
    await init_draft_state(user_a_id, channel_id)
    photo_obj = MagicMock(spec=Photo)
    photo_obj.file_id = "photo_file_id_1"
    photo_obj.file_unique_id = "photo_uniq_1"
    photo_obj.file_size = 1000

    msg_photo = create_mock_message(user_id=user_a_id, photo=photo_obj)
    
    await builder_input_handler(client, msg_photo)

    draft_a = await database.get_post_draft(user_a_id)
    assert draft_a is not None, "Draft was not created in database!"
    assert draft_a["media_type"] == "photo", f"Expected photo media_type, got {draft_a['media_type']}"
    assert draft_a["file_id"] == "photo_file_id_1", "file_id mismatch!"
    assert draft_a["state"] == "active", f"Expected state active, got {draft_a['state']}"
    
    assert len(client.sent_messages) > 0, "No menu sent!"
    assert "Post Builder Menu" in client.sent_messages[-1]["text"], "Menu title missing!"
    print("Test 1 Passed: Photo draft created & menu shown.")

    # ==========================================
    # Test 2: Video Draft
    # ==========================================
    print("\n--- Test 2: Video Draft ---")
    await mock_post_drafts.delete_many({})
    client.sent_messages.clear()
    await init_draft_state(user_a_id, channel_id)

    video_obj = MagicMock(spec=Video)
    video_obj.file_id = "video_file_id_2"
    video_obj.file_unique_id = "video_uniq_2"
    video_obj.file_size = 5000
    video_obj.file_name = "test.mp4"

    msg_video = create_mock_message(user_id=user_a_id, video=video_obj)
    await builder_input_handler(client, msg_video)

    draft_a = await database.get_post_draft(user_a_id)
    assert draft_a is not None
    assert draft_a["media_type"] == "video"
    assert draft_a["file_id"] == "video_file_id_2"
    print("Test 2 Passed: Video draft created successfully.")

    # ==========================================
    # Test 3: GIF Draft
    # ==========================================
    print("\n--- Test 3: GIF Draft ---")
    await mock_post_drafts.delete_many({})
    client.sent_messages.clear()
    await init_draft_state(user_a_id, channel_id)

    gif_obj = MagicMock(spec=Animation)
    gif_obj.file_id = "gif_file_id_3"
    gif_obj.file_unique_id = "gif_uniq_3"
    gif_obj.file_size = 2000
    gif_obj.file_name = "test.gif"

    msg_gif = create_mock_message(user_id=user_a_id, animation=gif_obj)
    await builder_input_handler(client, msg_gif)

    draft_a = await database.get_post_draft(user_a_id)
    assert draft_a is not None
    assert draft_a["media_type"] in ["animation", "video", "gif"], f"Got media_type: {draft_a['media_type']}"
    print(f"Test 3 Passed: GIF draft created with media_type {draft_a['media_type']}.")

    # ==========================================
    # Test 4: Album Draft
    # ==========================================
    print("\n--- Test 4: Album Draft ---")
    await mock_post_drafts.delete_many({})
    client.sent_messages.clear()
    await init_draft_state(user_a_id, channel_id)

    photo_item = MagicMock(spec=Photo)
    photo_item.file_id = "photo_album_1"
    photo_item.file_unique_id = "photo_album_uniq_1"
    photo_item.file_size = 1000

    msg_album_1 = create_mock_message(user_id=user_a_id, photo=photo_item, media_group_id="mg_123", caption="Album Caption")
    await builder_input_handler(client, msg_album_1)

    video_item = MagicMock(spec=Video)
    video_item.file_id = "video_album_2"
    video_item.file_unique_id = "video_album_uniq_2"
    video_item.file_size = 2000
    video_item.file_name = "album.mp4"

    msg_album_2 = create_mock_message(user_id=user_a_id, video=video_item, media_group_id="mg_123")
    await builder_input_handler(client, msg_album_2)

    print("Waiting 1.2 seconds for media group menu helper to run...")
    await asyncio.sleep(1.2)

    draft_a = await database.get_post_draft(user_a_id)
    assert draft_a is not None
    assert draft_a["media_type"] == "album"
    assert len(draft_a["media_files"]) == 2, f"Expected 2 media files, got {len(draft_a['media_files'])}"
    assert draft_a["caption"] == "Album Caption", "Caption mismatch"
    print("Test 4 Passed: Album draft parsed and saved as a single draft.")

    # ==========================================
    # Test 5: Caption Editing
    # ==========================================
    print("\n--- Test 5: Caption Editing ---")
    client.sent_messages.clear()

    callback_query = MagicMock(spec=CallbackQuery)
    callback_query.id = "cb_12345"
    callback_query.from_user = User(id=user_a_id, first_name="User12345")
    callback_query.matches = [MagicMock()]
    callback_query.matches[0].group = MagicMock(return_value="caption")
    callback_query.answer = AsyncMock()
    callback_query.message = create_mock_message(user_id=user_a_id)

    await builder_menu_callback_handler(client, callback_query)

    draft_a = await database.get_post_draft(user_a_id)
    assert draft_a["state"] == "awaiting_caption"

    msg_new_caption = create_mock_message(user_id=user_a_id, text="Updated post caption!")
    await builder_input_handler(client, msg_new_caption)

    draft_a = await database.get_post_draft(user_a_id)
    assert draft_a["caption"] == "Updated post caption!"
    assert draft_a["state"] == "active"
    print("Test 5 Passed: Caption updated and builder menu restored.")

    # ==========================================
    # Test 6: Draft Persistence
    # ==========================================
    print("\n--- Test 6: Draft Persistence ---")
    draft_before_restart = await database.get_post_draft(user_a_id)
    assert draft_before_restart is not None, "Draft missing before restart check"
    
    draft_after_restart = await database.get_post_draft(user_a_id)
    assert draft_after_restart["caption"] == "Updated post caption!"
    assert draft_after_restart["media_type"] == "album"
    print("Test 6 Passed: Draft persists in database.")

    # ==========================================
    # Test 7: Cancel
    # ==========================================
    print("\n--- Test 7: Cancel ---")
    callback_query_cancel = MagicMock(spec=CallbackQuery)
    callback_query_cancel.id = "cb_cancel_123"
    callback_query_cancel.from_user = User(id=user_a_id, first_name="User12345")
    callback_query_cancel.matches = [MagicMock()]
    callback_query_cancel.matches[0].group = MagicMock(return_value="cancel")
    callback_query_cancel.answer = AsyncMock()
    callback_query_cancel.message = create_mock_message(user_id=user_a_id)

    await builder_menu_callback_handler(client, callback_query_cancel)

    draft_cancelled = await database.get_post_draft(user_a_id)
    assert draft_cancelled is None, "Draft was not deleted on cancel!"
    print("Test 7 Passed: Cancel deletes the draft successfully.")

    # ==========================================
    # Test 8: Multiple Users
    # ==========================================
    print("\n--- Test 8: Multiple Users ---")
    await init_draft_state(user_a_id, channel_id)
    msg_a = create_mock_message(user_id=user_a_id, photo=photo_obj)
    await builder_input_handler(client, msg_a)

    await init_draft_state(user_b_id, -100456)
    msg_b = create_mock_message(user_id=user_b_id, video=video_obj)
    await builder_input_handler(client, msg_b)

    draft_a = await database.get_post_draft(user_a_id)
    draft_b = await database.get_post_draft(user_b_id)

    assert draft_a is not None
    assert draft_b is not None
    assert draft_a["user_id"] == user_a_id
    assert draft_a["media_type"] == "photo"
    assert draft_b["user_id"] == user_b_id
    assert draft_b["media_type"] == "video"
    print("Test 8 Passed: No interference between multiple users.")

    print("\nAll 8 tests completed successfully!")

if __name__ == "__main__":
    loop.run_until_complete(run_tests())
