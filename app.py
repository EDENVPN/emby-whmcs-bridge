import os
import hmac
import hashlib
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# ── Config from env ──────────────────────────────────────────────────────────
EMBY_URL     = os.environ['EMBY_URL'].rstrip('/')
EMBY_API_KEY = os.environ['EMBY_API_KEY']
SQUARE_TOKEN = os.environ['SQUARE_ACCESS_TOKEN']
SQUARE_SIG   = os.environ['SQUARE_WEBHOOK_SIGNATURE_KEY']
WHMCS_SECRET = os.environ['WHMCS_SECRET']   # shared secret for WHMCS hook calls
PORT         = int(os.environ.get('PORT', 5000))

SQUARE_API   = 'https://connect.squareup.com/v2'

# ═════════════════════════════════════════════════════════════════════════════
# EMBY HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def emby_headers():
    return {'X-Emby-Token': EMBY_API_KEY, 'Content-Type': 'application/json'}

def emby_create_user(username, password='ChangeMe123!'):
    """Create an Emby user and return the user dict."""
    r = requests.post(
        f'{EMBY_URL}/Users/New',
        headers=emby_headers(),
        json={'Name': username}
    )
    r.raise_for_status()
    user = r.json()
    uid = user['Id']
    # Set password
    requests.post(
        f'{EMBY_URL}/Users/{uid}/Password',
        headers=emby_headers(),
        json={'Id': uid, 'NewPw': password}
    )
    # Enable the account
    _emby_set_policy(uid, disabled=False)
    return user

def emby_find_user(username):
    r = requests.get(f'{EMBY_URL}/Users', headers=emby_headers())
    r.raise_for_status()
    for u in r.json():
        if u['Name'].lower() == username.lower():
            return u
    return None

def _emby_set_policy(uid, disabled: bool):
    r = requests.get(f'{EMBY_URL}/Users/{uid}', headers=emby_headers())
    r.raise_for_status()
    user = r.json()
    policy = user.get('Policy', {})
    policy['IsDisabled'] = disabled
    requests.post(
        f'{EMBY_URL}/Users/{uid}/Policy',
        headers=emby_headers(),
        json=policy
    )

def emby_suspend_user(username):
    u = emby_find_user(username)
    if u:
        _emby_set_policy(u['Id'], disabled=True)
        return True
    return False

def emby_unsuspend_user(username):
    u = emby_find_user(username)
    if u:
        _emby_set_policy(u['Id'], disabled=False)
        return True
    return False

def emby_delete_user(username):
    u = emby_find_user(username)
    if u:
        requests.delete(f'{EMBY_URL}/Users/{u["Id"]}', headers=emby_headers())
        return True
    return False

# ═════════════════════════════════════════════════════════════════════════════
# SQUARE HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def sq_headers():
    return {
        'Authorization': f'Bearer {SQUARE_TOKEN}',
        'Content-Type': 'application/json',
        'Square-Version': '2024-04-17'
    }

def sq_get_or_create_customer(email, name):
    r = requests.post(
        f'{SQUARE_API}/customers/search',
        headers=sq_headers(),
        json={'query': {'filter': {'email_address': {'exact': email}}}}
    )
    r.raise_for_status()
    customers = r.json().get('customers', [])
    if customers:
        return customers[0]
    # Create new
    r2 = requests.post(
        f'{SQUARE_API}/customers',
        headers=sq_headers(),
        json={'email_address': email, 'display_name': name,
              'reference_id': email}
    )
    r2.raise_for_status()
    return r2.json()['customer']

def verify_square_signature(body_bytes, sig_header, url):
    """Verify Square HMAC-SHA256 webhook signature."""
    msg = SQUARE_SIG + url + body_bytes.decode('utf-8')
    expected = hashlib.sha256(msg.encode()).digest()
    import base64
    return hmac.compare_digest(
        base64.b64encode(expected).decode(),
        sig_header
    )

# ═════════════════════════════════════════════════════════════════════════════
# WHMCS HOOK ENDPOINTS
# These are called by WHMCS Action Hooks (Setup > Automation > Custom hooks)
# using a simple HTTP GET/POST to your Railway URL.
# ═════════════════════════════════════════════════════════════════════════════

def verify_whmcs(req):
    secret = req.args.get('secret') or req.form.get('secret') or (req.json or {}).get('secret')
    if secret != WHMCS_SECRET:
        return False
    return True

@app.route('/provision/create', methods=['POST'])
def provision_create():
    """Called by WHMCS when an order is activated."""
    if not verify_whmcs(request):
        return jsonify({'error': 'unauthorized'}), 403
    data = request.json
    username = data.get('username')
    email    = data.get('email')
    name     = data.get('name', username)
    if not username or not email:
        return jsonify({'error': 'missing username or email'}), 400

    # Create or find Emby user
    existing = emby_find_user(username)
    if existing:
        emby_unsuspend_user(username)
        emby_uid = existing['Id']
    else:
        user = emby_create_user(username)
        emby_uid = user['Id']

    # Ensure Square customer exists
    sq_customer = sq_get_or_create_customer(email, name)

    return jsonify({
        'status': 'created',
        'emby_user_id': emby_uid,
        'square_customer_id': sq_customer['id']
    })

@app.route('/provision/suspend', methods=['POST'])
def provision_suspend():
    if not verify_whmcs(request):
        return jsonify({'error': 'unauthorized'}), 403
    data = request.json
    username = data.get('username')
    ok = emby_suspend_user(username)
    return jsonify({'status': 'suspended' if ok else 'not_found'})

@app.route('/provision/unsuspend', methods=['POST'])
def provision_unsuspend():
    if not verify_whmcs(request):
        return jsonify({'error': 'unauthorized'}), 403
    data = request.json
    username = data.get('username')
    ok = emby_unsuspend_user(username)
    return jsonify({'status': 'unsuspended' if ok else 'not_found'})

@app.route('/provision/terminate', methods=['POST'])
def provision_terminate():
    if not verify_whmcs(request):
        return jsonify({'error': 'unauthorized'}), 403
    data = request.json
    username = data.get('username')
    ok = emby_delete_user(username)
    return jsonify({'status': 'terminated' if ok else 'not_found'})

# ═════════════════════════════════════════════════════════════════════════════
# SQUARE WEBHOOK ENDPOINT
# ═════════════════════════════════════════════════════════════════════════════

@app.route('/webhooks/square', methods=['POST'])
def square_webhook():
    body = request.get_data()
    sig  = request.headers.get('x-square-hmacsha256-signature', '')
    url  = request.url

    if not verify_square_signature(body, sig, url):
        return jsonify({'error': 'invalid signature'}), 403

    event = request.json
    etype = event.get('type', '')
    data  = event.get('data', {}).get('object', {})

    # Subscription events
    if etype == 'subscription.updated':
        sub    = data.get('subscription', {})
        status = sub.get('status', '')
        cid    = sub.get('customer_id', '')
        # Look up customer email, then find WHMCS mapping
        _handle_subscription_status(cid, status)

    elif etype in ('invoice.payment_made', 'payment.completed'):
        # Payment succeeded — ensure customer is active
        cid = (data.get('invoice') or data.get('payment') or {}).get('customer_id', '')
        if cid:
            _handle_subscription_status(cid, 'ACTIVE')

    elif etype == 'invoice.payment_failed':
        invoice = data.get('invoice', {})
        cid     = invoice.get('primary_recipient', {}).get('customer_id', '')
        if cid:
            _handle_subscription_status(cid, 'SUSPENDED')

    return jsonify({'received': True})

def _handle_subscription_status(square_customer_id, status):
    """Given a Square customer ID and status, update Emby access."""
    # Get customer email from Square
    r = requests.get(
        f'{SQUARE_API}/customers/{square_customer_id}',
        headers=sq_headers()
    )
    if not r.ok:
        return
    customer = r.json().get('customer', {})
    email = customer.get('email_address', '')
    # The Emby username is stored as the customer's reference_id or email prefix
    username = customer.get('reference_id') or email.split('@')[0]

    if status in ('ACTIVE', 'ACTIVE_TRIAL'):
        emby_unsuspend_user(username)
    elif status in ('SUSPENDED', 'DEACTIVATED', 'CANCELED', 'PAUSED'):
        emby_suspend_user(username)

# ═════════════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ═════════════════════════════════════════════════════════════════════════════

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'service': 'emby-whmcs-bridge'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
