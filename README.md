# 🛡️ The AI Gatekeeper: Zero-Trust Email Filter

**The AI Gatekeeper** is a Python-based email security tool designed to reclaim your inbox. Unlike traditional spam filters that look for *bad* actors, this script operates on a **Zero-Trust** model: it blocks everything unless the sender is verified as a human.

It combines **Heuristic Analysis** (checking technical headers) with **Semantic Analysis** (OpenAI GPT-4o) to distinguish between automated "graymail" (newsletters, receipts, bots) and genuine personal correspondence.

## 🚀 Features

*   **Zero-Trust Filtering:** Treats all incoming mail as spam until proven otherwise.
*   **Hybrid Detection:**
    *   **Traditional:** Flags technical indicators of automation (List-Unsubscribe headers, "no-reply" senders).
    *   **LLM (AI):** Uses GPT-4o to analyze context and intent, filtering out marketing, receipts, and cold sales.
*   **Challenge-Response System:** Automatically emails unverified senders asking them to reply with a secret code (e.g., "HUMAN") to prove they aren't robots.
*   **Auto-Whitelisting:** Scans your inbox for correct replies to the challenge and automatically adds those senders to a persistent `whitelist.txt`.
*   **Dry Run Mode:** Test the logic without actually sending emails or blocking mail.

## 🛠️ Prerequisites

1.  **Python 3.8+**
2.  **Gmail Account:** You must enable 2-Factor Authentication and generate an **App Password**. You cannot use your standard login password.
3.  **OpenAI API Key:** Requires a paid account (uses `gpt-4o-mini` for cost efficiency).

## 📦 Installation

1.  Clone this repository or download the script.
2.  Install the required dependencies:

```bash```
pip install openai pandas html2text

## ⚙️ Configuration
Open the script (gatekeeper.py) and update the Configuration Section at the top:
code
Python
# GMAIL SETTINGS
EMAIL_USER = "your_email@gmail.com"
EMAIL_PASS = "your_16_char_app_password" 

# OPENAI SETTINGS
OPENAI_API_KEY = "sk-your-openai-key"

# SAFETY SETTING
DRY_RUN = True  # Set to False only when ready to go live!
🧠 How It Works (The Logic Flow)
When the script runs, it processes emails in the following order:
Phase 1: Verification Scan
The script scans your inbox for replies to previous Challenge Emails.
It looks for the secret code (e.g., "HUMAN") in the body.
If found, the sender is immediately added to whitelist.txt.
Phase 2: Inbox Filtration
For every new email in your inbox:
Whitelist Check: Is the sender in whitelist.txt?
YES: ✅ PASSED. (Email is safe).
NO: Proceed to step 2.
Bot Filter (Traditional): Does the email contain List-Unsubscribe headers, or come from noreply@?
YES: 🤖 BLOCKED. (It is a newsletter or bot. No challenge sent to avoid backscatter).
NO: Proceed to step 3.
LLM Sanity Check: Does the AI think this looks like a human personal email?
NO: 🗑️ IGNORED. (Likely cold sales or subtle marketing).
YES: ❓ CHALLENGED.
The script sends an automated email: "Please reply with 'HUMAN' to prove you are real."
## 🏃 Usage
1. Test Mode (Dry Run)
Keep DRY_RUN = True. Run the script:
code
Bash
python gatekeeper.py
The script will print logs to the console showing you exactly which emails would be blocked and which would receive a challenge, without actually taking action.
2. Live Mode
Set DRY_RUN = False. The script will now:
Send emails via SMTP.
Update your whitelist.txt file automatically.
## 📁 File Structure
gatekeeper.py: The main logic script.
whitelist.txt: A simple text file containing trusted email addresses (one per line).
gatekeeper_log_[date].csv: A log of every email processed and the action taken.
##  ⚠️ Disclaimer
API Costs: This script makes calls to OpenAI. While gpt-4o-mini is cheap, processing thousands of emails will incur costs.
Missed Emails: The "Paranoid" settings will block legitimate automated emails (password resets, flight confirmations, etc.). You must manually check your spam/logs or add those senders to your whitelist.
Email Sending Limits: Gmail has daily sending limits. Do not use this on an inbox receiving thousands of emails daily.
