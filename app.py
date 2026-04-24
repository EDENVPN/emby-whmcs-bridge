import os
import hmac
import hashlib
import secrets
import string
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# — Config from env —
EMBY_URL          = os.environ['EMBY_URL'].rstrip('/')
EMBY_API_KEY      = os.environ['EMBY_API_KEY']
SQUARE_TOKEN      = os.environ['SQUARE_ACCESS_TOKEN']
SQUARE_SIG        = os.environ['SQUARE_WEBHOOK_SIGNATURE_KEY']
WHMCS_SECRET      = os.environ['WHMCS_SECRET']
WHMCS_URL         = os.environ.get('WHMCS_URL', '').rstrip('/')
WHMCS_IDENTIFIER  = os.environ.get('WHMCS_API_IDENTIFIER', '')
WHMCS_API_SECRET  = os.environ.get('WHMCS_API_SECRET', '')
PORT              = int(os.environ.get('PORT', 5000))

SQUARE_API = 'https://connect.squareup.com/v2'

# ═══════════════════════════════════
# EMBY HELPERS
# ═══════════════════════════════════

def emby_headers():
    return {'X-Emby-Token': EMBY_API_KEY, 'Content-Type': 'application/json'}

def gen_password(length=12):
    chars = string.ascii_letters + string.digits + '!@#$'
    return ''.join(secrets.choice(chars) for _ in range(length))

def emby_create_user(username, password=None):
    if not password:
        password = gen_password()
    r = requests.post(
        f'{EMBY_URL}/Users/New',
        headers=emby_headers(),
        json={'Name': username}
    )
    r.raise_for_status()
    user = r.json()
    uid = user['Id']
    # set password
    requests.post(
        f'{EMBY_URL}/Users/{uid}/Password',
        headers=emby_headers(),
        json={'NewPw': password, 'ResetPassword': True}
    )
    # enable access
    policy = user.get('Policy', {})
    policy['IsDisabled'] = False
    policy['EnableAllFolders'] = True
    requests.post(
        f'{EMBY_URL}/Users/{uid}/Policy',
        headers=emby_headers(),
        json=policy
    )
    return uid, password

def emby_disable_user(username):
    users = requests.get(f'{EMBY_URL}/Users', headers=emby_headers()).json()
    for u in users:
        if u['Name'].lower() == username.lower():
            uid = u['Id']
            policy = u.get('Policy', {})
            policy['IsDisabled'] = True
            requests.post(f'{EMBY_URL}/Users/{uid}/Policy', headers=emby_headers(), json=policy)
            return uid
    return None

def emby_delete_user(username):
    users = requests.get(f'{EMBY_URL}/Users', headers=emby_headers()).json()
    for u in users:
        if u['Name'].lower() == username.lower():
            uid = u['Id']
            requests.delete(f'{EMBY_URL}/Users/{uid}', headers=emby_headers())
            return uid
    return None

# ═══════════════════════════════════
# SQUARE HELPERS
# ═══════════════════════════════════

def sq_headers():
    return {
        'Authorization': f'Bearer {SQUARE_TOKEN}',
        'Content-Type': 'application/json',
        'Square-Version': '2024-01-17'
    }

def verify_square_signature(body_bytes, sig_header):
    expected = hmac.new(SQUARE_SIG.encode(), body_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig_header or '')

def create_square_invoice(email, name, amount_cents, note='Emby Streaming - Monthly'):
    idempotency_key = secrets.token_hex(16)
    # Create customer
    cust_r = requests.post(f'{SQUARE_API}/customers', headers=sq_headers(), json={
        'email_address': email, 'given_name': name, 'idempotency_key': idempotency_key
    })
    customer_id = cust_r.json().get('customer', {}).get('id')
    # Create order
    order_r = requests.post(f'{SQUARE_API}/orders', headers=sq_headers(), json={
        'idempotency_key': secrets.token_hex(16),
        'order': {
            'location_id': get_location_id(),
            'line_items': [{'name': note, 'quantity': '1',
                            'base_price_money': {'amount': amount_cents, 'currency': 'USD'}}]
        }
    })
    order_id = order_r.json().get('order', {}).get('id')
    # Create invoice
    inv_r = requests.post(f'{SQUARE_API}/invoices', headers=sq_headers(), json={
        'idempotency_key': secrets.token_hex(16),
        'invoice': {
            'location_id': get_location_id(),
            'order_id': order_id,
            'primary_recipient': {'customer_id': customer_id},
            'payment_requests': [{
                'request_type': 'BALANCE',
                'due_date': None,
                'automatic_payment_source': 'NONE'
            }],
            'delivery_method': 'EMAIL',
            'invoice_number': f'EMB-{idempotency_key[:8].upper()}'
        }
    })
    inv = inv_r.json().get('invoice', {})
    inv_id = inv.get('id')
    # Publish invoice
    requests.post(f'{SQUARE_API}/invoices/{inv_id}/publish', headers=sq_headers(), json={
        'idempotency_key': secrets.token_hex(16), 'version': 0
    })
    return inv.get('public_url', '')

def get_location_id():
    r = requests.get(f'{SQUARE_API}/locations', headers=sq_headers())
    locs = r.json().get('locations', [])
    return locs[0]['id'] if locs else ''

# ═══════════════════════════════════
# WHMCS API HELPER
# ═══════════════════════════════════

def whmcs_api(action, extra_params=None):
    params = {
        'identifier': WHMCS_IDENTIFIER,
        'secret': WHMCS_API_SECRET,
        'action': action,
        'responsetype': 'json'
    }
    if extra_params:
        params.update(extra_params)
    r = requests.post(f'{WHMCS_URL}/includes/api.php', data=params)
    return r.json()

def whmcs_update_service_status(service_id, status):
    return whmcs_api('UpdateClientProduct', {'serviceid': service_id, 'status': status})

# ═══════════════════════════════════
# ROUTES
# ═══════════════════════════════════

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'service': 'emby-whmcs-bridge'})

@app.route('/webhook/whmcs', methods=['POST'])
def whmcs_hook():
    """Called by WHMCS when services are created/terminated."""
    data = request.json or request.form.to_dict()
    secret = data.get('secret', '')
    if secret != WHMCS_SECRET:
        return jsonify({'error': 'unauthorized'}), 401

    action = data.get('action', '')
    email = data.get('email', '')
    username = data.get('username', email.split('@')[0] if email else '')
    service_id = data.get('service_id', '')
    amount = int(float(data.get('amount', '999')))  # in cents

    if action == 'create':
        uid, password = emby_create_user(username)
        # Create Square invoice for payment
        inv_url = ''
        if email:
            try:
                inv_url = create_square_invoice(email, username, amount)
            except Exception as e:
                app.logger.warning(f'Square invoice failed: {e}')
        return jsonify({
            'status': 'created',
            'emby_user_id': uid,
            'emby_username': username,
            'emby_password': password,
            'square_invoice_url': inv_url
        })

    elif action == 'suspend':
        uid = emby_disable_user(username)
        if service_id:
            whmcs_update_service_status(service_id, 'Suspended')
        return jsonify({'status': 'suspended', 'emby_user_id': uid})

    elif action == 'terminate':
        uid = emby_delete_user(username)
        if service_id:
            whmcs_update_service_status(service_id, 'Terminated')
        return jsonify({'status': 'terminated', 'emby_user_id': uid})

    elif action == 'unsuspend':
        users = requests.get(f'{EMBY_URL}/Users', headers=emby_headers()).json()
        for u in users:
            if u['Name'].lower() == username.lower():
                uid = u['Id']
                policy = u.get('Policy', {})
                policy['IsDisabled'] = False
                requests.post(f'{EMBY_URL}/Users/{uid}/Policy', headers=emby_headers(), json=policy)
                return jsonify({'status': 'unsuspended', 'emby_user_id': uid})
        return jsonify({'status': 'user_not_found'}), 404

    return jsonify({'status': 'unknown_action', 'action': action})

@app.route('/webhook/square', methods=['POST'])
def square_hook():
    """Called by Square when a payment is completed."""
    body = request.get_data()
    sig = request.headers.get('x-square-hmacsha256-signature', '')
    if not verify_square_signature(body, sig):
        return jsonify({'error': 'invalid signature'}), 401

    event = request.json
    event_type = event.get('type', '')

    if event_type in ('payment.created', 'payment.updated'):
        payment = event.get('data', {}).get('object', {}).get('payment', {})
        status = payment.get('status', '')
        if status == 'COMPLETED':
            note = payment.get('note', '')
            buyer_email = payment.get('buyer_email_address', '')
            username = buyer_email.split('@')[0] if buyer_email else f'user_{payment.get("id", "")[:8]}'
            uid, password = emby_create_user(username)
            app.logger.info(f'Square payment completed - created Emby user {username}')
            return jsonify({'status': 'user_created', 'emby_user': username})

    elif event_type == 'invoice.payment_made':
        invoice = event.get('data', {}).get('object', {}).get('invoice', {})
        customer_id = invoice.get('primary_recipient', {}).get('customer_id', '')
        if customer_id:
            cust_r = requests.get(f'{SQUARE_API}/customers/{customer_id}', headers=sq_headers())
            cust = cust_r.json().get('customer', {})
            email = cust.get('email_address', '')
            username = email.split('@')[0] if email else f'user_{customer_id[:8]}'
            uid, password = emby_create_user(username)
            app.logger.info(f'Invoice paid - created Emby user {username}')
            return jsonify({'status': 'user_created', 'emby_user': username})

    return jsonify({'status': 'event_received', 'type': event_type})

@app.route('/api/users', methods=['GET'])
def list_emby_users():
    """List all Emby users (for admin verification)."""
    secret = request.headers.get('X-Bridge-Secret', '')
    if secret != WHMCS_SECRET:
        return jsonify({'error': 'unauthorized'}), 401
    users = requests.get(f'{EMBY_URL}/Users', headers=emby_headers()).json()
    return jsonify([{'id': u['Id'], 'name': u['Name'], 'disabled': u.get('Policy', {}).get('IsDisabled', False)} for u in users])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
