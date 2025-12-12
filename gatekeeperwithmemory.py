import imaplib
import smtplib
import email
from email.header import decode_header
from email.mime.text import MIMEText
from email.utils import parseaddr
import openai
import pandas as pd
import html2text
import os
from datetime import datetime
import time

# ================= CONFIGURATION =================
# GMAIL SETTINGS
EMAIL_USER = "your@gmail.com"
EMAIL_PASS = "" 
IMAP_SERVER = "imap.gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_COUNT = 20 

# FILES
WHITELIST_FILE = "whitelist.txt"
LOG_FILE = f"gatekeeper_log_{datetime.now().strftime('%Y%m%d')}.csv"

# OPENAI SETTINGS
OPENAI_API_KEY = "sk-...." 
openai.api_key = OPENAI_API_KEY

# SAFETY SETTING
DRY_RUN = True  # Set to False to ACTUALLY send challenges and update whitelist

# CHALLENGE SETTINGS
# The subject we send, and look for replies to
CHALLENGE_SUBJECT_BASE = "Action Required: Please verify you are human"
# The secret word they must type
SECRET_CODE = "Nick" 

CHALLENGE_BODY = """
Hello,

I am an automated email screening system, your email has passed our initial test, but we just you to 
please reply to this email with the name of the person you are trying to get in touch with, and if correct we will forward you message and all future messages right away.

Thank you,
Automated Gatekeeper 
"""
# =================================================

# --- FILE MANAGEMENT ---
def load_whitelist():
    """Reads trusted emails from a file."""
    if not os.path.exists(WHITELIST_FILE):
        # Create file if it doesn't exist
        with open(WHITELIST_FILE, "w") as f:
            f.write("mom@gmail.com\n") # Example
        return set(["mom@gmail.com"])
    
    with open(WHITELIST_FILE, "r") as f:
        # Read lines, strip whitespace, remove empty lines
        emails = {line.strip().lower() for line in f if line.strip()}
    return emails

def update_whitelist(new_email):
    """Adds a new email to the file."""
    current_list = load_whitelist()
    if new_email in current_list:
        return # Already exists
    
    if DRY_RUN:
        print(f"   [DRY RUN] Would write {new_email} to {WHITELIST_FILE}")
        return

    with open(WHITELIST_FILE, "a") as f:
        f.write(f"\n{new_email}")
    print(f"   💾 Saved {new_email} to {WHITELIST_FILE}")

# --- EMAIL TOOLS ---
def extract_email_address(raw_from):
    name, addr = parseaddr(raw_from)
    return addr.lower()

def clean_email_body(msg):
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    body += part.get_payload(decode=True).decode()
                except: pass
    else:
        try: 
            body = msg.get_payload(decode=True).decode() 
        except: pass
    return body[:1000].strip()

def send_challenge(to_email):
    if DRY_RUN:
        print(f"   [DRY RUN] Sending challenge to: {to_email}")
        return
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        msg = MIMEText(CHALLENGE_BODY.format(name=EMAIL_USER))
        msg['Subject'] = CHALLENGE_SUBJECT_BASE
        msg['From'] = EMAIL_USER
        msg['To'] = to_email
        server.sendmail(EMAIL_USER, to_email, msg.as_string())
        server.quit()
        print(f"   📧 Sent challenge to: {to_email}")
    except Exception as e:
        print(f"   [ERROR] Sending failed: {e}")

# --- PHASE 1: CHECK FOR VERIFICATIONS ---
def process_challenge_replies(mail):
    """
    Scans for emails replying to our challenge. 
    If they contain the SECRET_CODE, whitelist them.
    """
    print("\n🔍 Phase 1: Checking for Verified Humans...")
    
    # Search for emails with our specific subject line
    # (RFC822 search criteria)
    search_crit = f'(SUBJECT "{CHALLENGE_SUBJECT_BASE}")'
    status, messages = mail.search(None, search_crit)
    
    if not messages[0]:
        print("   No verification replies found.")
        return

    email_ids = messages[0].split()
    
    for e_id in email_ids:
        _, msg_data = mail.fetch(e_id, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        
        sender = extract_email_address(msg.get("From"))
        subject = msg.get("Subject", "")
        body = clean_email_body(msg).upper() # Uppercase for easier comparison

        # Ensure it is a REPLY, not the one we sent
        if sender == EMAIL_USER.lower():
            continue

        print(f"   Checking reply from {sender}...")

        # Check for the secret code (e.g., "HUMAN")
        if SECRET_CODE in body:
            print(f"   🎉 SUCCESS: '{SECRET_CODE}' found!")
            update_whitelist(sender)
        else:
            print(f"   ❌ Failed: Reply did not contain secret code.")

# --- PHASE 2: SCAN INBOX ---
def is_bot(msg, subject, body):
    # 1. Technical Headers
    if msg.get("List-Unsubscribe") or msg.get("Auto-Submitted") == 'auto-generated':
        return True
    # 2. Keywords
    text = (str(subject) + " " + str(body)).lower()
    if any(x in text for x in ["unsubscribe", "privacy policy", "view in browser"]):
        return True
    return False

def main():
    # 1. Setup
    print(f"Loading whitelist from {WHITELIST_FILE}...")
    whitelist = load_whitelist()
    print(f"Trusted senders: {len(whitelist)}")

    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(EMAIL_USER, EMAIL_PASS)
    mail.select("inbox")

    # 2. Run Verification Phase (Updates Whitelist)
    process_challenge_replies(mail)
    
    # Reload whitelist in case we just added someone
    whitelist = load_whitelist()

    # 3. Run Scanning Phase
    print("\n🔍 Phase 2: Scanning Recent Emails...")
    status, messages = mail.search(None, "ALL")
    latest_email_ids = messages[0].split()[-EMAIL_COUNT:]
    
    results = []

    for e_id in latest_email_ids:
        try:
            _, msg_data = mail.fetch(e_id, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            sender = extract_email_address(msg.get("From"))
            
            # Skip if it's me (Sent items often appear in All Mail/Inbox depending on view)
            if sender == EMAIL_USER.lower():
                continue

            # Decode Subject
            subject_header = decode_header(msg["Subject"])[0]
            subject = subject_header[0]
            if isinstance(subject, bytes):
                subject = subject.decode(subject_header[1] or "utf-8")
            
            body = clean_email_body(msg)

            # LOGIC TREE
            status = "UNKNOWN"
            
            # A. Whitelisted?
            if sender in whitelist:
                status = "✅ PASSED (Whitelisted)"
            
            # B. Bot?
            elif is_bot(msg, subject, body):
                status = "🤖 BLOCKED (Bot/Newsletter)"
            
            # C. Challenge?
            else:
                # LLM check to ensure it's not subtle spam
                # (Can remove this if you want to challenge EVERYONE not in whitelist)
                status = "❓ CHALLENGING (Sent Request)"
                send_challenge(sender)

            print(f"[{sender}] -> {status}")
            
            results.append({"Sender": sender, "Subject": subject[:30], "Status": status})

        except Exception as e:
            print(f"Error: {e}")

    # Save logs
    pd.DataFrame(results).to_csv(LOG_FILE, index=False)
    mail.close()
    mail.logout()
    print("\nDone.")

if __name__ == "__main__":
    main() 
