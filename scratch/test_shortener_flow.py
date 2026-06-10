import asyncio
import time
import urllib.request
import urllib.parse
import urllib.error
import logging

# Set up path to import from project root
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import database
from database import init_db
from database.mongo import shorteners_col, files_col
from database.shorteners import (
    add_shortener,
    get_best_shortener,
)
from utils.web_server import start_web_server, stop_web_server

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestShortener")


async def run_tests():
    logger.info("Initializing database...")
    await init_db()

    # Clear previous test data
    await shorteners_col.delete_many({})
    await files_col.delete_many({"token": "test_token_123"})

    logger.info("1. Adding test shorteners...")
    # Add some test shorteners
    await add_shortener(
        name="Test_GPLinks",
        api_url="http://localhost:8081/mock_shortener",
        api_key="gp_key_test_123",
        weight=2,
        geo_countries=["ALL"],
        cpm=5.0,
    )

    await add_shortener(
        name="Test_ShrinkEarn",
        api_url="http://localhost:8081/mock_shortener",
        api_key="se_key_test_123",
        weight=1,
        geo_countries=["ALL"],
        cpm=3.0,
    )

    await add_shortener(
        name="Test_US_Only",
        api_url="http://localhost:8081/mock_shortener",
        api_key="us_key_test_123",
        weight=5,
        geo_countries=["US"],
        cpm=7.0,
    )

    logger.info("2. Testing Geo-Targeting & Weight Rotation...")
    # Test Geo targeting US: should match US only and ALL.
    # Weight of US is 5, GPLinks is 2, ShrinkEarn is 1. Total weight = 8.
    us_matches = []
    for _ in range(100):
        best = await get_best_shortener(user_country="US")
        if best:
            us_matches.append(best["name"])

    gp_count = us_matches.count("Test_GPLinks")
    se_count = us_matches.count("Test_ShrinkEarn")
    us_count = us_matches.count("Test_US_Only")

    logger.info(
        f"US Target matches count out of 100 trials: US_Only={us_count}, GPLinks={gp_count}, ShrinkEarn={se_count}"
    )
    assert (
        us_count > gp_count
    ), "US only shortener should have higher frequency due to weight=5"

    # Test Geo targeting IN: should match GPLinks (2) and ShrinkEarn (1). Total weight = 3. US_Only should NOT match.
    in_matches = []
    for _ in range(100):
        best = await get_best_shortener(user_country="IN")
        if best:
            in_matches.append(best["name"])

    assert (
        "Test_US_Only" not in in_matches
    ), "US shortener was matched for India geo-target!"
    logger.info("Geo-targeting and weight rotation passed successfully.")

    # 3. Create a test shared link
    logger.info("3. Creating mock shared link...")
    await files_col.insert_one(
        {
            "token": "test_token_123",
            "files": [{"file_id": "file_1", "file_name": "Test File"}],
            "owner_id": 9999,
            "bot_id": None,
            "views": 0,
            "downloads": 0,
            "unique_users": [],
        }
    )

    # Configure local Redirect Server settings
    config.REDIRECT_BASE_URL = "http://localhost:8081"
    config.WEB_SERVER_PORT = 8081

    logger.info("4. Starting local HTTP Redirect Server...")
    start_web_server()
    # Give the thread a moment to spin up
    time.sleep(1)

    try:
        # We need to test the /go endpoint
        # The /go endpoint redirects to the shortener.
        # Since the shortener call uses a dummy key, it will fail, which should trigger the fallback to direct verify link.
        # The direct verify link is: http://localhost:8081/verify/test_token_123/9999?sid=...
        logger.info(
            "5. Testing /go endpoint (should handle shortener API failure gracefully and redirect to /verify)..."
        )

        go_url = "http://localhost:8081/go/test_token_123/9999"

        # Build custom opener to prevent automatic redirect following so we can inspect headers
        class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = urllib.request.build_opener(NoRedirectHandler)

        # We also mock CF headers to pass country
        req = urllib.request.Request(go_url)
        req.add_header(
            "CF-IPCountry", "IN"
        )  # India, so it rotates between GPLinks and ShrinkEarn

        try:
            response = await asyncio.to_thread(opener.open, req)
        except urllib.error.HTTPError as e:
            response = e
        status_code = getattr(response, "status", None) or getattr(
            response, "code", None
        )
        redirect_target = response.headers.get("Location")

        logger.info(f"Response Code: {status_code}")
        logger.info(f"Redirect Target: {redirect_target}")

        assert status_code in [301, 302], f"Expected redirect, got {status_code}"
        assert redirect_target is not None, "Location header not found"
        assert (
            "/verify/test_token_123/9999" in redirect_target
        ), f"Expected verify endpoint redirect fallback, got {redirect_target}"

        # Get the shortener ID (sid) from redirect target
        parsed = urllib.parse.urlparse(redirect_target)
        queries = urllib.parse.parse_qs(parsed.query)
        sid_list = queries.get("sid")
        sid = sid_list[0] if sid_list else None
        assert (
            sid is not None
        ), "Redirect URL does not contain shortener ID (sid) query parameter"

        # Check views stats updated
        file_doc = await database.get_file_link("test_token_123")
        assert file_doc is not None, "File document not found"
        assert (
            file_doc.get("monetization_views", 0) > 0
        ), "File monetization views did not increment"

        # 6. Test /verify endpoint
        logger.info(
            "6. Testing /verify endpoint (should track click/revenue and render HTML skip timer)..."
        )
        verify_url = redirect_target  # This contains the sid

        response_verify = await asyncio.to_thread(urllib.request.urlopen, verify_url)
        status_code_verify = getattr(response_verify, "status", None) or getattr(
            response_verify, "code", None
        )
        assert status_code_verify == 200, f"Expected 200, got {status_code_verify}"

        html_body = response_verify.read().decode("utf-8")
        assert (
            "Unlocking Files" in html_body
        ), "Skip timer page did not render correctly"
        assert (
            "Get Files" in html_body
        ), "Proceed button is missing from Skip timer page"

        # Verify stats updated
        file_doc_after = await database.get_file_link("test_token_123")
        assert file_doc_after is not None, "File document after verify not found"
        assert (
            file_doc_after.get("monetization_clicks", 0) == 1
        ), "File monetization clicks did not increment"
        assert (
            file_doc_after.get("monetization_revenue", 0.0) > 0.0
        ), "File monetization revenue did not update"

        logger.info(
            f"Metrics: Views={file_doc_after.get('monetization_views')}, Clicks={file_doc_after.get('monetization_clicks')}, Revenue=${file_doc_after.get('monetization_revenue')}"
        )
        logger.info(
            "Web endpoints, HTML rendering and analytics metrics verified successfully!"
        )

    finally:
        logger.info("7. Stopping local HTTP Redirect Server...")
        stop_web_server()

        # Clean up database
        await shorteners_col.delete_many(
            {"name": {"$in": ["Test_GPLinks", "Test_ShrinkEarn", "Test_US_Only"]}}
        )
        await files_col.delete_many({"token": "test_token_123"})
        logger.info("Database cleaned up.")

    logger.info("🎉 ALL TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(run_tests())
