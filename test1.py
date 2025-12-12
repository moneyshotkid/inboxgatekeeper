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
EMAIL_USER = "your@gmail.com"
EMAIL_PASS = "" # Not your login password!
IMAP_SERVER = "imap.gmail.com"
EMAIL_COUNT = 40  # How many recent emails to test

# OPENAI SETTINGS
OPENAI_API_KEY = "sk-......" # Your OpenAI Key
openai.api_key = OPENAI_API_KEY

# OUTPUT FILE
OUTPUT_FILE = f"spam_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
# =================================================

def clean_email_body(msg):
    """Extracts and cleans text from email, removing HTML."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            try:
                if "attachment" not in content_disposition:
                    payload = part.get_payload(decode=True)
                    if payload:
                        if content_type == "text/plain":
                            body += payload.decode()
                        elif content_type == "text/html":
                            h = html2text.HTML2Text()
                            h.ignore_links = False
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
            
    # Truncate to save tokens and processing time (first 1000 chars)
    return body[:1000].strip()

# --- METHOD 1: TRADITIONAL (Heuristic / Rule Based) ---
def traditional_spam_filter(subject, body):
    """
    A logic-based filter representing traditional SpamAssassin-style scoring.
    """
    score = 0
    reasons = []
    
    # Normalize
    text = (str(subject) + " " + str(body)).lower()
    
    # 1. Trigger Words (Weighted)
    triggers = {
        "verify your account": 3, "urgent": 2, "winner": 4, 
        "lottery": 5, "inheritance": 4, "bank account": 2, 
        "click here": 1, "unsubscribe": 0.5, "offer": 1, 
        "limited time": 2, "crypto": 3, "investment": 2, "free": 2
    }
    
    for word, weight in triggers.items():
        if word in text:
            score += weight
            reasons.append(f"Contains '{word}'")

    # 2. Heuristics
    if subject.isupper():
        score += 3
        reasons.append("Subject is ALL CAPS")
        
    if "!" * 3 in text:
        score += 2
        reasons.append("Excessive exclamation marks")

    if "$" in subject:
        score += 2
        reasons.append("Money symbol in subject")

    # Classification Threshold
    is_spam = score >= 4
    return {
        "method": "Traditional",
        "is_spam": is_spam,
        "score": score,
        "reason": "; ".join(reasons) if reasons else "Clean"
    }

# --- METHOD 2: LLM (OpenAI GPT-4o-mini or GPT-3.5) ---
def llm_spam_filter(subject, body):
    """
    Uses an LLM to analyze context, tone, and intent.
    """
    client = openai.Client(api_key=OPENAI_API_KEY)
    
    prompt = f"""
    Analyze the following email and determine if it is SPAM or HAM (Legitimate).
    
    Subject: {subject}
    Body snippet: {body}
    
    Rules:
    - Look for phishing attempts, urgent fake requests, and unsolicited marketing.
    - Newsletters from reputable companies are HAM.
    - Personal emails are HAM.
    
    Respond in this exact format:
    CLASSIFICATION: [SPAM or HAM]
    REASON: [Short explanation]
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini", # Cost effective model
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
        print("Did you use an App Password?")
        return

    mail.select("inbox")
    
    # Fetch last N emails
    status, messages = mail.search(None, "ALL")
    email_ids = messages[0].split()
    latest_email_ids = email_ids[-EMAIL_COUNT:]

    results = []

    print(f"Processing last {len(latest_email_ids)} emails...")

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

                    # Run Method 1
                    trad_result = traditional_spam_filter(subject, body)
                    
                    # Run Method 2
                    llm_result = llm_spam_filter(subject, body)

                    # Store Results
                    results.append({
                        "From": sender,
                        "Subject": subject,
                        "Body_Snippet": body[:100],
                        "Traditional_Prediction": "SPAM" if trad_result['is_spam'] else "HAM",
                        "Traditional_Reason": trad_result['reason'],
                        "LLM_Prediction": "SPAM" if llm_result['is_spam'] else "HAM",
                        "LLM_Reason": llm_result['reason'],
                        "Human_Review": "" # Blank column for you to fill in
                    })

        except Exception as e:
            print(f"Skipping email due to error: {e}")

    # Save to CSV
    df = pd.DataFrame(results)
    df.to_csv(OUTPUT_FILE, index=False)
    
    mail.close()
    mail.logout()
    print(f"\nDone! Results saved to {OUTPUT_FILE}")
    print("Open the CSV file to review the 'Traditional' vs 'LLM' verdicts.")

if __name__ == "__main__":
    main()