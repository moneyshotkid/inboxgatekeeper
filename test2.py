import imaplib
import email
from email.header import decode_header
import openai
import pandas as pd
import html2text
import re
import os
from datetime import datetime

# ================= CONFIGURATION =================
# GMAIL SETTINGS
# GMAIL SETTINGS
EMAIL_USER = "your@gmail.com"
EMAIL_PASS = "" # Not your login password!
IMAP_SERVER = "imap.gmail.com"
EMAIL_COUNT = 40  # How many recent emails to test

# OPENAI SETTINGS
OPENAI_API_KEY = "sk-......" # Your OpenAI Key
openai.api_key = OPENAI_API_KEY

# OUTPUT FILE
OUTPUT_FILE = f"paranoid_spam_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
# =================================================

def clean_email_body(msg):
    """Extracts and cleans text from email, removing HTML."""
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
                        h.ignore_links = True # Ignore links to focus on text
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
            
    return body[:1500].strip() # Slightly larger buffer for context

# --- METHOD 1: PARANOID TRADITIONAL (Heuristic) ---
def traditional_spam_filter(msg, subject, body):
    """
    Flags ANYTHING that looks automated, corporate, or mass-mailed.
    """
    score = 0
    reasons = []
    
    # Normalize text
    text = (str(subject) + " " + str(body)).lower()
    sender = msg.get("From", "").lower()
    
    # 1. TECHNICAL HEADER CHECK (The smoking gun for automation)
    # Almost all newsletters, alerts, and marketing tools add this header.
    if msg.get("List-Unsubscribe"):
        score += 5
        reasons.append("Technical Header: List-Unsubscribe found")

    # 2. SENDER CHECKS
    bad_senders = ["no-reply", "noreply", "newsletter", "info@", "support@", "marketing", "sales", "hello@"]
    for bs in bad_senders:
        if bs in sender:
            score += 3
            reasons.append(f"Generic sender: '{bs}'")

    # 3. CORPORATE FOOTER LANGUAGE
    # Real humans don't usually put copyright notices in emails to friends.
    corporate_triggers = [
        "privacy policy", "terms of service", "all rights reserved", 
        "view in browser", "unsubscribe", "manage preferences", 
        "copyright", "inc.", "llc"
    ]
    
    found_triggers = [t for t in corporate_triggers if t in text]
    if found_triggers:
        score += 3
        reasons.append(f"Corporate footer detected ({found_triggers[0]})")

    # 4. TRANSACTIONAL WORDS
    # Catching receipts and alerts
    trans_triggers = ["order confirmation", "receipt", "invoice", "verify your email", "security alert"]
    for t in trans_triggers:
        if t in text:
            score += 2
            reasons.append(f"Transactional language: '{t}'")

    # STRICT THRESHOLD: Even a score of 2 (one minor trigger) flags it.
    is_spam = score >= 2
    
    return {
        "method": "Traditional (Paranoid)",
        "is_spam": is_spam,
        "score": score,
        "reason": "; ".join(reasons) if reasons else "Clean (Likely Personal)"
    }

# --- METHOD 2: PARANOID LLM (Contextual Zero-Trust) ---
def llm_spam_filter(subject, body):
    """
    Uses LLM with strict instructions to flag ANY non-personal email.
    """
    client = openai.Client(api_key=OPENAI_API_KEY)
    
    prompt = f"""
    Analyze the following email.
    
    Subject: {subject}
    Body snippet: {body}
    
    STRICT "PERSONAL-ONLY" FILTERING RULES:
    1. The goal is to identify "Graymail" and "Machine Generated" mail.
    2. If the email is a Newsletter, Advertisement, Receipt, Security Alert, Shipping Notification, or Business Update: Classify as SPAM.
    3. If the email is a generic "No-Reply" notification: Classify as SPAM.
    4. The ONLY emails classified as HAM should be personal, hand-written correspondence between two humans (e.g., "Hey, do you want to grab lunch?").
    
    Respond in this exact format:
    CLASSIFICATION: [SPAM or HAM]
    REASON: [Short explanation]
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini", 
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        content = response.choices[0].message.content
        
        is_spam = "CLASSIFICATION: SPAM" in content
        reason = content.split("REASON:")[1].strip() if "REASON:" in content else content
        
        return {
            "method": "LLM",
            "is_spam": is_spam,
            "reason": reason
        }
    except Exception as e:
        return {"method": "LLM", "is_spam": False, "reason": f"Error: {str(e)}"}

# --- MAIN EXECUTION ---
def main():
    print("Connecting to Gmail...")
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    
    try:
        mail.login(EMAIL_USER, EMAIL_PASS)
    except Exception as e:
        print(f"Login Failed: {e}")
        return

    mail.select("inbox")
    
    # Fetch last N emails
    status, messages = mail.search(None, "ALL")
    email_ids = messages[0].split()
    latest_email_ids = email_ids[-EMAIL_COUNT:]

    results = []

    print(f"Processing last {len(latest_email_ids)} emails with PARANOID settings...")

    for i, e_id in enumerate(latest_email_ids):
        try:
            _, msg_data = mail.fetch(e_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    # Decode Subject
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding if encoding else "utf-8")
                    
                    sender = msg.get("From")
                    body = clean_email_body(msg)

                    print(f"[{i+1}/{EMAIL_COUNT}] Analyzing: {subject[:30]}...")

                    # Run Method 1 (Now passing 'msg' object for header analysis)
                    trad_result = traditional_spam_filter(msg, subject, body)
                    
                    # Run Method 2
                    llm_result = llm_spam_filter(subject, body)

                    # Store Results
                    results.append({
                        "From": sender,
                        "Subject": subject,
                        "Body_Snippet": body[:100].replace("\n", " "),
                        "Traditional_Prediction": "SPAM" if trad_result['is_spam'] else "HAM",
                        "Traditional_Reason": trad_result['reason'],
                        "LLM_Prediction": "SPAM" if llm_result['is_spam'] else "HAM",
                        "LLM_Reason": llm_result['reason'],
                        "Human_Review": "" 
                    })

        except Exception as e:
            print(f"Skipping email due to error: {e}")

    # Save to CSV
    df = pd.DataFrame(results)
    df.to_csv(OUTPUT_FILE, index=False)
    
    mail.close()
    mail.logout()
    print(f"\nDone! Results saved to {OUTPUT_FILE}")

if __name__ == "__main__":
