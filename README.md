# FRM Premium Signal System

**FerryRichMan Limited** · Top-2 Weighted Momentum ETF Signal with Conditional Leverage

---

## 🎯 Strategy Overview

- **Universe**: SPY, QQQ, VEU, GLD, TLT, BIL (6 unleveraged)
- **Leverage twins**: SPY → SSO (2x), QQQ → QLD (2x)
- **Score**: 0.8 × 3M return + 0.2 × 12M return (Adj Close)
- **Decision**: Top-2 by score, hold 60% in #1 + 40% in #2
- **Conditional leverage**: SPY @ score ≥ 0.05, QQQ @ score ≥ 0.08
- **Execution**: First trading day of next month at Adj Open

## 📊 Backtest Results (2008-2026, 18.8 years, 225 months)

> 以下數字係 2026-10 回看（lookback）計法更正後重跑嘅版本，同 App 內顯示一致
> （`validation_premium.json` 生成日 2026-10-14）。

| Metric | Value |
|---|---|
| CAGR | **16.65%** |
| Max Drawdown | -30.0% |
| Sharpe Ratio | 0.86 |
| Sortino Ratio | 1.14 |
| $10k → | $179,451 |
| Trades / year | ~12 |

---

## 🚀 Deployment Steps

### Step 1: Push to GitHub

```bash
# In Downloads folder (or move files to a clean folder first)
git init
git add app_premium.py academic_validation_ui.py validation_premium.json requirements.txt .gitignore .streamlit/secrets.toml.example README.md
git commit -m "Initial Premium app"

# Create new GitHub repo (e.g., qrs-premium), then:
git remote add origin https://github.com/YOUR_USERNAME/qrs-premium.git
git branch -M main
git push -u origin main
```

⚠️ **IMPORTANT**: The `.gitignore` excludes `.streamlit/secrets.toml` so the shared
HMAC secret won't leak. Only the `.example` template is committed.

### Step 2: Deploy on Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click **"New app"**
3. Select your repo (`qrs-premium`)
4. **Main file path**: `app_premium.py`
5. **Branch**: `main`
6. Click **"Advanced settings"** → **"Secrets"**, paste:
   ```toml
   FRM_SUB_SECRET = "SAME_HEX_AS_POPI_BACKEND_FRM_SUB_SECRET"
   ```
7. Click **"Deploy"**

You'll get a URL like `https://qrs-premium-XXXX.streamlit.app/`

### Step 3: Test

- Visit the URL → should show the "貼上解鎖 Token" login page
- Paste a valid token (or click through from ferryrichman.com, which appends
  `?token=...` to the URL) → should unlock the dashboard

### Step 4: How Subscribers Get In

This app does **not** use a static password. Access is gated by a short-lived,
HMAC-signed token issued by the POPI backend when a customer redeems their
subscription code on ferryrichman.com:

1. **Token issuance**: customer enters their unlock code on ferryrichman.com →
   POPI backend's `/api/subscription/redeem` verifies it and signs a token
   encoding `{plan, exp}` with the shared `FRM_SUB_SECRET` key
   (format: `<payload_b64>.<sig_b64>`).
2. **Handoff**: ferryrichman.com hands the token to this app either as a
   `?token=...` URL query param (one-click "💎 進入 Premium" flow) or the
   customer pastes it directly into the login box.
3. **Verification**: `_verify_frm_token()` in `app_premium.py` (function
   `check_password()` is the gate) re-derives the HMAC signature locally with
   the same `FRM_SUB_SECRET` — no API call back to POPI is needed, so this
   app can verify offline. It also checks the token hasn't expired (`exp`)
   and that the plan is one of `ALLOWED_PLANS_FOR_THIS_APP` (or the token's
   `unlocks` array includes `etf-prem`).
4. **Single-device enforcement**: once verified, the token's session is
   registered server-side (`_register_token_session`). If the same token is
   used to log in from a second device, the first session is invalidated
   (admin plan is exempt from this check).

Because verification is fully offline, this app has **no direct dependency**
on the POPI backend being reachable at request time — it only needs to share
the same `FRM_SUB_SECRET` value.

---

## 🔄 Operator Tasks

**Rotating the shared secret** (e.g., quarterly for security):

1. Generate a new key: `python -c "import secrets; print(secrets.token_hex(32))"`
2. Update `FRM_SUB_SECRET` in **every** FRM service that verifies these
   tokens (POPI backend + this app + any other product app) — they must all
   match, or existing tokens will fail verification everywhere.
3. Streamlit Cloud → App settings → Secrets → update `FRM_SUB_SECRET` → Save
   (app auto-restarts).
4. Previously issued tokens signed with the old secret stop working
   immediately; affected subscribers must re-redeem their code on
   ferryrichman.com to get a freshly signed token.

**Granting/revoking access**: handled entirely on the POPI backend side
(subscription plan + `unlocks` array control which tokens pass
`_has_access()` here) — there is nothing to configure in this repo per
subscriber.

**Forcing a subscriber to re-login on a new device**: nothing to do manually
— logging in from a second device automatically kicks the first session
(see Step 4 above).

---

## 🔧 Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Copy secrets template
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit .streamlit/secrets.toml and set FRM_SUB_SECRET to the same value as the
# POPI backend (needed to verify HMAC unlock tokens). Never commit this file.

# Run locally
streamlit run app_premium.py
```

Visit [http://localhost:8501](http://localhost:8501)

---

## 📝 File Structure

```
.
├── app_premium.py              # Main Streamlit app (FRM Premium logic + UI + HMAC token gate)
├── academic_validation_ui.py   # Renders the academic validation section
├── validation_premium.json     # Pre-computed validation results
├── requirements.txt            # Python dependencies
├── .gitignore                  # Excludes secrets, __pycache__, etc.
├── .streamlit/
│   ├── secrets.toml            # ⚠️ Local only, NEVER commit
│   └── secrets.toml.example    # Template (safe to commit)
└── README.md                   # This file
```

---

## ⚠️ Critical Risk Warnings

This Premium system uses **2x leveraged ETFs** (SSO, QLD) and is intended for
sophisticated investors who can tolerate:

- **Single-month losses up to -20%** (historical worst)
- **Drawdowns of -30% to -35%** (expected; could be -40% in tail event)
- **2x leveraged ETF decay** in choppy markets
- **Monthly turnover** ~12 trades/year (tax + commission impact; live figure shown in-app)
- **Strict execution discipline** required (missing one signal can hurt annual returns)

**This is NOT a passive buy-and-hold strategy. Subscribers must commit to monthly review and execution.**

---

## 📞 Support

- Subscribe / Renew: [Quantum Pioneers](https://www.quantum-pioneers.com)
- WhatsApp signal delivery: monthly on first trading day
- Strategy questions: refer to in-app Validation & Methodology sections

---

## 🏷️ Version

- **v1.1** (October 2026): `compute_signals()` 嘅 3M／6M／9M／12M 回看改為月份 period 對齊
  （修正 2／4／6／11 月嘅回看偏差）；回測指標已用修正後計法重跑，歷史上 2／4／6／11 月嘅
  訊號／持倉行亦已更新。策略公式、門檻、60/40 權重、執行規則**完全不變**。
- **v1.0** (May 2026): Initial Premium release
  - FRM Premium（Top-2 60/40 weighted, conditional leverage, per-ETF threshold）
  - Validation suite (walk-forward, GFC, AI burst stress tests)
  - Subscriber access via HMAC-signed unlock tokens (`FRM_SUB_SECRET`, see Step 4) — no static password

© FerryRichMan Limited. All rights reserved.
