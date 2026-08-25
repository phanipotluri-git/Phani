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


BROWSER_CLOSED_MARKERS = ("has been closed", "Target page, context or browser")


def pause(message: str):
    print(f"\n>>> {message}")
    input(">>> Press Enter here once done... ")


def handle_failure(action_desc: str, exc: Exception, manual_hint: str):
    """Print what actually went wrong, and stop cleanly instead of looping
    through more doomed steps if the browser/page itself is gone."""
    text = str(exc)
    if any(marker in text for marker in BROWSER_CLOSED_MARKERS):
        sys.exit(
            f"\nThe browser window was closed while trying to {action_desc}. "
            "Nothing further can be automated once that happens -- re-run "
            "the script to start over."
        )
    pause(f"Could not {action_desc} ({text}). {manual_hint}")


def find_field(page, label_text: str, placeholder: str = None, tag: str = "input", after_text: str = None):
    """Best-effort locator for a form control near a visual label.

    The real TTD form does not reliably associate labels with their
    controls via <label for=...> (confirmed: get_by_label timed out
    finding nothing for "Pilgrim Name" on a live run), so try several
    strategies in order and use whichever actually finds something.

    If `after_text` is given (e.g. "Pilgrim Details"), the *first* strategy
    tried is a DOM-proximity XPath scoped to elements appearing after that
    anchor AND near `label_text` specifically -- both scoped, in one query.
    This matters because some labels/placeholders repeat elsewhere on the
    page (confirmed: "Enter Age" appears both in the top-level slot form
    and in each Pilgrim Details block -- an unscoped placeholder search
    silently fills the wrong field). Falls back to the unscoped versions
    (get_by_label, get_by_placeholder, plain proximity) if that fails.

    Every proximity match here tries the label's *own direct text* (XPath
    text()) before falling back to its full descendant text (XPath '.').
    On a real, deeply-nested DOM (this site is visually a Material-style
    app with wrapper divs everywhere), contains(., label_text) can match
    an ancestor wrapper whose *aggregate* text happens to contain the
    label, not just the label element itself -- confirmed by reproducing
    exactly this failure against a nested mock. text() only ever matches
    an element's own direct text node, which is unambiguous.

    Returns a Locator (which may match 0, 1, or more elements -- caller
    decides via .first / .nth(i)), or raises if nothing at all was found.
    """
    def _proximity(scope_prefix: str, tag_: str):
        for predicate in (f"text(), '{label_text}'", f"normalize-space(.), '{label_text}'"):
            try:
                xpath = f"xpath={scope_prefix}//*[contains({predicate})]/following::{tag_}[1]"
                loc = page.locator(xpath)
                if loc.count() > 0:
                    return loc
            except Exception:
                continue
        return None

    if after_text:
        try:
            anchor_xpath = f"//*[contains(text(), '{after_text}')]"
            for label_predicate in (f"text(), '{label_text}'", f"normalize-space(.), '{label_text}'"):
                xpath = f"xpath={anchor_xpath}/following::*[contains({label_predicate})]/following::{tag}[1]"
                loc = page.locator(xpath)
                if loc.count() > 0:
                    return loc
        except Exception:
            pass

    try:
        loc = page.get_by_label(label_text, exact=False)
        if loc.count() > 0:
            return loc
    except Exception:
        pass

    if placeholder:
        try:
            loc = page.get_by_placeholder(placeholder, exact=False)
            if loc.count() > 0:
                return loc
        except Exception:
            pass

    loc = _proximity("", tag)
    if loc is not None:
        return loc

    raise LookupError(f"no element found for label '{label_text}' (tried proximity/label/placeholder)")


def select_dropdown_value(page, trigger_label: str, option_text: str, after_text: str = None, idx: int = 0):
    """Set a dropdown field's value.

    Confirmed live (screenshot from a real run): TTD's "Category" field is
    NOT a native <select> -- it's a clickable div showing the current
    value, which opens a floating popup listing clickable option rows
    ("Senior Citizen", "Medical Cases", "Differently Abled") when clicked.
    Gender / Photo ID Proof / Accompany-with-Spouse look visually
    identical in earlier screenshots, so likely the same component.

    Tries a real <select> first (harmless if it's not one), then falls
    back to click-trigger-then-click-option for a custom combobox.
    """
    try:
        find_field(page, trigger_label, tag="select", after_text=after_text).nth(idx).select_option(label=option_text)
        return
    except Exception:
        pass

    try:
        find_field(page, trigger_label, tag="*", after_text=after_text).nth(idx).click()
    except Exception as e:
        raise LookupError(f"could not click the '{trigger_label}' dropdown trigger: {e}")

    try:
        page.get_by_role("option", name=option_text, exact=True).first.click()
        return
    except Exception:
        pass

    try:
        # The popup's option row was just added to the page, so it's the
        # most recent matching text node -- .last avoids re-clicking the
        # trigger's own (possibly identical) displayed value.
        page.get_by_text(option_text, exact=True).last.click()
    except Exception as e:
        raise LookupError(f"could not click option '{option_text}' in the '{trigger_label}' dropdown: {e}")


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
        select_dropdown_value(page, "Category", "Senior Citizen")
    except Exception as e:
        handle_failure("select Category", e, "Please choose 'Senior Citizen' yourself.")

    print(f"Filling Age = {pilgrim['age']}...")
    try:
        find_field(page, "Age", placeholder="Enter Age", tag="input").first.fill(str(pilgrim["age"]))
    except Exception as e:
        handle_failure("fill Age", e, f"Please enter {pilgrim['age']} yourself.")

    print(f"Setting 'Accompany with the Spouse' = {accompany}...")
    # The site's dropdown options are ALL CAPS ("YES"/"NO"), but the config
    # value from TTD.html is Title Case ("Yes"/"No") -- try both.
    last_exc = None
    for candidate in (accompany, accompany.upper(), accompany.lower()):
        try:
            select_dropdown_value(page, "Accompany", candidate)
            break
        except Exception as e:
            last_exc = e
    else:
        handle_failure("select spouse option", last_exc, f"Please choose '{accompany}' yourself.")


def fill_pilgrim_details(page, person: dict, s_no: int):
    label = "yours" if s_no == 1 else "your spouse's"
    print(f"Filling Pilgrim Details ({label})...")
    # If the form pre-renders all S.No blocks at once (common in reactive
    # forms), ".last" would resolve to the same final block on every call,
    # silently overwriting it instead of filling each pilgrim's own block.
    # Index by position (nth) instead, 0-based.
    idx = s_no - 1
    anchor = "Pilgrim Details"
    try:
        find_field(page, "Pilgrim Name", placeholder="Enter Name", tag="input", after_text=anchor).nth(idx).fill(person["name"])
        find_field(page, "Age", placeholder="Enter Age", tag="input", after_text=anchor).nth(idx).fill(str(person["age"]))
        select_dropdown_value(page, "Gender", person["gender"], after_text=anchor, idx=idx)
        select_dropdown_value(page, "Photo ID Proof", person["id_proof_type"], after_text=anchor, idx=idx)
        find_field(page, "ID Card Number", placeholder="Enter ID Card Number", tag="input", after_text=anchor).nth(idx).fill(person["id_number"])
    except Exception as e:
        handle_failure(
            f"fill all Pilgrim Details fields for S.No {s_no}",
            e,
            f"Please check/complete them yourself for S.No {s_no}.",
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
        handle_failure("upload the photo", e, "Please upload it yourself.")


def confirm_mobile(page, mobile: str):
    print("Checking mobile number field...")
    try:
        field = find_field(page, "Mobile number", tag="input").first
        if field.input_value().strip() == "":
            field.fill(mobile)
    except Exception as e:
        text = str(e)
        if any(marker in text for marker in BROWSER_CLOSED_MARKERS):
            sys.exit(
                "\nThe browser window was closed while checking the mobile "
                "number field. Re-run the script to start over."
            )
        print(f"(Could not check/fill Mobile number automatically: {text}. "
              f"It's often prefilled from your account -- verify it yourself.)")


def main():
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("ttd_config.json")
    cfg = load_config(config_path)

    with sync_playwright() as p:
        # Prefer driving the system-installed Google Chrome (channel="chrome")
        # over Playwright's own bundled Chromium build -- the bundled build
        # drops support for older OS versions (e.g. it refuses to install on
        # macOS 12) well before the OS itself stops running Chrome fine.
        try:
            browser = p.chromium.launch(channel="chrome", headless=False)
        except Exception as e:
            sys.exit(
                "Could not launch Google Chrome via Playwright "
                f"({e}).\n"
                "Make sure Google Chrome is installed (chrome://version in "
                "Chrome shows its path). Alternatively, run "
                "'playwright install chromium' and remove the "
                "channel=\"chrome\" argument from p.chromium.launch(...) "
                "in this script to use Playwright's own bundled Chromium "
                "instead (only works if your OS is new enough for it)."
            )
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
        except Exception as e:
            handle_failure("click Continue", e, "Please click it yourself.")

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
