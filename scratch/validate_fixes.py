import sys
import os
import asyncio
import datetime

sys.path.insert(0, os.getcwd())

# Reconfigure stdout for UTF-8 to support printing emojis on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Setup mock environmental variables
os.environ["API_ID"] = "12345"
os.environ["API_HASH"] = "abcdef"
os.environ["BOT_TOKEN"] = "12345:abcdef"

# Create event loop
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# Import bot and database
import bot
import database
from pyrogram.types import Message, Chat, User
from pyrogram import Client, ContinuePropagation

# Mock Pyrogram Message & CallbackQuery
class MockMessage:
    def __init__(self, id=1, from_user=None, chat=None, text="", client=None, photo=None, document=None, reply_to_message=None, **kwargs):
        self.id = id
        self.from_user = from_user
        self.chat = chat
        self.text = text
        self.photo = photo
        self.document = document
        self.reply_to_message = reply_to_message
        self._replies = []
        self._propagation_stopped = False
        self._edited_reply_markup = None

    async def reply_text(self, text, *args, **kwargs):
        self._replies.append(text)
        print(f"   [Reply] {text}")
        return self

    async def edit_text(self, text, reply_markup=None, *args, **kwargs):
        self.text = text
        self._replies.append(text)
        print(f"   [Edit Text] {text}")
        return self

    async def reply_photo(self, photo, caption="", *args, **kwargs):
        self._replies.append(caption)
        print(f"   [Reply Photo] {caption}")
        return self

    async def edit_reply_markup(self, reply_markup=None):
        self._edited_reply_markup = reply_markup
        print("   [Edit Reply Markup] Called")

    def stop_propagation(self):
        self._propagation_stopped = True
        print("   [Stop Propagation] Called")

    async def copy(self, chat_id, caption="", reply_markup=None, *args, **kwargs):
        print(f"   [Copy Message] to {chat_id} with caption: {caption}")
        return self

class MockCallbackQuery:
    def __init__(self, query_id, user, data, message=None, matches=None):
        self.id = query_id
        self.from_user = user
        self.data = data
        self.message = message
        self.matches = matches
        self._answers = []
        self._edited_texts = []
        self._edited_reply_markup = None

    async def answer(self, text="", show_alert=False):
        self._answers.append(text)
        if text:
            print(f"   [Callback Answer] {text}")
        return True

    async def edit_message_text(self, text, reply_markup=None, *args, **kwargs):
        self._edited_texts.append(text)
        print(f"   [Callback Edit Message] {text}")
        return self.message

async def test_all():
    await database.init_db()
    
    # Test User ID
    user_id = 987654321
    mock_user = User(id=user_id, first_name="TestUser", username="testuser")
    mock_user._client = bot.app
    mock_chat = Chat(id=user_id, type=type('ChatType', (), {'value': 'private'})())

    # Clean up test user state from DB to avoid test pollution
    await database.users_col.delete_many({"_id": {"$in": [user_id, 111111, 222222]}})
    await database.ad_drafts_col.delete_many({"_id": {"$in": [user_id, 111111, 222222]}})
    from database.mongo import products_col
    await products_col.delete_many({"token": "test_prod_123"})

    # Insert test user to make sure the document exists
    await database.add_user(
        user_id=user_id,
        first_name="TestUser",
        last_name="",
        username="testuser"
    )

    print("\n==================================================")
    print("RUNNING TEST 1: User sends 'Hello' - Verify single reply and stopped propagation")
    print("==================================================")
    msg1 = MockMessage(id=1, from_user=mock_user, chat=mock_chat, text="Hello", client=bot.app)
    
    # Run the text handler directly
    from handlers.start import text_message_handler
    try:
        await text_message_handler(bot.app, msg1)
    except Exception as e:
        print(f"Error in handler: {e}")
    
    assert len(msg1._replies) == 1, f"Expected 1 reply, got {len(msg1._replies)}"
    assert msg1._propagation_stopped is True, "Expected propagation to be stopped"
    print("✅ TEST 1 PASSED: One reply, propagation stopped.")

    print("\n==================================================")
    print("RUNNING TEST 2: Ad draft expiry after 24 hours")
    print("==================================================")
    # Start ad creation
    await database.upsert_ad_draft(user_id, {"step": "awaiting_details", "ad_type": "broadcast"})
    
    # Manually set created_at to 25 hours ago
    stale_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=25)
    await database.ad_drafts_col.update_one({"_id": user_id}, {"$set": {"created_at": stale_time}})
    
    # Run ad creation text handler
    from handlers.ads import ad_create_text_handler
    msg2 = MockMessage(id=2, from_user=mock_user, chat=mock_chat, text="Title | Description | 5.0", client=bot.app)
    
    try:
        await ad_create_text_handler(bot.app, msg2)
    except ContinuePropagation:
        print("   [Bypassed via ContinuePropagation]")
    except Exception as e:
        print(f"   Error: {e}")

    # Verify that draft was deleted
    draft = await database.get_ad_draft(user_id)
    assert draft is None, "Expected expired draft to be deleted"
    assert len(msg2._replies) == 1 and "expired" in msg2._replies[0], f"Expected session expired message, got: {msg2._replies}"
    assert msg2._propagation_stopped is True, "Expected propagation to be stopped for expired draft"
    print("✅ TEST 2 PASSED: Expired draft handled correctly and deleted.")

    print("\n==================================================")
    print("RUNNING TEST 3: User sends /cancel - Clear all temporary states")
    print("==================================================")
    # Set multiple temporary states
    await database.create_batch(user_id)
    await database.upsert_ad_draft(user_id, {"step": "awaiting_details", "ad_type": "broadcast"})
    await database.create_edit_session(user_id, "token123")
    await database.create_password_setting_session(user_id, "token123")
    await database.create_password_entry_session(user_id, "token123")
    await database.users_col.update_one({"_id": user_id}, {"$set": {"state": "catalog_title", "catalog_draft": "some_data"}}, upsert=True)
    
    # Trigger /cancel
    from handlers.upload import batch_cancel_cmd
    msg3 = MockMessage(id=3, from_user=mock_user, chat=mock_chat, text="/cancel", client=bot.app)
    await batch_cancel_cmd(bot.app, msg3)
    
    # Verify everything is cleared
    assert (await database.get_active_batch(user_id)) is None, "Batch not cleared"
    assert (await database.get_ad_draft(user_id)) is None, "Ad draft not cleared"
    assert (await database.get_edit_session(user_id)) is None, "Edit session not cleared"
    assert (await database.get_password_setting_session(user_id)) is None, "Password setting session not cleared"
    assert (await database.get_password_entry_session(user_id)) is None, "Password entry session not cleared"
    
    user_doc = await database.get_user(user_id)
    assert user_doc.get("state") is None, "User state not cleared"
    assert user_doc.get("catalog_draft") is None, "Catalog draft not cleared"
    assert len(msg3._replies) == 1 and msg3._replies[0] == "✅ Current operation cancelled.", f"Expected cancel reply, got: {msg3._replies}"
    print("✅ TEST 3 PASSED: All temporary states cleared, cancel confirmation sent.")

    print("\n==================================================")
    print("RUNNING TEST 4: Successful ad creation removes draft immediately")
    print("==================================================")
    # Start ad creation
    await database.upsert_ad_draft(user_id, {"step": "awaiting_details", "ad_type": "broadcast"})
    
    # Process valid ad creation text
    msg4 = MockMessage(id=4, from_user=mock_user, chat=mock_chat, text="Special Sale | Check out the sale | 2.5", client=bot.app)
    await ad_create_text_handler(bot.app, msg4)
    
    # Verify draft is cleared
    draft = await database.get_ad_draft(user_id)
    assert draft is None, "Expected draft to be cleared immediately after successful creation"
    assert len(msg4._replies) == 1 and "Created!" in msg4._replies[0], f"Expected creation success message, got: {msg4._replies}"
    print("✅ TEST 4 PASSED: Draft removed immediately upon successful creation.")

    print("\n==================================================")
    print("RUNNING TEST 5: Startup cleanup deletes expired drafts & states (> 24 hours)")
    print("==================================================")
    # Create an expired draft (25 hours ago) and a non-expired draft (1 hour ago)
    user_expired = 111111
    user_active = 222222
    stale_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=25)
    active_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
    
    # Mock user document for stale state cleanup
    await database.users_col.update_one(
        {"_id": user_expired}, 
        {"$set": {"last_seen": stale_time, "state": "sh_name"}}, 
        upsert=True
    )
    await database.users_col.update_one(
        {"_id": user_active}, 
        {"$set": {"last_seen": active_time, "state": "sh_name"}}, 
        upsert=True
    )
    
    await database.upsert_ad_draft(user_expired, {"step": "awaiting_details", "ad_type": "broadcast"})
    await database.ad_drafts_col.update_one({"_id": user_expired}, {"$set": {"created_at": stale_time}})
    
    await database.upsert_ad_draft(user_active, {"step": "awaiting_details", "ad_type": "broadcast"})
    await database.ad_drafts_col.update_one({"_id": user_active}, {"$set": {"created_at": active_time}})
    
    # Run startup cleanup
    await database.delete_expired_drafts_and_states()
    
    # Verify expired is deleted, but active is kept
    assert (await database.get_ad_draft(user_expired)) is None, "Expired ad draft not cleaned up"
    assert (await database.get_ad_draft(user_active)) is not None, "Active ad draft was incorrectly cleaned up"
    
    user_expired_doc = await database.get_user(user_expired)
    user_active_doc = await database.get_user(user_active)
    assert user_expired_doc.get("state") is None, "Expired user state not cleaned up"
    assert user_active_doc.get("state") == "sh_name", "Active user state was incorrectly cleaned up"
    
    # Clean up test database records
    await database.ad_drafts_col.delete_many({"_id": {"$in": [user_id, user_expired, user_active]}})
    await database.users_col.delete_many({"_id": {"$in": [user_id, user_expired, user_active]}})
    print("✅ TEST 5 PASSED: Startup cleanup processed correctly.")

    # Patch client send methods to avoid hitting Telegram servers
    sent_messages = []
    async def mock_send_message(chat_id, text, *args, **kwargs):
        sent_messages.append((chat_id, text))
        print(f"   [Send Message] to {chat_id}: {text}")
        return MockMessage(text=text)
    bot.app.send_message = mock_send_message

    async def mock_send_photo(chat_id, photo, caption="", *args, **kwargs):
        sent_messages.append((chat_id, caption))
        print(f"   [Send Photo] to {chat_id}: {caption}")
        return MockMessage(text=caption)
    bot.app.send_photo = mock_send_photo

    async def mock_send_cached_media(chat_id, file_id, caption="", *args, **kwargs):
        sent_messages.append((chat_id, caption))
        print(f"   [Send Cached Media] to {chat_id}: {caption}")
        return MockMessage(text=caption)
    bot.app.send_cached_media = mock_send_cached_media

    print("\n==================================================")
    print("RUNNING TEST 6: Digital Product UPI Checkout")
    print("==================================================")
    from database.products import create_product
    from handlers.marketplace import pay_upi_product_callback_handler
    from bson import ObjectId
    
    # Recreate the test user because Test 5 cleanup deleted it
    await database.add_user(
        user_id=user_id,
        first_name="TestUser",
        last_name="",
        username="testuser"
    )

    # 1. Create a dummy product
    product = await create_product(
        token="test_prod_123",
        name="Amazing Presets",
        description="Lightroom presets bundle",
        price=10,
        owner_id=user_id,
        price_upi=99.0,
        files=[{"file_id": "file_123", "file_name": "presets.zip"}]
    )
    prod_id = str(product["_id"])
    
    # 2. Mock CallbackQuery Matches
    class MatchObj:
        def __init__(self, groups):
            self._groups = groups
        def group(self, i):
            return self._groups[i-1]
            
    matches = [MatchObj([prod_id])]
    
    msg_cb = MockMessage(id=10, from_user=mock_user, chat=mock_chat)
    cb_query = MockCallbackQuery("query_123", mock_user, f"pay_upi_prod_{prod_id}", message=msg_cb, matches=matches)
    
    # Run the UPI checkout callback
    await pay_upi_product_callback_handler(bot.app, cb_query)
    
    # Verify user state is awaiting UPI screenshot
    user_doc = await database.get_user(user_id)
    assert user_doc.get("state", "").startswith("awaiting_upi_screenshot_"), f"User state should start with awaiting_upi_screenshot_, got {user_doc.get('state')}"
    payment_id = user_doc["state"].split("awaiting_upi_screenshot_")[1]
    
    # Verify the pending UPI payment details in database
    payment = await database.get_upi_payment(payment_id)
    assert payment is not None, "Pending payment not found in DB"
    assert payment["plan"] == f"prod_{prod_id}"
    assert payment["amount_inr"] == 99.0
    print("✅ TEST 6 PASSED: Product UPI checkout created payment entry and set user state.")

    print("\n==================================================")
    print("RUNNING TEST 7: UPI Screenshot Validation")
    print("==================================================")
    from handlers.upload import file_uploader
    
    # 1. Send invalid file format (e.g. zip document)
    class MockDocumentZip:
        def __init__(self):
            self.file_id = "doc_zip"
            self.file_name = "hack.zip"
            self.file_size = 1024
            
    msg_invalid = MockMessage(
        id=20, 
        from_user=mock_user, 
        chat=mock_chat, 
        document=MockDocumentZip(), 
        client=bot.app
    )
    await file_uploader(bot.app, msg_invalid)
    assert "Invalid File Format" in msg_invalid._replies[0], f"Expected zip rejection error, got: {msg_invalid._replies}"
    
    # 2. Send valid photo screenshot
    class MockPhoto:
        def __init__(self):
            self.file_id = "photo_123"
            
    msg_valid = MockMessage(
        id=21, 
        from_user=mock_user, 
        chat=mock_chat, 
        photo=MockPhoto(), 
        client=bot.app
    )
    await file_uploader(bot.app, msg_valid)
    
    # Verify screenshot message id is saved in payment
    payment = await database.get_upi_payment(payment_id)
    assert payment["screenshot_msg_id"] == 21, "Screenshot message ID not saved"
    # Verify state was cleared
    user_doc = await database.get_user(user_id)
    assert user_doc.get("state") is None, "State not cleared"
    print("✅ TEST 7 PASSED: Validation rejects ZIP, accepts JPG/PNG, saves MSG ID and clears state.")

    print("\n==================================================")
    print("RUNNING TEST 8: UPI Payment Approval & Product Delivery")
    print("==================================================")
    from handlers.premium import admin_upi_callback_handler
    
    admin_user = User(id=846049642, first_name="Admin", username="admin")
    admin_user._client = bot.app
    matches_approve = [MatchObj(["approve", payment_id])]
    
    msg_approve_cb = MockMessage(id=30, from_user=admin_user, chat=mock_chat)
    cb_approve = MockCallbackQuery("query_approve", admin_user, f"admin_upi_approve_{payment_id}", message=msg_approve_cb, matches=matches_approve)
    
    # Mock is_admin to return True
    original_is_admin = database.is_admin
    async def mock_is_admin(uid, *args):
        return True
    database.is_admin = mock_is_admin
    
    # Clear sent messages tracker
    sent_messages.clear()
    
    # Trigger approval callback
    await admin_upi_callback_handler(bot.app, cb_approve)
    
    # Verify purchase is recorded
    has_purchased = await database.verify_purchase(user_id, product["_id"])
    assert has_purchased is True, "Purchase should be recorded in DB"
    
    # Verify product sales counter incremented
    updated_prod = await database.get_product_by_id(product["_id"])
    assert updated_prod["sales_count"] == 1, f"Sales count should be 1, got {updated_prod['sales_count']}"
    
    # Verify delivery message sent to user
    sent_captions = [msg[1] for msg in sent_messages]
    assert any("Delivering files" in cap for cap in sent_captions), "Expected delivery message"
    assert any("presets.zip" in cap for cap in sent_captions), "Expected file presets.zip in delivery"
    print("✅ TEST 8 PASSED: UPI approval records purchase, increments sales, and delivers files.")

    print("\n==================================================")
    print("RUNNING TEST 9: Prevent Duplicate Product Purchases")
    print("==================================================")
    # Try buying product again - buy_product_callback_handler should detect existing purchase and auto-deliver
    from handlers.marketplace import buy_product_callback_handler
    
    matches_buy = [MatchObj([prod_id])]
    msg_buy = MockMessage(id=40, from_user=mock_user, chat=mock_chat)
    cb_buy = MockCallbackQuery("query_buy", mock_user, f"buy_prod_{prod_id}", message=msg_buy, matches=matches_buy)
    
    sent_messages.clear()
    await buy_product_callback_handler(bot.app, cb_buy)
    
    # Verify duplicate warning alert is sent
    assert any("already purchased" in ans for ans in cb_buy._answers), f"Expected duplicate purchase alert, got: {cb_buy._answers}"
    # Verify files are delivered automatically
    sent_captions = [msg[1] for msg in sent_messages]
    assert any("presets.zip" in cap for cap in sent_captions), "Expected files delivered automatically"
    
    # Clean up product and payment
    from database.mongo import products_col, purchases_col, upi_pending_col
    await products_col.delete_one({"_id": product["_id"]})
    await purchases_col.delete_one({"user_id": user_id, "product_id": product["_id"]})
    await upi_pending_col.delete_one({"_id": ObjectId(payment_id)})
    
    # Restore original is_admin
    database.is_admin = original_is_admin
    print("✅ TEST 9 PASSED: Duplicate purchase correctly prevented with auto-delivery.")
    print("All tests passed successfully!")

if __name__ == "__main__":
    loop.run_until_complete(test_all())
