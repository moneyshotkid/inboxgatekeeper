import imaplib
import smtplib
import email
from email.header import decode_header
from email.mime.text import MIMEText
from email.utils import parseaddr
import openai
import pandas as pd
import html2text
import re
from datetime import datetime
import time

# ================= CONFIGURATION =================
# GMAIL SETTINGS
EMAIL_USER = "your@gmail.com"
EMAIL_PASS = "" # Not your login password!
IMAP_SERVER = "imap.gmail.com"
EMAIL_COUNT = 40  # How many recent emails to test

# OPENAI SETTINGS
OPENAI_API_KEY = "sk-......" # Your OpenAI Key
openai.api_key = OPENAI_API_KEY

# SAFETY SETTING
DRY_RUN = True  # Set to False to ACTUALLY send challenge emails

# WHITELIST (Trusted Senders - Lowercase)
WHITELIST = [
    "person1@email.com",
    "person2@email.com"
]

# CHALLENGE EMAIL TEMPLATE
CHALLENGE_SUBJECT = "Action Required: Please verify you are human"
CHALLENGE_BODY = """
Hello,

In an attempt to prevent spam and marketing emails, your message cleared the initial test, I just need to reply to this email the name of the person you are trying to get ahold of. Then I will forward your message and all future message directly to Nick. 


Thank you for understanding,
Nick Nguyens Personal Automated Gatekeeper
"""
# =================================================

def extract_email_address(raw_from):
    """Extracts just the email address from 'Name <email@domain.com>'"""
    name, addr = parseaddr(raw_from)
    return addr.lower()

def clean_email_body(msg):
    """Extracts and cleans text from email."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            try:
                payload = part.get_payload(decode=True)
                if payload:
                    if content_type == "text/plain":
                        body += payload.decode()
                    elif content_type == "text/html":
                        h = html2text.HTML2Text()
                        h.ignore_links = True
                        body += h.handle(payload.decode())
            except:
                pass
    else:
        try:
            payload = msg.get_payload(decode=True)
            if msg.get_content_type() == "text/html":
                h = html2text.HTML2Text()
                body = h.handle(payload.decode())
            else:
                body = payload.decode()
        except:
            pass
    return body[:1500].strip()

def send_challenge(to_email):
    """Sends the automated challenge response."""
    if DRY_RUN:
        print(f"   [DRY RUN] Would send challenge email to: {to_email}")
        return True

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        
        msg = MIMEText(CHALLENGE_BODY.format(name=EMAIL_USER))
        msg['Subject'] = CHALLENGE_SUBJECT
        msg['From'] = EMAIL_USER
        msg['To'] = to_email
        
        server.sendmail(EMAIL_USER, to_email, msg.as_string())
        server.quit()
        print(f"   [SENT] Challenge email sent to: {to_email}")
        return True
    except Exception as e:
        print(f"   [ERROR] Could not send email: {e}")
        return False

# --- FILTER LOGIC ---
def is_bot_or_transactional(msg, subject, body):
    """
    Determines if an email is clearly a bot, newsletter, or receipt.
    We DO NOT want to send challenge emails to bots (backscatter).
    """
    # 1. Technical Headers (Strongest Signal)
    if msg.get("List-Unsubscribe") or msg.get("Auto-Submitted") == 'auto-generated':
        return True, "Technical Header (List-Unsubscribe/Auto)"

    # 2. Sender Name Checks
    sender = extract_email_address(msg.get("From", ""))
    bad_prefixes = ["no-reply", "noreply", "newsletter", "bounce", "notifications", "service", "support"]
    if any(x in sender for x in bad_prefixes):
        return True, "Bot Sender Name"

    # 3. Content Checks (Heuristic)
    text = (str(subject) + " " + str(body)).lower()
    bot_triggers = ["unsubscribe", "privacy policy", "view in browser", "receipt", "order confirmation"]
    if any(t in text for t in bot_triggers):
        return True, f"Automated Content Trigger"

    return False, "Looks Human"

def llm_analysis(subject, body):
    """
    LLM sanity check.
    """
    client = openai.Client(api_key=OPENAI_API_KEY)
    prompt = f"""
    Analyze this email.
    Subject: {subject}
    Body: {body}
    
    Is this email likely from a specific HUMAN being trying to contact the user personally? 
    Or is it a newsletter, receipt, notification, or cold-marketing blast?
    
    Format:
    TYPE: [HUMAN or BOT]
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        content = response.choices[0].message.content
        return "HUMAN" in content
    except:
        return False

# --- MAIN EXECUTION ---
def main():
    print("Connecting to Gmail IMAP...")
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    try:
        mail.login(EMAIL_USER, EMAIL_PASS)
    except Exception as e:
        print(f"Login Failed: {e}")
        return
    mail.select("inbox")
    
    status, messages = mail.search(None, "ALL")
    latest_email_ids = messages[0].split()[-EMAIL_COUNT:]

    results = []

    print(f"Scanning last {len(latest_email_ids)} emails...")
    print(f"Mode: {'DRY RUN (No emails sent)' if DRY_RUN else 'LIVE (Sending Challenges)'}")
    print("-" * 60)

    for i, e_id in enumerate(latest_email_ids):
        try:
            _, msg_data = mail.fetch(e_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    # 1. Extract Details
                    subject_header = decode_header(msg["Subject"])[0]
                    subject = subject_header[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(subject_header[1] if subject_header[1] else "utf-8")
                    
                    raw_sender = msg.get("From")
                    sender_email = extract_email_address(raw_sender)
                    body = clean_email_body(msg)

                    print(f"[{i+1}] {sender_email} | {subject[:30]}...")

                    action_taken = "None"
                    reason = ""

                    # 2. LOGIC FLOW
                    
                    # A. Whitelist Check
                    if sender_email in WHITELIST:
                        action_taken = "PASSED"
                        reason = "Sender in Whitelist"
                        print(f"   ✅ {reason}")

                    # B. Bot Filter (Traditional)
                    else:
                        is_bot, bot_reason = is_bot_or_transactional(msg, subject, body)
                        
                        if is_bot:
                            action_taken = "IGNORED"
                            reason = f"Identified as Bot ({bot_reason})"
                            print(f"   🤖 {reason} - No challenge sent.")
                        
                        # C. Potential Human (Send Challenge)
                        else:
                            # Optional: Ask LLM for second opinion before challenging
                            # (To avoid challenging subtle spam)
                            is_llm_human = llm_analysis(subject, body)
                            
                            if is_llm_human:
                                action_taken = "CHALLENGED"
                                reason = "Unknown Sender + Looks Human"
                                print(f"   ❓ {reason}")
                                send_challenge(sender_email)
                            else:
                                action_taken = "IGNORED"
                                reason = "LLM identified as subtle spam/marketing"
                                print(f"   🗑️ {reason}")

                    results.append({
                        "Sender": sender_email,
                        "Subject": subject,
                        "Action": action_taken,
                        "Reason": reason
                    })

        except Exception as e:
            print(f"Error processing email: {e}")

    # Save Log
    df = pd.DataFrame(results)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    df.to_csv(f"gatekeeper_log_{timestamp}.csv", index=False)
    
    mail.close()
    mail.logout()
    print("\nProcess Complete.")

if __name__ == "__main__":
    main()