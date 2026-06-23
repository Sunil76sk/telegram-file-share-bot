from __future__ import annotations

import re
import urllib.parse
import urllib.request
import json
import logging
import threading
import asyncio
import os
import uuid
import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import config
import database

logger = logging.getLogger(__name__)

# Main event loop reference to run async database operations from HTTP thread
main_loop: asyncio.AbstractEventLoop | None = None
httpd: ThreadingHTTPServer | None = None


def run_async(coro):
    """Run a coroutine on the main event loop from a synchronous thread."""
    if main_loop is None:
        raise RuntimeError("Event loop not initialized for web server.")
    future = asyncio.run_coroutine_threadsafe(coro, main_loop)
    return future.result()


def get_ip_country(ip_address: str) -> str:
    """Perform GeoIP lookup using ip-api.com."""
    if ip_address in ["127.0.0.1", "localhost", "::1", ""]:
        return "US"
    try:
        url = f"http://ip-api.com/json/{ip_address}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data.get("status") == "success":
                return data.get("countryCode", "US")
    except Exception as e:
        logger.error(f"GeoIP error for {ip_address}: {e}")
    return "US"


async def generate_short_link(shortener: dict, long_url: str) -> str | None:
    """Call a third-party shortener API to shorten the redirect URL."""
    api_url = shortener["api_url"]
    api_key = shortener["api_key"]

    # URL encode the destination URL
    encoded_url = urllib.parse.quote(long_url)

    # Build standard AdLinkFly API URL
    url = f"{api_url}?api={api_key}&url={encoded_url}"

    def _call():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as response:
                content_type = response.headers.get("Content-Type", "")
                body = response.read().decode("utf-8")

                if "application/json" in content_type or body.strip().startswith("{"):
                    try:
                        data = json.loads(body)
                        for key in [
                            "shortenedUrl",
                            "short_url",
                            "shortened_url",
                            "url",
                        ]:
                            if key in data:
                                return data[key]
                        if data.get("status") == "error":
                            logger.error(
                                f"Shortener API returned error: {data.get('message')}"
                            )
                    except Exception:
                        pass

                if body.strip().startswith("http"):
                    return body.strip()
        except Exception as e:
            logger.error(f"Error calling shortener API ({api_url}): {e}")
        return None

    return await asyncio.to_thread(_call)


class RedirectHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress standard logging to prevent cluttering console
        pass

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)

        # Mock shortener API for testing
        if path == "/mock_shortener":
            long_url = query_params.get("url", ["http://localhost:8080/verify"])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(long_url.encode("utf-8"))
            return

        # 1. Route: /go/<token>/<user_id>
        go_match = re.match(r"^/go/([a-zA-Z0-9_-]+)/(\d+)$", path)
        if go_match:
            token = go_match.group(1)
            user_id = int(go_match.group(2))

            # Fetch file link details
            file_doc = run_async(database.get_file_link(token))
            if not file_doc:
                self.send_error(404, "File Link Not Found")
                return

            # Determine client IP and country
            client_ip = (
                self.headers.get("CF-Connecting-IP")
                or self.headers.get("X-Forwarded-For")
                or self.headers.get("X-Real-IP")
                or self.client_address[0]
            )

            # If multiple IPs in X-Forwarded-For, pick the first one
            if "," in client_ip:
                client_ip = client_ip.split(",")[0].strip()

            country = self.headers.get("CF-IPCountry") or get_ip_country(client_ip)

            # Get user language code from DB if available to assist geo-targeting
            user_doc = run_async(database.get_user(user_id))
            user_lang = user_doc.get("language_code") if user_doc else None

            # Get best shortener for this route
            bot_id = file_doc.get("bot_id")
            shortener = run_async(
                database.get_best_shortener(
                    bot_id=bot_id, user_country=country, user_lang=user_lang
                )
            )

            # Destination to return to after completing ad
            redirect_base = config.REDIRECT_BASE_URL.rstrip("/")
            verify_url = f"{redirect_base}/verify/{token}/{user_id}"

            if not shortener:
                # No active shorteners, redirect directly to verification page
                self.send_response(302)
                self.send_header("Location", verify_url)
                self.end_headers()
                return

            # Append shortener ID to trace click completion
            verify_url_with_shortener = f"{verify_url}?sid={str(shortener['_id'])}"

            # Call API to shorten the link
            short_link = run_async(
                generate_short_link(shortener, verify_url_with_shortener)
            )

            if not short_link:
                # Fallback to direct verification if API fails
                logger.warning(
                    f"Shortener API failed for {shortener['name']}. Falling back to direct redirect."
                )
                self.send_response(302)
                self.send_header("Location", verify_url_with_shortener)
                self.end_headers()
                return

            # Log view/impression
            run_async(database.increment_shortener_stats(shortener["_id"], views=1))
            run_async(database.increment_link_monetization_stats(token, views=1))
            run_async(
                database.track_event(
                    user_id, "shortener_view", token=token, country=country
                )
            )

            # Redirect user to the shortened Ad Link
            self.send_response(302)
            self.send_header("Location", short_link)
            self.end_headers()
            return

        # 2. Route: /verify/<token>/<user_id>
        verify_match = re.match(r"^/verify/([a-zA-Z0-9_-]+)/(\d+)$", path)
        if verify_match:
            token = verify_match.group(1)
            user_id = int(verify_match.group(2))

            # Retrieve shortener ID parameter to credit metrics
            sid = query_params.get("sid", [None])[0]

            # Credit metrics if sid is present
            if sid:
                shortener = run_async(database.get_shortener_by_id(sid))
                if shortener:
                    cpm = shortener.get("cpm", 3.0)
                    revenue = cpm / 1000.0
                    run_async(
                        database.increment_shortener_stats(
                            sid, clicks=1, revenue=revenue
                        )
                    )
                    run_async(
                        database.increment_link_monetization_stats(
                            token, clicks=1, revenue=revenue
                        )
                    )
                    run_async(
                        database.track_event(user_id, "shortener_click", token=token)
                    )

            # Fetch file doc to identify which bot username to redirect back to
            file_doc = run_async(database.get_file_link(token))
            bot_username = None

            if file_doc and file_doc.get("bot_id"):
                sub_bot = run_async(
                    database.sub_bots_col.find_one({"bot_id": file_doc["bot_id"]})
                )
                if not sub_bot:
                    sub_bot = run_async(
                        database.sub_bots_col.find_one(
                            {"bot_token": {"$regex": f"^{file_doc['bot_id']}:"}}
                        )
                    )
                if sub_bot:
                    bot_username = sub_bot.get("username")

            if not bot_username:
                # Main bot fallback
                bot_username = (
                    getattr(config, "BOT_USERNAME", "file_share_bot")
                    or "file_share_bot"
                )

            # Final destination deep link back to Telegram bot
            tg_redirect = f"https://t.me/{bot_username}?start=unl_{token}"

            # Render HTML Skip Timer Page
            html_content = self.get_skip_timer_html(tg_redirect)

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html_content.encode("utf-8"))
            return

        # 3. Route: /sponsored/<token>/<user_id> - Sponsored download page
        sponsored_match = re.match(r"^/sponsored/([a-zA-Z0-9_-]+)/(\d+)$", path)
        if sponsored_match:
            token = sponsored_match.group(1)
            user_id = int(sponsored_match.group(2))

            file_doc = run_async(database.get_file_link(token))
            if not file_doc:
                self.send_error(404, "File Link Not Found")
                return

            # Find active sponsored page ads
            active_sponsored = run_async(database.get_all_ads(ad_type="sponsored_page"))
            active_sponsored = [
                a for a in active_sponsored if a.get("status") == "active"
            ]

            sponsor = active_sponsored[0] if active_sponsored else None

            if sponsor:
                run_async(database.log_ad_impression(str(sponsor["_id"]), user_id))

            bot_username = getattr(config, "BOT_USERNAME", "file_share_bot")
            tg_redirect = f"https://t.me/{bot_username}?start=unl_{token}"

            html = self.get_sponsored_page_html(
                brand_name=(
                    sponsor.get("brand_name", "Our Sponsor") if sponsor else None
                ),
                brand_message=sponsor.get("brand_message", "") if sponsor else None,
                brand_logo_url=sponsor.get("brand_logo_url") if sponsor else None,
                redirect_url=tg_redirect,
                sponsor_ad_id=str(sponsor["_id"]) if sponsor else None,
                user_id=user_id,
                token=token,
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
            return

        # 4. Route: /ad_click/<ad_id>/<user_id> - Track sponsored ad clicks
        ad_click_match = re.match(r"^/ad_click/([a-f0-9]{24})/(\d+)$", path)
        if ad_click_match:
            ad_id = ad_click_match.group(1)
            user_id = int(ad_click_match.group(2))
            run_async(database.log_ad_click(ad_id, user_id))
            # Redirect to the ad's button URL or back to bot
            ad = run_async(database.get_ad(ad_id))
            redirect_to = (
                ad.get(
                    "button_url",
                    f"https://t.me/{getattr(config, 'BOT_USERNAME', 'file_share_bot')}",
                )
                if ad
                else f"https://t.me/{getattr(config, 'BOT_USERNAME', 'file_share_bot')}"
            )
            self.send_response(302)
            self.send_header("Location", redirect_to)
            self.end_headers()
            return

        # 5. Route: /postbuilder
        if path == "/postbuilder":
            html_path = os.path.join("assets", "post_builder.html")
            if not os.path.exists(html_path):
                self.send_error(404, "Post Builder Frontend Not Found")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            with open(html_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.wfile.write(content.encode("utf-8"))
            return

        # 6. Route: /clk/<post_id>/<button_index>
        clk_match = re.match(r"^/clk/([a-f0-9]{24})/(\d+)$", path)
        if clk_match:
            post_id_str = clk_match.group(1)
            btn_idx = int(clk_match.group(2))
            
            post_doc = run_async(database.get_post_history_entry(post_id_str))
            if not post_doc:
                self.send_error(404, "Post Not Found")
                return
            
            buttons = post_doc.get("buttons", [])
            if btn_idx < 0 or btn_idx >= len(buttons):
                self.send_error(404, "Button Not Found")
                return
                
            btn = buttons[btn_idx]
            dest_url = btn.get("url")
            if not dest_url:
                self.send_error(404, "Destination URL Missing")
                return
                
            run_async(database.increment_post_clicks(post_id_str))
            channel_id = post_doc.get("channel_id")
            message_id = post_doc.get("message_id")
            button_text = btn.get("text", "Button")
            run_async(database.log_button_click(0, channel_id, message_id, button_text))
            
            self.send_response(302)
            self.send_header("Location", dest_url)
            self.end_headers()
            return

        # 7. Route: /api/builder/channels
        if path == "/api/builder/channels":
            user_id = int(query_params.get("user_id", [0])[0])
            channels = run_async(database.get_creator_channels(user_id))
            response_data = []
            for ch in channels:
                response_data.append({
                    "channel_id": ch.get("channel_id") or ch.get("_id"),
                    "channel_title": ch.get("channel_title") or ch.get("title") or "Unnamed Channel"
                })
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode("utf-8"))
            return

        # 8. Route: /api/builder/drafts
        if path == "/api/builder/drafts":
            user_id = int(query_params.get("user_id", [0])[0])
            
            async def fetch_drafts():
                cursor = database.drafts_col.find({"user_id": user_id}).sort("updated_at", -1)
                return [d async for d in cursor]
                
            drafts = run_async(fetch_drafts())
            response_data = []
            for d in drafts:
                response_data.append({
                    "_id": str(d["_id"]),
                    "user_id": d.get("user_id"),
                    "updated_at": d.get("updated_at").isoformat() if isinstance(d.get("updated_at"), datetime.datetime) else str(d.get("updated_at")),
                    "post_data": d.get("post_data", {})
                })
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode("utf-8"))
            return

        # 9. Route: /api/builder/image
        if path == "/api/builder/image":
            filename = query_params.get("name", [None])[0]
            if not filename:
                self.send_error(400, "Missing filename")
                return
                
            filename = os.path.basename(filename)
            file_path = os.path.join("temp_uploads", filename)
            
            if not os.path.exists(file_path):
                self.send_error(404, "Image Not Found")
                return
                
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with open(file_path, "rb") as f:
                self.wfile.write(f.read())
            return

        # Fallback
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not Found")

    def get_skip_timer_html(self, redirect_url: str) -> str:
        """HTML content with premium layout and countdown timer."""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Unlocking Your Files...</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-grad: linear-gradient(135deg, #0f0c1b 0%, #1e1136 50%, #0b0813 100%);
            --card-bg: rgba(255, 255, 255, 0.03);
            --card-border: rgba(255, 255, 255, 0.08);
            --accent: linear-gradient(90deg, #8a2be2, #00ffff);
            --accent-glow: rgba(138, 43, 226, 0.4);
            --text-primary: #ffffff;
            --text-secondary: #a5a1b8;
        }}
        
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: 'Outfit', sans-serif;
            background: var(--bg-grad);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            padding: 20px;
        }}

        .background-glow {{
            position: absolute;
            width: 500px;
            height: 500px;
            background: radial-gradient(circle, rgba(138, 43, 226, 0.15) 0%, rgba(0, 0, 0, 0) 70%);
            top: -100px;
            left: -100px;
            z-index: 1;
            pointer-events: none;
        }}
        
        .background-glow-2 {{
            position: absolute;
            width: 600px;
            height: 600px;
            background: radial-gradient(circle, rgba(0, 255, 255, 0.1) 0%, rgba(0, 0, 0, 0) 70%);
            bottom: -150px;
            right: -150px;
            z-index: 1;
            pointer-events: none;
        }}

        .container {{
            position: relative;
            z-index: 10;
            width: 100%;
            max-width: 450px;
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border-radius: 24px;
            padding: 40px 30px;
            text-align: center;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.1);
            animation: fadeIn 0.8s cubic-bezier(0.16, 1, 0.3, 1);
        }}

        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(20px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        .icon-box {{
            width: 72px;
            height: 72px;
            background: rgba(138, 43, 226, 0.1);
            border: 1px solid rgba(138, 43, 226, 0.2);
            border-radius: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 24px;
            box-shadow: 0 8px 16px rgba(0, 0, 0, 0.2);
        }}

        .icon-box svg {{
            width: 36px;
            height: 36px;
            fill: url(#grad);
        }}

        h1 {{
            font-size: 24px;
            font-weight: 800;
            margin-bottom: 12px;
            letter-spacing: -0.5px;
            background: linear-gradient(90deg, #ffffff, #d3cbe7);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        p {{
            font-size: 15px;
            color: var(--text-secondary);
            line-height: 1.6;
            margin-bottom: 30px;
        }}

        .timer-wrapper {{
            position: relative;
            width: 120px;
            height: 120px;
            margin: 0 auto 35px;
        }}

        .timer-svg {{
            transform: rotate(-90deg);
            width: 120px;
            height: 120px;
        }}

        .timer-track {{
            fill: none;
            stroke: rgba(255, 255, 255, 0.04);
            stroke-width: 6;
        }}

        .timer-bar {{
            fill: none;
            stroke: url(#grad);
            stroke-width: 6;
            stroke-linecap: round;
            stroke-dasharray: 339;
            stroke-dashoffset: 0;
            transition: stroke-dashoffset 1s linear;
        }}

        .timer-text {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 32px;
            font-weight: 800;
            background: linear-gradient(90deg, #00ffff, #8a2be2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .btn {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 100%;
            padding: 16px 24px;
            font-size: 16px;
            font-weight: 600;
            color: #0b0813;
            background: var(--accent);
            border: none;
            border-radius: 14px;
            cursor: pointer;
            text-decoration: none;
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            box-shadow: 0 4px 15px var(--accent-glow);
            opacity: 0.5;
            pointer-events: none;
        }}

        .btn.active {{
            opacity: 1;
            pointer-events: auto;
            color: #ffffff;
            background: var(--accent);
        }}

        .btn.active:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(0, 255, 255, 0.4), 0 0 15px rgba(138, 43, 226, 0.4);
        }}

        .btn.active:active {{
            transform: translateY(1px);
        }}

        .footer {{
            margin-top: 24px;
            font-size: 12px;
            color: rgba(165, 161, 184, 0.4);
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }}
    </style>
</head>
<body>
    <div class="background-glow"></div>
    <div class="background-glow-2"></div>
    
    <div class="container">
        <div class="icon-box">
            <svg viewBox="0 0 24 24">
                <defs>
                    <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" style="stop-color:#00ffff;stop-opacity:1" />
                        <stop offset="100%" style="stop-color:#8a2be2;stop-opacity:1" />
                    </linearGradient>
                </defs>
                <path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"/>
            </svg>
        </div>
        
        <h1>Unlocking Files</h1>
        <p>Please wait a moment while we securely prepare your file access link...</p>
        
        <div class="timer-wrapper">
            <svg class="timer-svg" viewBox="0 0 120 120">
                <circle class="timer-track" cx="60" cy="60" r="54"></circle>
                <circle id="timer-bar" class="timer-bar" cx="60" cy="60" r="54"></circle>
            </svg>
            <div id="timer-text" class="timer-text">5</div>
        </div>
        
        <a href="{redirect_url}" id="proceed-btn" class="btn">Please Wait...</a>
        
        <div class="footer">Securely Verified</div>
    </div>

    <script>
        const duration = 5;
        let timeLeft = duration;
        const timerText = document.getElementById('timer-text');
        const timerBar = document.getElementById('timer-bar');
        const proceedBtn = document.getElementById('proceed-btn');
        
        const strokeDasharray = 339; // 2 * Math.PI * r (r=54)

        const interval = setInterval(() => {{
            timeLeft--;
            if (timeLeft <= 0) {{
                clearInterval(interval);
                timerText.textContent = "✓";
                timerBar.style.strokeDashoffset = strokeDasharray;
                
                proceedBtn.textContent = "Get Files ⚡";
                proceedBtn.classList.add('active');
                
                // Auto redirect
                setTimeout(() => {{
                    window.location.href = "{redirect_url}";
                }}, 800);
            }} else {{
                timerText.textContent = timeLeft;
                const offset = strokeDasharray - (strokeDasharray * (duration - timeLeft) / duration);
                timerBar.style.strokeDashoffset = offset;
            }}
        }}, 1000);
    </script>
</body>
</html>"""

    def get_sponsored_page_html(
        self,
        brand_name: str | None,
        brand_message: str | None,
        brand_logo_url: str | None,
        redirect_url: str,
        sponsor_ad_id: str | None,
        user_id: int,
        token: str,
    ) -> str:
        brand_section = ""
        if brand_name:
            brand_section = f"""
            <div class="sponsor-badge">
                <span class="sponsor-label">Sponsored</span>
                <span class="sponsor-name">{brand_name}</span>
            </div>
            """
        if brand_logo_url:
            brand_section = f"""
            <div class="sponsor-badge">
                <span class="sponsor-label">Sponsored by</span>
                <img src="{brand_logo_url}" alt="{brand_name or 'Sponsor'}" class="sponsor-logo">
            </div>
            """

        click_tracker = ""
        if sponsor_ad_id:
            click_tracker = f"https://{getattr(config, 'REDIRECT_BASE_URL', 'localhost').rstrip('/')}/ad_click/{sponsor_ad_id}/{user_id}"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>File Access - Sponsored by {brand_name or 'Our Partner'}</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Outfit', sans-serif;
            background: linear-gradient(135deg, #0f0c1b 0%, #1e1136 50%, #0b0813 100%);
            color: #ffffff;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .glow-1 {{
            position: fixed; width: 500px; height: 500px;
            background: radial-gradient(circle, rgba(138, 43, 226, 0.15) 0%, transparent 70%);
            top: -100px; left: -100px; pointer-events: none;
        }}
        .glow-2 {{
            position: fixed; width: 600px; height: 600px;
            background: radial-gradient(circle, rgba(0, 255, 255, 0.1) 0%, transparent 70%);
            bottom: -150px; right: -150px; pointer-events: none;
        }}
        .card {{
            position: relative; z-index: 10;
            width: 100%; max-width: 480px;
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.08);
            backdrop-filter: blur(20px);
            border-radius: 24px;
            padding: 40px 30px;
            text-align: center;
            box-shadow: 0 20px 40px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.1);
            animation: fadeUp 0.8s cubic-bezier(0.16,1,0.3,1);
        }}
        @keyframes fadeUp {{ from {{ opacity: 0; transform: translateY(20px); }} to {{ opacity: 1; transform: translateY(0); }} }}
        .sponsor-badge {{
            display: inline-flex; align-items: center; gap: 10px;
            padding: 6px 16px;
            border-radius: 20px;
            font-size: 13px; font-weight: 600;
            background: rgba(138,43,226,0.15);
            border: 1px solid rgba(138,43,226,0.3);
            margin-bottom: 20px;
        }}
        .sponsor-label {{ color: #a5a1b8; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; }}
        .sponsor-name {{ color: #fff; }}
        .sponsor-logo {{ height: 24px; border-radius: 4px; }}
        h1 {{
            font-size: 28px; font-weight: 800; margin-bottom: 12px;
            background: linear-gradient(90deg, #ffffff, #d3cbe7);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            letter-spacing: -0.5px;
        }}
        .brand-message {{
            font-size: 15px; color: #a5a1b8; line-height: 1.7; margin-bottom: 30px;
        }}
        .icon-box {{
            width: 72px; height: 72px;
            background: rgba(138, 43, 226, 0.1);
            border: 1px solid rgba(138, 43, 226, 0.2);
            border-radius: 20px;
            display: flex; align-items: center; justify-content: center;
            margin: 0 auto 24px;
        }}
        .icon-box svg {{ width: 36px; height: 36px; fill: #8a2be2; }}
        .btn {{
            display: inline-flex; align-items: center; justify-content: center;
            width: 100%; padding: 16px 24px;
            font-size: 16px; font-weight: 600;
            color: #ffffff;
            background: linear-gradient(90deg, #8a2be2, #00ffff);
            border: none; border-radius: 14px;
            cursor: pointer; text-decoration: none;
            transition: all 0.3s cubic-bezier(0.25,0.8,0.25,1);
            box-shadow: 0 4px 20px rgba(138,43,226,0.3);
            margin-bottom: 12px;
        }}
        .btn:hover {{ transform: translateY(-2px); box-shadow: 0 8px 30px rgba(0,255,255,0.3); }}
        .btn-secondary {{
            background: rgba(255,255,255,0.06);
            box-shadow: none; color: #a5a1b8;
        }}
        .btn-secondary:hover {{ background: rgba(255,255,255,0.1); color: #fff; }}
        .footer {{ margin-top: 24px; font-size: 12px; color: rgba(165,161,184,0.3); letter-spacing: 0.5px; text-transform: uppercase; }}
    </style>
</head>
<body>
    <div class="glow-1"></div>
    <div class="glow-2"></div>
    <div class="card">
        {brand_section}
        <div class="icon-box">
            <svg viewBox="0 0 24 24"><path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"/></svg>
        </div>
        <h1>Your Files Are Ready</h1>
        <p class="brand-message">{brand_message or 'This content is brought to you by our sponsors.'}</p>
        <a href="{click_tracker or redirect_url}" id="get-files-btn" class="btn">Get Files ⚡</a>
        <div class="footer">Powered by {brand_name or 'Our Sponsors'}</div>
    </div>
</body>
</html>"""

    def get_funnel_landing_html(
        self,
        title: str,
        description: str,
        source_display: str,
        asset_display: str,
        invite_link: str,
        bot_deep_link: str,
    ) -> str:
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Exclusive Content</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Outfit', sans-serif;
            background: linear-gradient(135deg, #0f0c1b 0%, #1e1136 50%, #0b0813 100%);
            color: #ffffff;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .glow-1 {{
            position: fixed; width: 500px; height: 500px;
            background: radial-gradient(circle, rgba(138, 43, 226, 0.15) 0%, transparent 70%);
            top: -100px; left: -100px; pointer-events: none;
        }}
        .glow-2 {{
            position: fixed; width: 600px; height: 600px;
            background: radial-gradient(circle, rgba(0, 255, 255, 0.1) 0%, transparent 70%);
            bottom: -150px; right: -150px; pointer-events: none;
        }}
        .card {{
            position: relative; z-index: 10;
            width: 100%; max-width: 480px;
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.08);
            backdrop-filter: blur(20px);
            border-radius: 24px;
            padding: 40px 30px;
            text-align: center;
            box-shadow: 0 20px 40px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.1);
            animation: fadeUp 0.8s cubic-bezier(0.16,1,0.3,1);
        }}
        @keyframes fadeUp {{ from {{ opacity: 0; transform: translateY(20px); }} to {{ opacity: 1; transform: translateY(0); }} }}
        .badge {{
            display: inline-block;
            padding: 6px 16px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
            background: rgba(138,43,226,0.15);
            border: 1px solid rgba(138,43,226,0.3);
            margin-bottom: 20px;
        }}
        h1 {{
            font-size: 28px; font-weight: 800; margin-bottom: 12px;
            background: linear-gradient(90deg, #ffffff, #d3cbe7);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            letter-spacing: -0.5px;
        }}
        .desc {{
            font-size: 15px; color: #a5a1b8; line-height: 1.7; margin-bottom: 24px;
        }}
        .meta {{ display: flex; gap: 12px; justify-content: center; margin-bottom: 30px; flex-wrap: wrap; }}
        .meta-item {{
            padding: 8px 16px;
            background: rgba(255,255,255,0.04);
            border-radius: 10px;
            font-size: 13px;
            color: #a5a1b8;
        }}
        .steps {{ text-align: left; margin-bottom: 30px; }}
        .step {{
            display: flex; align-items: flex-start; gap: 14px;
            padding: 14px 16px;
            background: rgba(255,255,255,0.02);
            border-radius: 12px;
            margin-bottom: 10px;
            border: 1px solid rgba(255,255,255,0.04);
        }}
        .step-num {{
            width: 28px; height: 28px; min-width: 28px;
            border-radius: 50%;
            background: linear-gradient(90deg, #8a2be2, #00ffff);
            display: flex; align-items: center; justify-content: center;
            font-size: 13px; font-weight: 700; color: #0b0813;
        }}
        .step-text {{ font-size: 14px; color: #d3cbe7; line-height: 1.5; }}
        .btn {{
            display: inline-flex; align-items: center; justify-content: center;
            width: 100%; padding: 16px 24px;
            font-size: 16px; font-weight: 600;
            color: #ffffff;
            background: linear-gradient(90deg, #8a2be2, #00ffff);
            border: none; border-radius: 14px;
            cursor: pointer; text-decoration: none;
            transition: all 0.3s cubic-bezier(0.25,0.8,0.25,1);
            box-shadow: 0 4px 20px rgba(138,43,226,0.3);
            margin-bottom: 12px;
        }}
        .btn:hover {{ transform: translateY(-2px); box-shadow: 0 8px 30px rgba(0,255,255,0.3), 0 0 15px rgba(138,43,226,0.3); }}
        .btn-secondary {{
            background: rgba(255,255,255,0.06);
            box-shadow: none;
            color: #a5a1b8;
        }}
        .btn-secondary:hover {{ background: rgba(255,255,255,0.1); color: #fff; }}
        .footer {{ margin-top: 24px; font-size: 12px; color: rgba(165,161,184,0.3); letter-spacing: 0.5px; text-transform: uppercase; }}
    </style>
</head>
<body>
    <div class="glow-1"></div>
    <div class="glow-2"></div>
    <div class="card">
        <div class="badge">{asset_display}</div>
        <h1>{title}</h1>
        <p class="desc">{description}</p>
        <div class="meta">
            <span class="meta-item">{source_display}</span>
            <span class="meta-item">{asset_display}</span>
        </div>
        <div class="steps">
            <div class="step">
                <div class="step-num">1</div>
                <div class="step-text">Join our Telegram channel to unlock access</div>
            </div>
            <div class="step">
                <div class="step-num">2</div>
                <div class="step-text">Click "Verify" in the bot to confirm membership</div>
            </div>
            <div class="step">
                <div class="step-num">3</div>
                <div class="step-text">Download your exclusive {asset_display.lower()} instantly</div>
            </div>
        </div>
        <a href="{invite_link}" class="btn" target="_blank">📢 Join Channel First</a>
        <a href="{bot_deep_link}" class="btn btn-secondary">🤖 Already Joined? Open Bot</a>
        <div class="footer">Exclusive Content Drop</div>
    </div>
</body>
</html>"""

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_DELETE(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)
        
        if path == "/api/builder/draft":
            user_id = int(query_params.get("user_id", [0])[0])
            draft_id_str = query_params.get("draft_id", [None])[0]
            
            if not draft_id_str:
                self.send_error(400, "Missing draft_id")
                return
                
            try:
                from bson import ObjectId
                res = run_async(database.drafts_col.delete_one({"_id": ObjectId(draft_id_str), "user_id": user_id}))
                success = res.deleted_count > 0
            except Exception as e:
                logger.error(f"Error deleting draft: {e}")
                success = False
                
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success}).encode("utf-8"))
            return
            
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not Found")

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)
        
        content_length = int(self.headers.get('Content-Length', 0))
        post_data_bytes = self.rfile.read(content_length)
        
        content_type = self.headers.get('Content-Type', '')
        
        # 1. API: /api/builder/upload (multipart/form-data)
        if path == "/api/builder/upload":
            if "multipart/form-data" not in content_type:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "message": "Content-Type must be multipart/form-data"}).encode("utf-8"))
                return
                
            try:
                boundary = content_type.split("boundary=")[1].encode()
                parts = post_data_bytes.split(b'--' + boundary)
                
                filename = None
                file_bytes = None
                
                for part in parts:
                    if not part or part == b'--\r\n' or part == b'\r\n' or part == b'--':
                        continue
                    if b'\r\n\r\n' in part:
                        header_part, body_part = part.split(b'\r\n\r\n', 1)
                        if body_part.endswith(b'\r\n'):
                            body_part = body_part[:-2]
                        
                        header_str = header_part.decode('utf-8', errors='ignore')
                        if 'name="file"' in header_str:
                            fn_match = re.search(r'filename="([^"]+)"', header_str)
                            if fn_match:
                                filename = fn_match.group(1)
                            file_bytes = body_part
                            
                if not file_bytes:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(json.dumps({"success": False, "message": "No file uploaded"}).encode("utf-8"))
                    return
                    
                ext = os.path.splitext(filename)[1] or ".jpg"
                unique_filename = f"{uuid.uuid4()}{ext}"
                
                os.makedirs("temp_uploads", exist_ok=True)
                output_path = os.path.join("temp_uploads", unique_filename)
                with open(output_path, "wb") as f:
                    f.write(file_bytes)
                    
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "filename": unique_filename}).encode("utf-8"))
                return
            except Exception as e:
                logger.error(f"Upload error: {e}")
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "message": str(e)}).encode("utf-8"))
                return

        # Decode standard JSON body for other endpoints
        try:
            data = json.loads(post_data_bytes.decode('utf-8'))
        except Exception:
            data = {}

        # 2. API: /api/builder/fit
        if path == "/api/builder/fit":
            filename = data.get("filename")
            ratio = data.get("ratio")
            style = data.get("style", "blur")
            
            if not filename or not ratio:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "message": "Missing required fields"}).encode("utf-8"))
                return
                
            input_path = os.path.join("temp_uploads", os.path.basename(filename))
            if not os.path.exists(input_path):
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "message": "Original image not found"}).encode("utf-8"))
                return
                
            with open(input_path, "rb") as f:
                image_bytes = f.read()
                
            from utils.image_converter import ImageConverter
            converter = ImageConverter()
            try:
                fitted_bytes = run_async(converter.fit_image(image_bytes, ratio, style))
                fitted_filename = f"fitted_{ratio.replace(':', '_')}_{style}_{os.path.basename(filename)}"
                output_path = os.path.join("temp_uploads", fitted_filename)
                with open(output_path, "wb") as f:
                    f.write(fitted_bytes)
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "filename": fitted_filename}).encode("utf-8"))
                return
            except Exception as e:
                logger.error(f"Error fitting image: {e}")
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "message": str(e)}).encode("utf-8"))
                return

        # 3. API: /api/builder/draft
        if path == "/api/builder/draft":
            user_id = data.get("user_id")
            draft_id_str = data.get("draft_id")
            post_data = data.get("post_data", {})
            
            if not user_id:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "message": "Missing user_id"}).encode("utf-8"))
                return
                
            try:
                from bson import ObjectId
                doc = {
                    "user_id": user_id,
                    "post_data": post_data,
                    "updated_at": datetime.datetime.now(datetime.timezone.utc)
                }
                if draft_id_str:
                    res = run_async(database.drafts_col.update_one(
                        {"_id": ObjectId(draft_id_str), "user_id": user_id},
                        {"$set": doc}
                    ))
                    success = res.modified_count > 0 or res.matched_count > 0
                else:
                    res = run_async(database.drafts_col.insert_one(doc))
                    success = True
            except Exception as e:
                logger.error(f"Error saving draft: {e}")
                success = False
                
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success}).encode("utf-8"))
            return

        # 4. API: /api/builder/publish
        if path == "/api/builder/publish":
            user_id = data.get("user_id")
            channel_ids = data.get("channel_ids", [])
            caption = data.get("caption", "")
            image_path = data.get("image_path")
            buttons = data.get("buttons", [])
            
            if not user_id or not channel_ids:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "message": "Missing user_id or channel_ids"}).encode("utf-8"))
                return
                
            from bot import app
            
            async def perform_publish():
                success_count = 0
                for channel_id in channel_ids:
                    try:
                        from bson import ObjectId
                        post_id = ObjectId()
                        
                        redirect_base = config.REDIRECT_BASE_URL.rstrip("/")
                        rewritten_buttons = []
                        for idx, btn in enumerate(buttons):
                            track_url = f"{redirect_base}/clk/{str(post_id)}/{idx}"
                            rewritten_buttons.append({
                                "text": btn["text"],
                                "url": track_url
                            })
                            
                        from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                        keyboard = []
                        for btn in rewritten_buttons:
                            keyboard.append([InlineKeyboardButton(text=btn["text"], url=btn["url"])])
                        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
                        
                        sent_msg = None
                        if image_path:
                            full_image_path = os.path.join("temp_uploads", image_path)
                            sent_msg = await app.send_photo(
                                chat_id=channel_id,
                                photo=full_image_path,
                                caption=caption,
                                reply_markup=reply_markup
                            )
                        else:
                            sent_msg = await app.send_message(
                                chat_id=channel_id,
                                text=caption,
                                reply_markup=reply_markup
                            )
                            
                        if sent_msg:
                            doc = {
                                "_id": post_id,
                                "channel_id": channel_id,
                                "user_id": user_id,
                                "message_id": sent_msg.id,
                                "media_type": "photo" if image_path else "text",
                                "caption": caption,
                                "buttons": buttons,
                                "reactions": [],
                                "comments": False,
                                "pin": False,
                                "caption_above": False,
                                "scheduled": False,
                                "repost": False,
                                "posted_at": datetime.datetime.now(datetime.timezone.utc),
                                "views": 0,
                                "clicks": 0,
                            }
                            await database.CHANNEL_POST_HISTORY_COL.insert_one(doc)
                            await database.increment_channel_stat(channel_id, "posts", 1)
                            success_count += 1
                    except Exception as ex:
                        logger.error(f"Error publishing to channel {channel_id}: {ex}")
                return success_count > 0
                
            success = run_async(perform_publish())
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success}).encode("utf-8"))
            return

        # 5. API: /api/builder/schedule
        if path == "/api/builder/schedule":
            user_id = data.get("user_id")
            channel_ids = data.get("channel_ids", [])
            title = data.get("title")
            caption = data.get("caption", "")
            image_path = data.get("image_path")
            buttons = data.get("buttons", [])
            publish_time_str = data.get("publish_time")
            
            if not user_id or not channel_ids or not publish_time_str:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "message": "Missing required fields"}).encode("utf-8"))
                return
                
            scheduled_time = datetime.datetime.fromisoformat(publish_time_str.replace("Z", "+00:00"))
            
            async def perform_schedule():
                for channel_id in channel_ids:
                    await database.create_scheduled_post(
                        user_id=user_id,
                        channel_id=channel_id,
                        media_type="photo" if image_path else "text",
                        file_id=None,
                        caption=caption,
                        buttons=buttons,
                        scheduled_time=scheduled_time,
                        poster_url=image_path
                    )
                return True
                
            success = run_async(perform_schedule())
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success}).encode("utf-8"))
            return

        # 6. API: /api/builder/repost
        if path == "/api/builder/repost":
            user_id = data.get("user_id")
            channel_ids = data.get("channel_ids", [])
            title = data.get("title")
            caption = data.get("caption", "")
            image_path = data.get("image_path")
            buttons = data.get("buttons", [])
            interval_minutes = data.get("interval_minutes")
            delete_old = data.get("delete_old", True)
            
            if not user_id or not channel_ids or not interval_minutes:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "message": "Missing required fields"}).encode("utf-8"))
                return
                
            async def perform_repost_schedule():
                for channel_id in channel_ids:
                    await database.create_repost_job(
                        user_id=user_id,
                        channel_id=channel_id,
                        media_type="photo" if image_path else "text",
                        file_id=None,
                        caption=caption,
                        buttons=buttons,
                        repost_interval=interval_minutes,
                        delete_gap=0,
                        poster_url=image_path,
                        delete_old=delete_old
                    )
                return True
                
            success = run_async(perform_repost_schedule())
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not Found")


def start_web_server():
    """Start the web server in a daemon background thread."""
    global main_loop, httpd
    if not config.REDIRECT_BASE_URL:
        logger.info(
            "REDIRECT_BASE_URL is not set. Local redirect web server will not start."
        )
        return

    main_loop = asyncio.get_running_loop()
    port = config.WEB_SERVER_PORT

    def _serve():
        global httpd
        try:
            httpd = ThreadingHTTPServer(("", port), RedirectHandler)
            logger.info(f"Local Redirect Server started on port {port}.")
            httpd.serve_forever()
        except Exception as e:
            logger.error(f"Failed to start local redirect server on port {port}: {e}")

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()


def stop_web_server():
    """Shutdown the web server."""
    global httpd
    if httpd:
        httpd.shutdown()
        logger.info("Local Redirect Server stopped.")
