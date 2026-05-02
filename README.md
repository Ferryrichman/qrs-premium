# QRS Premium Signal System (Strategy C)

**FerryRichMan Limited** · Top-2 Weighted Momentum ETF Signal with Conditional Leverage

---

## 🎯 Strategy Overview

- **Universe**: SPY, QQQ, VEU, GLD, TLT, BIL (6 unleveraged)
- **Leverage twins**: SPY → SSO (2x), QQQ → QLD (2x)
- **Score**: 0.8 × 3M return + 0.2 × 12M return (Adj Close)
- **Decision**: Top-2 by score, hold 60% in #1 + 40% in #2
- **Conditional leverage**: SPY @ score ≥ 0.05, QQQ @ score ≥ 0.08
- **Execution**: First trading day of next month at Adj Open

## 📊 Backtest Results (2008-2026, 17.3 years)

| Metric | Value |
|---|---|
| CAGR | **15.0%** |
| Max Drawdown | -27.9% |
| Sharpe Ratio | 0.80 |
| Sortino Ratio | 1.03 |
| $10k → | $128,684 |

---

## 🚀 Deployment Steps

### Step 1: Push to GitHub

```bash
# In Downloads folder (or move files to a clean folder first)
git init
git add app_premium.py requirements.txt .gitignore .streamlit/secrets.toml.example README_PREMIUM.md
git commit -m "Initial Premium app"

# Create new GitHub repo (e.g., qrs-premium), then:
git remote add origin https://github.com/YOUR_USERNAME/qrs-premium.git
git branch -M main
git push -u origin main
```

⚠️ **IMPORTANT**: The `.gitignore` excludes `.streamlit/secrets.toml` so your password
won't leak. Only the `.example` template is committed.

### Step 2: Deploy on Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click **"New app"**
3. Select your repo (`qrs-premium`)
4. **Main file path**: `app_premium.py`
5. **Branch**: `main`
6. Click **"Advanced settings"** → **"Secrets"**, paste:
   ```toml
   access_password = "YOUR_ACTUAL_PASSWORD_HERE"
   ```
7. Click **"Deploy"**

You'll get a URL like `https://qrs-premium-XXXX.streamlit.app/`

### Step 3: Test

- Visit the URL → should show login page
- Enter the password you set in step 6 → should unlock the dashboard

### Step 4: Distribute Password to Subscribers

Update your Stripe receipt template / WhatsApp welcome message to include:

```
🔑 你的 Premium Access Password:
   YOUR_PASSWORD_HERE

🔗 Premium Dashboard:
   https://qrs-premium-XXXX.streamlit.app/

每月第一個交易日早上 HKT 09:00 後 dashboard 會更新最新訊號。
WhatsApp 群組亦會同步發送。
```

---

## 🔄 Updating the Password

If you need to rotate the password (e.g., quarterly for security):

1. Streamlit Cloud → App settings → Secrets → update `access_password`
2. Save (app auto-restarts)
3. Email/WhatsApp new password to all active subscribers

---

## 🔧 Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Copy secrets template
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit .streamlit/secrets.toml and set your password

# Run locally
streamlit run app_premium.py
```

Visit [http://localhost:8501](http://localhost:8501)

---

## 📝 File Structure

```
.
├── app_premium.py              # Main Streamlit app (Strategy C logic + UI)
├── requirements.txt            # Python dependencies
├── .gitignore                  # Excludes secrets, __pycache__, etc.
├── .streamlit/
│   ├── secrets.toml            # ⚠️ Local only, NEVER commit
│   └── secrets.toml.example    # Template (safe to commit)
└── README_PREMIUM.md           # This file
```

---

## ⚠️ Critical Risk Warnings

This Premium system uses **2x leveraged ETFs** (SSO, QLD) and is intended for
sophisticated investors who can tolerate:

- **Single-month losses up to -20%** (historical worst)
- **Drawdowns of -28% to -35%** (expected; could be -40% in tail event)
- **2x leveraged ETF decay** in choppy markets
- **Monthly turnover** ~14 trades/year (tax + commission impact)
- **Strict execution discipline** required (missing one signal can hurt annual returns)

**This is NOT a passive buy-and-hold strategy. Subscribers must commit to monthly review and execution.**

---

## 📞 Support

- Subscribe / Renew: [Quantum Pioneers](https://www.quantum-pioneers.com)
- WhatsApp signal delivery: monthly on first trading day
- Strategy questions: refer to in-app Validation & Methodology sections

---

## 🏷️ Version

- **v1.0** (May 2026): Initial Premium release
  - Strategy C (Top-2 60/40 weighted, conditional leverage, per-ETF threshold)
  - Validation suite (walk-forward, GFC, AI burst stress tests)
  - Password-protected access

© FerryRichMan Limited. All rights reserved.
