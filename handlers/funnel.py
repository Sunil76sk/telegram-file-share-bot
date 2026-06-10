from __future__ import annotations

import logging
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from bot import app
import database
from utils.funnel import (
    source_display_name,
    asset_type_display_name,
    format_funnel_link,
)
from utils.helpers import get_not_subscribed_channels
from utils.delivery import deliver_files

logger = logging.getLogger(__name__)


@app.on_message(filters.command("funnel") & filters.private)
async def funnel_list_cmd(client: Client, message: Message):
    args = message.text.split(None, 1)
    if len(args) > 1:
        campaign_id = args[1].strip()
        await show_campaign_detail(client, message, campaign_id)
        return
    campaigns = await database.get_all_campaigns(active_only=True)
    if not campaigns:
        await message.reply_text(
            "🎯 **Audience Funnels**\n\n"
            "No active campaigns right now. Stay tuned for exclusive content drops!"
        )
        return
    text = "🎯 **Audience Funnels**\n\n"
    text += "Browse our content campaigns. Tap any to access exclusive files:\n\n"
    for c in campaigns:
        src = source_display_name(c.get("source", "unknown"))
        at = asset_type_display_name(c.get("asset_type", "unknown"))
        text += f"• **{c['title']}**\n  {src} · {at}\n  `/funnel {c['_id']}`\n\n"
    await message.reply_text(text)


@app.on_message(filters.command("mycampaigns") & filters.private)
async def my_campaigns_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    is_bot_admin = await database.is_admin(user_id, client)
    if not is_bot_admin:
        await message.reply_text("⛔️ Only admins can manage campaigns.")
        return
    campaigns = await database.get_all_campaigns(active_only=False)
    if not campaigns:
        await message.reply_text("No campaigns yet. Use `/addcampaign` to create one.")
        return
    text = "📊 **All Campaigns**\n\n"
    for c in campaigns:
        status = "🟢 Active" if c.get("active") else "🔴 Inactive"
        text += (
            f"`{c['_id']}`\n"
            f"  Title: {c['title']}\n"
            f"  Source: {c.get('source', '?')}  |  Asset: {c.get('asset_type', '?')}\n"
            f"  Status: {status}  |  Views: {c.get('views', 0)}  |  Conv: {c.get('conversions', 0)}\n\n"
        )
    await message.reply_text(text)


@app.on_message(filters.command("addcampaign") & filters.private)
async def add_campaign_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    is_bot_admin = await database.is_admin(user_id, client)
    if not is_bot_admin:
        await message.reply_text("⛔️ Only admins can manage campaigns.")
        return
    args = message.text.split(None, 7)
    if len(args) < 7:
        await message.reply_text(
            "❌ **Usage:**\n"
            "`/addcampaign [campaign_id] [source] [asset_type] [chat_id] [invite_link] [title] [description]`\n\n"
            "**Sources:** instagram, youtube, movie_review, ott, ai_content\n"
            "**Asset Types:** wallpapers, subtitles, templates, resource_packs, educational\n\n"
            "Campaign IDs must start with `cmp_` (e.g. `cmp_summer_wp`)."
        )
        return
    campaign_id = args[1].strip()
    source = args[2].strip().lower()
    asset_type = args[3].strip().lower()
    chat_id_raw = args[4].strip()
    invite_link = args[5].strip()
    title = args[6].strip()
    description = args[7].strip() if len(args) > 7 else ""
    from utils.funnel import is_valid_campaign_id, is_valid_source, is_valid_asset_type

    if not is_valid_campaign_id(campaign_id):
        await message.reply_text(
            "❌ Campaign ID must start with `cmp_` and be 3-64 chars (letters, numbers, `_`, `-`)."
        )
        return
    if not is_valid_source(source):
        await message.reply_text(
            f"❌ Invalid source `{source}`. Valid: instagram, youtube, movie_review, ott, ai_content."
        )
        return
    if not is_valid_asset_type(asset_type):
        await message.reply_text(
            f"❌ Invalid asset type `{asset_type}`. Valid: wallpapers, subtitles, templates, resource_packs, educational."
        )
        return
    try:
        chat_id = int(chat_id_raw)
    except ValueError:
        chat_id = chat_id_raw
    campaign = await database.create_campaign(
        campaign_id=campaign_id,
        source=source,
        title=title,
        description=description,
        asset_type=asset_type,
        chat_id=chat_id,
        invite_link=invite_link,
    )
    if not campaign:
        await message.reply_text(f"❌ Campaign `{campaign_id}` already exists.")
        return
    bot_me = client.me or await client.get_me()
    funnel_link = format_funnel_link(bot_me.username, campaign_id, source)
    await message.reply_text(
        f"✅ **Campaign Created!**\n\n"
        f"**ID:** `{campaign_id}`\n"
        f"**Title:** {title}\n"
        f"**Source:** {source_display_name(source)}\n"
        f"**Asset:** {asset_type_display_name(asset_type)}\n"
        f"**Channel:** {chat_id}\n\n"
        f"🔗 **Funnel Link:**\n`{funnel_link}`\n\n"
        f"Use this link in your social media posts or bio."
    )


@app.on_message(filters.command("delcampaign") & filters.private)
async def del_campaign_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    is_bot_admin = await database.is_admin(user_id, client)
    if not is_bot_admin:
        await message.reply_text("⛔️ Only admins can manage campaigns.")
        return
    args = message.text.split(None, 1)
    if len(args) < 2:
        await message.reply_text("Usage: `/delcampaign [campaign_id]`")
        return
    campaign_id = args[1].strip()
    deleted = await database.delete_campaign(campaign_id)
    if deleted:
        await message.reply_text(f"🗑 Campaign `{campaign_id}` deleted.")
    else:
        await message.reply_text(f"❌ Campaign `{campaign_id}` not found.")


async def show_campaign_detail(client: Client, message: Message, campaign_id: str):
    campaign = await database.get_campaign(campaign_id)
    if not campaign or not campaign.get("active", True):
        await message.reply_text("❌ Campaign not found or no longer active.")
        return
    await database.increment_campaign_views(campaign_id)
    src = source_display_name(campaign.get("source", "unknown"))
    at = asset_type_display_name(campaign.get("asset_type", "unknown"))
    text = (
        f"🎯 **{campaign['title']}**\n\n"
        f"{campaign.get('description', '')}\n\n"
        f"📱 **Source:** {src}\n"
        f"📂 **Content:** {at}\n\n"
        f"👇 **Access this content by joining our channel below!**"
    )
    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📢 Join Channel", url=campaign.get("invite_link", "")
                )
            ],
            [
                InlineKeyboardButton(
                    "🔄 Verify & Access", callback_data=f"funnel_sub_{campaign_id}"
                )
            ],
        ]
    )
    await message.reply_text(text, reply_markup=buttons)


@app.on_callback_query(filters.regex(r"^funnel_sub_(.+)"))
async def funnel_sub_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    campaign_id = callback_query.matches[0].group(1)
    campaign = await database.get_campaign(campaign_id)
    if not campaign or not campaign.get("active", True):
        await callback_query.answer(
            "❌ This campaign is no longer active.", show_alert=True
        )
        return
    not_joined = await get_not_subscribed_channels(client, user_id)
    if not_joined:
        await callback_query.answer(
            "❌ Please join the channel first!", show_alert=True
        )
        return
    await database.increment_campaign_conversions(campaign_id)
    file_token = campaign.get("file_token")
    if file_token:
        file_doc = await database.get_file_link(file_token)
        if file_doc:
            await callback_query.answer("✅ Access granted! Delivering files...")
            await callback_query.message.delete()
            await deliver_files(client, callback_query.message.chat.id, file_doc)
            return
    bot_me = client.me or await client.get_me()
    funnel_link = format_funnel_link(bot_me.username, campaign_id)
    await callback_query.answer("✅ Channel joined!")
    await callback_query.message.edit_text(
        f"✅ **Access Granted!**\n\n"
        f"**{campaign['title']}**\n\n"
        f"Here is your exclusive bot link to access the files:\n\n"
        f"🔗 `{funnel_link}`\n\n"
        f"Share this with friends to help the community grow! 💪",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📢 Share with Friends",
                        url=f"https://t.me/share/url?url={funnel_link}&text=Check+out+this+exclusive+content!",
                    )
                ],
            ]
        ),
    )
