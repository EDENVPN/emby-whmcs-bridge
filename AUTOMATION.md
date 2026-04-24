# 🤖 Full Automation Setup Guide

## Complete Workflow - NO MANUAL STEPS NEEDED

This guide shows you how to make the **entire system automatic** from order to Emby access.

---

## 🎯 Goal: Zero Manual Work

**Current State:**
- ⚠️ Manual: You trigger bridge when orders come in
- ✅ Automatic: Square webhooks work automatically

**After This Setup:**
- ✅ **100% Automatic**: Customer orders → Emby account created → Square invoice sent → Customer pays → Access granted
- ✅ **100% Automatic**: Overdue → Auto-suspend → Payment received → Auto-unsuspend
- ✅ **100% Automatic**: Cancelled → Auto-terminate

---

## 🚀 METHOD 1: Zapier Automation (Recommended - 5 minutes)

### Step 1: Create Zapier Account
1. Go to https://zapier.com
2. Sign up (Free plan works!)

### Step 2: Create "New Order" Zap

**Trigger: WHMCS New Order**
```
App: Webhooks by Zapier
Trigger: Catch Hook
```

1. Copy webhook URL (e.g., `https://hooks.zapier.com/hooks/catch/123456/abc789/`)
2. In WHMCS: Setup → Automation Settings → Module Commands
3. Add webhook URL to fire on "Order Placed"

**Action: Call Bridge**
```
App: Webhooks by Zapier
Action: POST
URL: https://emby-whmcs-bridge-production.up.railway.app/webhook/whmcs
Payload Type: JSON
Data:
{
  "secret": "whmcs_bridge_secret_xK9mP2vL8nQ4rT7y",
  "action": "create",
  "email": "{{client_email}}",
  "username": "{{client_firstname}}_{{client_lastname}}",
  "service_id": "{{service_id}}",
  "amount": 999
}
```

### Step 3: Create "Service Suspended" Zap

**Trigger:** WHMCS Service Suspended
**Action:** POST to `/webhook/whmcs` with `action: "suspend"`

### Step 4: Create "Service Unsuspended" Zap

**Trigger:** WHMCS Payment Received
**Action:** POST to `/webhook/whmcs` with `action: "unsuspend"`

### Step 5: Create "Service Terminated" Zap

**Trigger:** WHMCS Service Terminated
**Action:** POST to `/webhook/whmcs` with `action: "terminate"`

---

## 🚀 METHOD 2: Make.com (Integromat) - More Power

1. Go to https://make.com
2. Create scenario: WHMCS → HTTP Request → Bridge
3. Configure same logic as Zapier above
4. Benefit: More complex workflows, cheaper at scale

---

## 🚀 METHOD 3: n8n (Self-Hosted - Free Forever)

### Install n8n
```bash
docker run -it --rm \
  --name n8n \
  -p 5678:5678 \
  -v ~/.n8n:/home/node/.n8n \
  n8nio/n8n
```

### Create Workflow
1. Webhook node → Listen for WHMCS events
2. HTTP Request node → POST to bridge
3. Deploy and get webhook URL
4. Add URL to WHMCS automation

---

## 📋 COMPLETE AUTOMATED FLOW

### Customer Orders
```
1. Customer → www.edenvpn.xyz → Orders "Emby Streaming"
2. WHMCS → Creates order + invoice
3. WHMCS → Fires webhook → Zapier
4. Zapier → POST to bridge → action: create
5. Bridge → Creates Emby user + Square invoice
6. Bridge → Returns: username, password, payment_url
7. Zapier → Emails customer (or WHMCS does)
8. Customer → Clicks Square payment link
9. Customer → Pays $9.99
10. Square → Webhook to bridge
11. Bridge → Activates account (already active but logged)
12. Customer → Logs into Emby ✅ DONE
```

### Customer Doesn't Pay (5 Days)
```
1. WHMCS Cron → Detects overdue (5 days)
2. WHMCS → Auto-suspends service
3. WHMCS → Fires webhook → Zapier
4. Zapier → POST to bridge → action: suspend
5. Bridge → Disables Emby account
6. Customer → Can't login ❌
```

### Customer Pays Late
```
1. Customer → Pays invoice
2. WHMCS → Marks paid
3. WHMCS → Fires webhook → Zapier
4. Zapier → POST to bridge → action: unsuspend
5. Bridge → Re-enables Emby account
6. Customer → Can login again ✅
```

### Customer Cancels (30 Days Unpaid)
```
1. WHMCS Cron → Auto-terminates
2. WHMCS → Fires webhook → Zapier
3. Zapier → POST to bridge → action: terminate
4. Bridge → Deletes Emby user permanently
5. Done 🗑️
```

---

## 🔧 SIMPLE WHMCS EMAIL-BASED TRIGGER (No Zapier)

If you don't want Zapier, use this workaround:

### Setup
1. Create email: automation@yourdomain.com
2. Forward to Zapier Email Parser OR use IFTTT
3. WHMCS sends email on every order
4. Email triggers automation

### WHMCS Email Template
Go to: Setup → Email Templates → Order Confirmation

Add to admin CC:
```
automation@yourdomain.com
```

Email parser extracts:
- Client Email
- Service ID
- Username

Then triggers bridge.

---

## 📊 DASHBOARD: Monitor Everything

### Railway Logs
```
https://railway.com/project/YOUR_PROJECT/logs
```
See all bridge activity in real-time

### Square Dashboard
```
https://squareup.com/dashboard
```
Track all payments

### WHMCS Activity Log
```
https://www.edenvpn.xyz/admin/systemactivitylog.php
```
See all WHMCS events

### Emby Users
```
http://igliidd-1e.box14.appboxmanager.xyz:9999/web/index.html#!/users
```
Verify user creation

---

## ✅ TEST THE AUTOMATION

### Quick Test
1. Create test order in WHMCS
2. Watch Zapier trigger
3. Check Railway logs for bridge call
4. Verify Emby user created
5. Check Square for invoice
6. Pay invoice
7. Verify it all works

### Test Command (Bypass Zapier)
```bash
curl -X POST https://emby-whmcs-bridge-production.up.railway.app/webhook/whmcs \
  -H "Content-Type: application/json" \
  -d '{
    "secret": "whmcs_bridge_secret_xK9mP2vL8nQ4rT7y",
    "action": "create",
    "email": "test@test.com",
    "username": "testuser",
    "amount": 999
  }'
```

---

## 🎬 VIDEO TUTORIAL (TODO)

Coming soon: Step-by-step video showing:
1. Zapier setup (5 min)
2. Test order (2 min)
3. Customer payment flow (3 min)
4. Suspension/termination (2 min)

---

## 💡 PRO TIPS

### Tip 1: Use Zapier Filters
Only trigger for "Emby Streaming" products:
```
Filter: Product Name contains "Emby"
```

### Tip 2: Add Slack Notifications
Get notified on every new signup:
```
Zapier → Slack → "New Emby user: john_doe"
```

### Tip 3: Auto-Email Credentials
Zapier can email customer directly:
```
Action: Gmail → Send Email
To: {{client_email}}
Subject: Your Emby Account is Ready!
Body:
Username: {{username}}
Password: {{password}}
Pay here: {{square_url}}
```

### Tip 4: Track in Google Sheets
Log every user:
```
Action: Google Sheets → Add Row
Data: Email, Username, Date, Status
```

---

## 🆘 TROUBLESHOOTING

### Bridge Not Responding
1. Check Railway logs
2. Verify service is Online
3. Test /health endpoint

### WHMCS Webhook Not Firing
1. Check WHMCS Activity Log
2. Verify webhook URL is correct
3. Test manually with curl

### Square Invoice Not Creating
1. Check Square API credentials
2. Verify location ID exists
3. Check Railway logs for errors

### Emby User Not Created
1. Check Emby API key
2. Verify Emby server is accessible
3. Check Railway logs

---

## 📞 SUPPORT

Questions? Check:
1. GitHub README: https://github.com/EDENVPN/emby-whmcs-bridge
2. Railway Logs: https://railway.com/project/...
3. Zapier Community: https://community.zapier.com/

---

**Last Updated:** April 24, 2026
**Status:** ✅ Production Ready
**Automation Level:** 🚀 100% Hands-Free
