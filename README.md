# Telegram File Share Bot — Creator Content Delivery Platform

> [!NOTE]
> **Vision**: Build a creator-focused content delivery platform that combines **File Sharing**, **Audience Growth**, **Analytics**, **Subscription Revenue**, and **Digital Commerce** into one scalable Telegram ecosystem capable of generating recurring revenue while remaining compliant with platform policies.

---


## Features

- 📥 **Single File Link Generation:** Send a single file to the bot and instantly receive a shareable permanent link.
- 📦 **Batch Upload Sessions:** Use the `/batch` command to group multiple files (of any type) under a single link. Use `/done` when finished.
- 🔄 **Link permanence (Edit/Append/Delete):** Manage existing links using the `/edit_link` interface:
  - Add/Append files to an existing link (token remains unchanged).
  - Remove files from a batch.
  - Delete shared links permanently.
- 🔒 **Dynamic Force Subscription Check:** Enforce users to join specified Telegram channels/groups before gaining access to files. Includes dynamic channel management (`/add_channel` and `/del_channel`).
- 👥 **Admin Access Control:**
  - dynamic admin promotion/demotion (`/add_admin` and `/del_admin`).
  - Ban/Unban users from using the bot (`/ban` and `/unban`).
- 📢 **Broadcaster:** Send message announcements or copy channel posts to all registered bot users with built-in rate-limiting (`FloodWait` mitigation) and progress tracking.
- 📊 **Usage Analytics:** View real-time statistics (total users, total links shared, and file-specific download counts).

---

## Technical Stack

- **Framework:** Pyrogram v2.x (Asyncio Telegram client)
- **Database:** MongoDB (using Motor, the async driver)
- **Crypto Speedups:** PyAes (fallback cryptography for easy cross-platform deployment)
- **CI/CD:** GitHub Actions for linting and code quality validation

---

## Getting Started

### Prerequisites
- Python 3.11 or greater
- MongoDB Database (Local or MongoDB Atlas)
- Telegram `API_ID` & `API_HASH` (get from [my.telegram.org](https://my.telegram.org))
- Telegram `BOT_TOKEN` (get from [@BotFather](https://t.me/BotFather))

### Installation & Local Setup

1. **Clone the repository:**
   ```bash
   git clone <repository_url>
   cd telegram-file-share-bot
   ```

2. **Initialize Python Virtual Environment:**
   ```bash
   python -m venv .venv
   ```

3. **Activate the Environment:**
   - **Windows (PowerShell):**
     ```powershell
     .\.venv\Scripts\Activate.ps1
     ```
   - **Linux/macOS:**
     ```bash
     source .venv/bin/activate
     ```

4. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

5. **Configure Environment Variables:**
   Copy the example environment template and fill in your details:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and configure:
   - `API_ID` and `API_HASH`
   - `BOT_TOKEN`
   - `MONGO_URI` (e.g., `mongodb://localhost:27017` or Atlas URL)
   - `DB_NAME`
   - `ADMIN_IDS` (comma-separated list of your numeric user ID)

6. **Run the Bot:**
   ```bash
   python main.py
   ```

---

## Command Reference

### Admin Commands

| Command | Description |
|---|---|
| `/batch` | Starts a multi-file batch upload session. |
| `/done` | Ends batch session and generates the permanent link. |
| `/cancel` | Aborts active batch session and clears uploaded files. |
| `/stats` | Shows global statistics (total users, total links). |
| `/broadcast` | Broadcasts text or a replied-to message to all users. |
| `/ban <user_id>` | Ban a user from downloading files. |
| `/unban <user_id>` | Unban a user. |
| `/add_channel <id/username> <link>` | Adds a channel to the force subscription list. |
| `/del_channel <id/username>` | Removes a channel from the force subscription list. |
| `/channels` | Lists all configured force subscription channels. |
| `/add_admin <user_id>` | Promotes a user to dynamic admin. |
| `/del_admin <user_id>` | Demotes a dynamic admin. |
| `/edit_link <code>` | Manages files and settings for a specific share link. |

---

## Modifying Existing Share Links (Link Permanence)

To edit files under an existing share code without changing the link url, use the `/edit_link` command followed by the token code (e.g. `/edit_link ABcDeFgH`):

1. **View Details & Files:**
   ```
   /edit_link ABcDeFgH
   ```
2. **Remove a File from the Batch:**
   ```
   /edit_link ABcDeFgH del 2
   ```
   _(Removes the 2nd file in the list. If it was the only file, the link is deleted.)_
3. **Append a File to the Link:**
   ```
   /edit_link ABcDeFgH add
   ```
   After sending the command, the bot activates an **Append Session**. Simply send the file you want to append. The bot will save it to the existing link and close the append session.
4. **Delete the entire Link:**
   ```
   /edit_link ABcDeFgH delete
   ```
