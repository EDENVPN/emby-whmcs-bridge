# Emby + WHMCS + Square Integration Bridge

**Automated user provisioning system** that connects Emby media server, WHMCS billing, and Square payments for seamless subscription management.

## 🎯 Overview

This bridge service automatically:
- Creates Emby user accounts when WHMCS services are provisioned
- Generates Square payment invoices for customers
- Handles Square payment webhooks to activate accounts
- Suspends/terminates Emby access based on WHMCS service status
- Integrates with WHMCS Cloud via API (no custom modules required)

## 🏗️ Architecture

```
┌─────────┐     ┌──────────┐     ┌─────────────┐     ┌──────────┐
│ WHMCS   │────>│  Bridge  │<────│   Square    │────>│ Customer │
│ Cloud   │     │  (Flask) │     │   Payments  │     │  Email   │
└─────────┘     └──────────┘     └─────────────┘     └──────────┘
                     │   │
                     │   └────> Emby API
                     │          (Create/Suspend/Delete Users)
                     │
                     └────> WHMCS API
                            (Update Service Status)
```

## ⚙️ Configuration

### Environment Variables (Railway/Docker)

```bash
EMBY_URL=http://your-emby-server:8096
EMBY_API_KEY=your_emby_api_key
SQUARE_ACCESS_TOKEN=your_square_production_token
SQUARE_WEBHOOK_SIGNATURE_KEY=your_square_webhook_sig_key
WHMCS_URL=https://your-whmcs-site.com
WHMCS_API_IDENTIFIER=your_whmcs_api_identifier
WHMCS_API_SECRET=your_whmcs_api_secret
WHMCS_SECRET=your_custom_webhook_secret
PORT=5000
```

### Setup Steps

#### 1. Emby Server
1. Navigate to **Dashboard → API Keys**
2. Create new API key named "WHMCS-Square Bridge"
3. Copy the key to `EMBY_API_KEY`

#### 2. Square Developer
1. Go to [Square Developer Console](https://developer.squareup.com/)
2. Create new application (or use existing)
3. Get **Production Access Token** → `SQUARE_ACCESS_TOKEN`
4. Create webhook subscription:
   - **URL**: `https://your-bridge-url.com/webhook/square`
   - **Events**: `payment.created`, `payment.updated`, `invoice.payment_made`
5. Copy **Signature Key** → `SQUARE_WEBHOOK_SIGNATURE_KEY`

#### 3. WHMCS Cloud
1. Go to **Setup → Staff Management → Manage API Credentials**
2. Create API Role with permissions:
   - Billing (all)
   - Client (all)
   - Module (all)
   - Orders (all)
   - Products (all)
3. Generate API Credential using the role
4. Copy **Identifier** → `WHMCS_API_IDENTIFIER`
5. Copy **Secret** → `WHMCS_API_SECRET`
6. Create product:
   - Type: **Other**
   - Name: "Emby Streaming - Monthly"
   - Pricing: Recurring ($9.99/month)
7. Enable automation: **Setup → Automation Settings**
   - ✓ Enable Suspension
   - ✓ Enable Unsuspension
   - ✓ Enable Termination

#### 4. Deploy to Railway
1. Fork this repository
2. Connect Railway to your GitHub repo
3. Add all environment variables
4. Railway auto-deploys and provides public URL

## 📡 API Endpoints

### Health Check
```bash
GET /health
```
Returns: `{"status": "ok", "service": "emby-whmcs-bridge"}`

### WHMCS Webhook
```bash
POST /webhook/whmcs
Content-Type: application/json

{
  "secret": "your_whmcs_secret",
  "action": "create",
  "email": "customer@example.com",
  "username": "customerusername",
  "service_id": "12345",
  "amount": 999
}
```

**Actions**: `create`, `suspend`, `unsuspend`, `terminate`

**Response (create)**:
```json
{
  "status": "created",
  "emby_user_id": "abc123",
  "emby_username": "customerusername",
  "emby_password": "GeneratedPass123!",
  "square_invoice_url": "https://squareup.com/pay-invoice/xyz"
}
```

### Square Webhook
```bash
POST /webhook/square
X-Square-Hmacsha256-Signature: signature_from_square
```
Automatically processes payment events and creates/activates Emby users.

### List Emby Users (Admin)
```bash
GET /api/users
X-Bridge-Secret: your_whmcs_secret
```
Returns all Emby users with their status.

## 🔄 Workflows

### Flow 1: Manual WHMCS Trigger
1. Customer orders "Emby Streaming" in WHMCS
2. Admin calls `/webhook/whmcs` with action=`create`
3. Bridge creates Emby user + generates Square invoice
4. Customer receives Square payment link via email
5. Customer pays → Square webhook fires
6. Bridge activates Emby account (sets password, enables access)
7. Customer receives Emby credentials via WHMCS email

### Flow 2: Square Direct Payment
1. Customer pays via Square invoice/link
2. Square webhook fires to bridge
3. Bridge auto-creates Emby user from payment email
4. Customer receives Emby credentials

### Flow 3: WHMCS Automation
1. WHMCS cron detects overdue invoice (5 days)
2. **Manual trigger** OR **Zapier/Make/n8n** calls `/webhook/whmcs` with action=`suspend`
3. Bridge disables Emby user
4. Customer pays invoice
5. WHMCS marks active → trigger `/webhook/whmcs` with action=`unsuspend`
6. Bridge re-enables Emby access

## 🚀 Usage Examples

### cURL: Create User + Square Invoice
```bash
curl -X POST https://your-bridge-url.com/webhook/whmcs \
  -H "Content-Type: application/json" \
  -d '{
    "secret": "whmcs_bridge_secret_xK9mP2vL8nQ4rT7y",
    "action": "create",
    "email": "john@example.com",
    "username": "john_doe",
    "amount": 999
  }'
```

### Python: Suspend User
```python
import requests

requests.post(
    'https://your-bridge-url.com/webhook/whmcs',
    json={
        'secret': 'whmcs_bridge_secret_xK9mP2vL8nQ4rT7y',
        'action': 'suspend',
        'username': 'john_doe',
        'service_id': '12345'
    }
)
```

## 🛠️ Development

### Local Testing
```bash
# Clone repo
git clone https://github.com/EDENVPN/emby-whmcs-bridge.git
cd emby-whmcs-bridge

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export EMBY_URL=http://localhost:8096
export EMBY_API_KEY=your_key
# ... set other vars

# Run
python app.py
```

Bridge runs on `http://localhost:5000`

### Testing Webhooks Locally
Use [ngrok](https://ngrok.com/) to expose local server:
```bash
ngrok http 5000
```
Use the ngrok URL in Square webhook configuration.

## 📝 WHMCS Cloud Limitations

WHMCS Cloud **does not support**:
- Custom PHP hook files
- Custom provisioning modules
- Direct file system access

**Workarounds**:
1. ✅ Use bridge with manual triggers (admin calls webhook)
2. ✅ Use Zapier/Make.com/n8n to watch WHMCS and trigger bridge
3. ✅ Use WHMCS API polling (future enhancement)

## 🔐 Security

- All webhook endpoints verify secrets/signatures
- WHMCS webhook requires `WHMCS_SECRET` in request body
- Square webhook validates HMAC-SHA256 signature
- Admin endpoints require `X-Bridge-Secret` header
- Production credentials only (Square production mode)

## 📦 Dependencies

- **Flask**: Web framework
- **requests**: HTTP client for Emby/Square/WHMCS APIs
- **Python 3.9+**

## 📄 License

MIT License - Free to use and modify

## 🤝 Support

For issues or questions:
1. Check existing [GitHub Issues](https://github.com/EDENVPN/emby-whmcs-bridge/issues)
2. Review API documentation above
3. Test with `/health` endpoint first
4. Verify all environment variables are set correctly

---

**Deployed Instance**: [emby-whmcs-bridge-production.up.railway.app](https://emby-whmcs-bridge-production.up.railway.app/health)

**Status**: ✅ Online | **Version**: 1.0.0 | **Last Updated**: April 2026
