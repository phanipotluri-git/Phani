#!/usr/bin/env python3
"""
TTD Sr. Citizen Darshan booking assistant.

Run this on YOUR OWN computer (not in a restricted sandbox) — it needs real
network access to ttdevasthanams.ap.gov.in and opens a real, visible browser
window so you can log in and receive your OTP.

What this script automates, and what it deliberately leaves to you:

  1. Log in (mobile + OTP)                          -> MANUAL (your OTP)
  2. Open Sr. Citizen Darshan booking flow           -> automatic
  3. Wait through the virtual queue                  -> automatic (polls for you)
  4. Select Category=Senior Citizen, Age, Spouse     -> automatic
  5. Pick date + confirm time slot on the calendar   -> MANUAL (on purpose —
     this is the fair, first-come part of a scarce quota that many other
     senior citizens are also waiting on; it should not be automated)
  6. Fill Pilgrim Details + upload ID photo          -> automatic
  7. Review and click the final Submit/Book button   -> MANUAL (on purpose —
     this script has not been tested against the live site, since the
     environment it was written in has no network access to this domain;
     verify everything before you commit to a real booking)

Setup:
    pip install playwright
    playwright install chromium

Usage:
    python ttd_booking_assist.py [path/to/ttd_config.json]

ttd_config.json is produced by TTD.html (the prefill page) — it is never
committed to git (see .gitignore) and never leaves your machine except to
be read by this script.

IMPORTANT: the selectors below are written from screenshots of the site,
not its live HTML (this environment could not reach the domain to inspect
it directly). They use resilient, text/role-based locators where possible,
but you may need to nudge a selector or two on first run — the script
prints what it's doing at each step so it's easy to see where to adjust.
"""

import base64
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

DASHBOARD_URL = "https://ttdevasthanams.ap.gov.in/home/dashboard"
QUEUE_POLL_TIMEOUT_MS = 30 * 60 * 1000  # 30 minutes max wait in the virtual queue
QUEUE_POLL_INTERVAL_S = 5


def load_config(path: Path) -> dict:
    if not path.exists():
        sys.exit(
            f"Config file not found: {path}\n"
            f"Fill out TTD.html, click 'Download config', and place the "
            f"resulting ttd_config.json next to this script (or pass its path)."
        )
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def pause(message: str):
    print(f"\n>>> {message}")
    input(">>> Press Enter here once done... ")


def wait_for_login(page):
    print("\nOpening the TTD dashboard. Please log in manually (mobile number + OTP).")
    page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
    pause("Log in in the browser window, then wait until you see the dashboard.")


def open_sr_citizen_flow(page):
    print("Looking for the 'Differently Abled / Sr. Citizen Darshan' tile...")
    candidates = [
        page.get_by_text("Differently Abled/Sr.Citizen Darshan", exact=False),
        page.get_by_text("Sr. Citizen", exact=False),
        page.get_by_text("Sr.Citizen", exact=False),
    ]
    for locator in candidates:
        try:
            if locator.count() > 0:
                locator.first.click()
                print("Clicked the Sr. Citizen Darshan tile.")
                return
        except Exception:
            continue
    pause(
        "Could not find the 'Differently Abled/Sr.Citizen Darshan' tile "
        "automatically. Please click it yourself."
    )


def wait_through_queue(page):
    print("Waiting through the virtual queue (this can take a while)...")
    deadline = time.time() + QUEUE_POLL_TIMEOUT_MS / 1000
    while time.time() < deadline:
        try:
            if page.get_by_text("Category", exact=False).count() > 0:
                print("Queue cleared — slot booking form is up.")
                return
        except Exception:
            pass
        try:
            if page.get_by_text("virtual queue", exact=False).count() == 0 and \
               "slot-booking" in page.url:
                print("Slot booking page reached.")
                return
        except Exception:
            pass
        time.sleep(QUEUE_POLL_INTERVAL_S)
    pause(
        "Timed out waiting for the queue after 30 minutes. Check the browser "
        "window — if you're through, press Enter to continue."
    )


def fill_category_age_spouse(page, cfg):
    pilgrim = cfg["pilgrim"]
    accompany = cfg.get("accompany_spouse", "No")

    print("Selecting Category = Senior Citizen...")
    try:
        page.get_by_label("Category", exact=False).select_option(label="Senior Citizen")
    except Exception:
        try:
            page.get_by_text("Category", exact=False).click()
            page.get_by_text("Senior Citizen", exact=True).click()
        except Exception:
            pause("Could not auto-select Category. Please choose 'Senior Citizen' yourself.")

    print(f"Filling Age = {pilgrim['age']}...")
    try:
        page.get_by_label("Age", exact=False).first.fill(str(pilgrim["age"]))
    except Exception:
        pause(f"Could not auto-fill Age. Please enter {pilgrim['age']} yourself.")

    print(f"Setting 'Accompany with the Spouse' = {accompany}...")
    # The site's dropdown options are ALL CAPS ("YES"/"NO"), but the config
    # value from TTD.html is Title Case ("Yes"/"No") -- try both.
    for candidate in (accompany, accompany.upper(), accompany.lower()):
        try:
            page.get_by_label("Accompany", exact=False).select_option(label=candidate)
            break
        except Exception:
            continue
    else:
        try:
            page.get_by_text("Accompany with the Spouse", exact=False).click()
            page.get_by_text(accompany, exact=False).click()
        except Exception:
            pause(f"Could not auto-select spouse option. Please choose '{accompany}' yourself.")


def fill_pilgrim_details(page, person: dict, s_no: int):
    label = "yours" if s_no == 1 else "your spouse's"
    print(f"Filling Pilgrim Details ({label})...")
    # If the form pre-renders all S.No blocks at once (common in reactive
    # forms), ".last" would resolve to the same final block on every call,
    # silently overwriting it instead of filling each pilgrim's own block.
    # Index by position (nth) instead, 0-based.
    idx = s_no - 1
    try:
        page.get_by_label("Pilgrim Name", exact=False).nth(idx).fill(person["name"])
        page.get_by_label("Age", exact=False).nth(idx).fill(str(person["age"]))
        page.get_by_label("Gender", exact=False).nth(idx).select_option(label=person["gender"])
        page.get_by_label("Photo ID Proof", exact=False).nth(idx).select_option(label=person["id_proof_type"])
        page.get_by_label("ID Card Number", exact=False).nth(idx).fill(person["id_number"])
    except Exception as e:
        pause(
            f"Could not auto-fill all Pilgrim Details fields ({e}). "
            f"Please check/complete them yourself for S.No {s_no}."
        )


def upload_photo(page, photo: dict):
    if not photo:
        print("No photo in config — skipping upload, please attach it yourself.")
        return
    print(f"Uploading ID proof photo ({photo['filename']})...")
    file_bytes = base64.b64decode(photo["base64"])
    file_payload = [{
        "name": photo["filename"],
        "mimeType": photo.get("mime") or "image/png",
        "buffer": file_bytes,
    }]
    try:
        # The real <input type="file"> is usually hidden behind a styled
        # "Upload document" label/button, so target the input directly
        # rather than the visible text.
        page.locator('input[type="file"]').first.set_input_files(files=file_payload)
        return
    except Exception:
        pass
    try:
        page.get_by_text("Upload document", exact=False).first.set_input_files(files=file_payload)
    except Exception as e:
        pause(f"Could not auto-upload the photo ({e}). Please upload it yourself.")


def confirm_mobile(page, mobile: str):
    print("Checking mobile number field...")
    try:
        field = page.get_by_label("Mobile number", exact=False).first
        if field.input_value().strip() == "":
            field.fill(mobile)
    except Exception:
        pass  # mobile is often prefilled from the logged-in account


def main():
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("ttd_config.json")
    cfg = load_config(config_path)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        wait_for_login(page)
        open_sr_citizen_flow(page)
        wait_through_queue(page)
        fill_category_age_spouse(page, cfg)

        pause(
            "Pick your preferred date on the calendar and confirm the time "
            "slot yourself — this step is intentionally manual."
        )

        fill_pilgrim_details(page, cfg["pilgrim"], s_no=1)
        if cfg.get("accompany_spouse") == "Yes" and cfg.get("spouse"):
            fill_pilgrim_details(page, cfg["spouse"], s_no=2)

        upload_photo(page, cfg.get("photo"))
        confirm_mobile(page, cfg.get("mobile", ""))

        print("\nAttempting to click 'Continue'...")
        try:
            page.get_by_text("Continue", exact=True).click()
        except Exception:
            pause("Could not auto-click Continue. Please click it yourself.")

        pause(
            "Everything auto-fillable is done. Please REVIEW the booking "
            "summary carefully and click the final Submit/Book button "
            "yourself — this script won't do that step for you."
        )

        print("Done. Leaving the browser open — close it manually when finished.")
        input("Press Enter here to close the browser window and exit... ")
        browser.close()


if __name__ == "__main__":
    main()
