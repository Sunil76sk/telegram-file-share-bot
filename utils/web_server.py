from __future__ import annotations

import re
import urllib.parse
import urllib.request
import json
import logging
import threading
import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
import config
import database
from utils.funnel import source_display_name, asset_type_display_name

logger = logging.getLogger(__name__)

# Main event loop reference to run async database operations from HTTP thread
main_loop: asyncio.AbstractEventLoop | None = None
httpd: HTTPServer | None = None


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
                        for key in ["shortenedUrl", "short_url", "shortened_url", "url"]:
                            if key in data:
                                return data[key]
                        if data.get("status") == "error":
                            logger.error(f"Shortener API returned error: {data.get('message')}")
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
            client_ip = self.headers.get("CF-Connecting-IP") or \
                        self.headers.get("X-Forwarded-For") or \
                        self.headers.get("X-Real-IP") or \
                        self.client_address[0]
            
            # If multiple IPs in X-Forwarded-For, pick the first one
            if "," in client_ip:
                client_ip = client_ip.split(",")[0].strip()

            country = self.headers.get("CF-IPCountry") or get_ip_country(client_ip)

            # Get user language code from DB if available to assist geo-targeting
            user_doc = run_async(database.get_user(user_id))
            user_lang = user_doc.get("language_code") if user_doc else None

            # Get best shortener for this route
            bot_id = file_doc.get("bot_id")
            shortener = run_async(database.get_best_shortener(bot_id=bot_id, user_country=country, user_lang=user_lang))

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
            short_link = run_async(generate_short_link(shortener, verify_url_with_shortener))
            
            if not short_link:
                # Fallback to direct verification if API fails
                logger.warning(f"Shortener API failed for {shortener['name']}. Falling back to direct redirect.")
                self.send_response(302)
                self.send_header("Location", verify_url_with_shortener)
                self.end_headers()
                return

            # Log view/impression
            run_async(database.increment_shortener_stats(shortener["_id"], views=1))
            run_async(database.increment_link_monetization_stats(token, views=1))
            run_async(database.track_event(user_id, "shortener_view", token=token, country=country))

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
                    run_async(database.increment_shortener_stats(sid, clicks=1, revenue=revenue))
                    run_async(database.increment_link_monetization_stats(token, clicks=1, revenue=revenue))
                    run_async(database.track_event(user_id, "shortener_click", token=token))

            # Fetch file doc to identify which bot username to redirect back to
            file_doc = run_async(database.get_file_link(token))
            bot_username = None

            if file_doc and file_doc.get("bot_id"):
                sub_bot = run_async(database.sub_bots_col.find_one({"_id": file_doc["bot_id"]}))
                if not sub_bot:
                    # Try lookup by field
                    sub_bot = run_async(database.sub_bots_col.find_one({"bot_token": {"$regex": f"^{file_doc['bot_id']}:"}}))
                if sub_bot:
                    bot_username = sub_bot.get("username")

            if not bot_username:
                # Main bot fallback
                bot_username = config.BOT_TOKEN.split(":")[0]
                # To resolve actual bot username, we can fallback to the client username configured later or default to a place holder.
                # But since we have config, we can fetch username during boot. Let's make sure it is dynamic.
                # In custom_start, we store the bot username globally. Let's check config or store it.
                bot_username = getattr(config, "BOT_USERNAME", "file_share_bot")

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
            active_sponsored = [a for a in active_sponsored if a.get("status") == "active"]

            sponsor = active_sponsored[0] if active_sponsored else None

            if sponsor:
                run_async(database.log_ad_impression(str(sponsor["_id"]), user_id))

            bot_username = getattr(config, "BOT_USERNAME", "file_share_bot")
            tg_redirect = f"https://t.me/{bot_username}?start=unl_{token}"

            html = self.get_sponsored_page_html(
                brand_name=sponsor.get("brand_name", "Our Sponsor") if sponsor else None,
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
            redirect_to = ad.get("button_url", f"https://t.me/{getattr(config, 'BOT_USERNAME', 'file_share_bot')}") if ad else f"https://t.me/{getattr(config, 'BOT_USERNAME', 'file_share_bot')}"
            self.send_response(302)
            self.send_header("Location", redirect_to)
            self.end_headers()
            return

        # 5. Route: /funnel/<campaign_id> - Campaign landing page
        funnel_match = re.match(r"^/funnel/([a-zA-Z0-9_-]+)$", path)
        if funnel_match:
            campaign_id = funnel_match.group(1)
            campaign = run_async(database.get_campaign(campaign_id))
            if not campaign:
                self.send_error(404, "Campaign Not Found")
                return
            src = source_display_name(campaign.get("source", "unknown"))
            at = asset_type_display_name(campaign.get("asset_type", "unknown"))
            invite_link = campaign.get("invite_link", "")
            bot_username = getattr(config, "BOT_USERNAME", "file_share_bot")
            campaign_payload = campaign_id
            if campaign.get("source"):
                campaign_payload += f"&src_{campaign['source']}"
            bot_deep_link = f"https://t.me/{bot_username}?start={campaign_payload}"
            html = self.get_funnel_landing_html(
                title=campaign.get("title", "Exclusive Content"),
                description=campaign.get("description", "Access exclusive files by joining our channel!"),
                source_display=src,
                asset_display=at,
                invite_link=invite_link,
                bot_deep_link=bot_deep_link,
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
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


    def get_sponsored_page_html(self, brand_name: str | None, brand_message: str | None, brand_logo_url: str | None, redirect_url: str, sponsor_ad_id: str | None, user_id: int, token: str) -> str:
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

    def get_funnel_landing_html(self, title: str, description: str, source_display: str, asset_display: str, invite_link: str, bot_deep_link: str) -> str:
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


def start_web_server():
    """Start the web server in a daemon background thread."""
    global main_loop, httpd
    if not config.REDIRECT_BASE_URL:
        logger.info("REDIRECT_BASE_URL is not set. Local redirect web server will not start.")
        return

    main_loop = asyncio.get_running_loop()
    port = config.WEB_SERVER_PORT

    def _serve():
        global httpd
        try:
            httpd = HTTPServer(("", port), RedirectHandler)
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
