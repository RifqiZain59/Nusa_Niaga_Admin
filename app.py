from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from io import BytesIO
import json
import base64
import time
import random

# --- FIREBASE IMPORTS ---
import firebase_admin
from firebase_admin import credentials, auth, firestore

app = Flask(__name__)
app.secret_key = "rahasia_nusa_niaga_no_uuid"

# ==========================================
# 0. INISIALISASI FIREBASE & FIRESTORE
# ==========================================
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
        print("✅ Firebase Admin & Firestore berhasil diinisialisasi.")
    except Exception as e:
        print(f"⚠️ Gagal inisialisasi Firebase: {e}")

db = firestore.client()
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# [PENTING] Mencegah Browser Cache agar Data Selalu Update
@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# ==========================================
# 1. GENERATOR ID & HELPER
# ==========================================
def generate_id():
    timestamp = int(time.time())
    random_part = random.randint(100, 999)
    return f"{timestamp}{random_part}"

def parse_flutter_date(date_str):
    try:
        if isinstance(date_str, datetime): return date_str
        if not date_str: return datetime.now()
        clean_str = str(date_str).replace(' at ', ' ').split(' UTC')[0].split(' +')[0]
        try:
            return datetime.strptime(clean_str, '%B %d, %Y %I:%M:%S %p')
        except ValueError:
            return datetime.fromisoformat(str(date_str))
    except Exception:
        return datetime.now()

# ==========================================
# 2. HELPER CLASSES
# ==========================================
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    doc = db.collection('users').document(str(user_id)).get()
    if doc.exists:
        return User(doc.id, doc.to_dict())
    return None

class FirestoreModel:
    def __init__(self, id, data):
        self.id = id
        self._data = data if data else {}

    def __getattr__(self, name):
        return self._data.get(name)

class User(UserMixin, FirestoreModel):
    def check_password(self, password):
        return check_password_hash(self._data.get('password_hash', ''), password)
    
    def set_password(self, password):
        self._data['password_hash'] = generate_password_hash(password)

class Category(FirestoreModel): pass

class Product(FirestoreModel):
    @property
    def category(self):
        cat_id = self._data.get('category_id')
        if cat_id:
            doc = db.collection('categories').document(str(cat_id)).get()
            if doc.exists: return Category(doc.id, doc.to_dict())
        return None

    @property
    def price(self): return int(self._data.get('price', 0))

    @property
    def stock(self): return int(self._data.get('stock', 0))

    @property
    def created_at(self):
        return parse_flutter_date(self._data.get('created_at'))

class Customer(FirestoreModel):
    @property
    def points(self): return int(self._data.get('points', 0))
    
    @property
    def created_at(self):
        return parse_flutter_date(self._data.get('created_at'))

class Transaction(FirestoreModel):
    @property
    def product(self):
        prod_id = self._data.get('product_id')
        if prod_id:
            doc = db.collection('products').document(str(prod_id)).get()
            if doc.exists: return Product(doc.id, doc.to_dict())
        return Product(None, {'name': 'Produk Terhapus'})
    
    @property
    def date(self):
        val = self._data.get('date') or self._data.get('created_at')
        return parse_flutter_date(val)

    @property
    def final_price(self):
        val = self._data.get('final_price')
        if val is None:
            val = self._data.get('summary', {}).get('grand_total', 0)
        return int(val)

    @property
    def quantity(self):
        val = self._data.get('quantity')
        return int(val) if val is not None else 0
    
    @property
    def discount_voucher(self):
        val = self._data.get('discount_voucher')
        return int(val) if val is not None else 0
    
    @property
    def points_earned(self):
        val = self._data.get('points_earned')
        return int(val) if val is not None else 0
    
    @property
    def status(self):
        return self._data.get('status', 'success')

class Review(FirestoreModel):
    @property
    def customer(self):
        cid = self._data.get('customer_id') or self._data.get('user_id')
        # Prioritas pakai nama yang tersimpan di review
        name = self._data.get('customer_name')
        if name: return Customer(cid, {'name': name})
        
        # Fallback query DB
        if cid:
            d = db.collection('customers').document(str(cid)).get()
            if d.exists: return Customer(d.id, d.to_dict())
        return Customer(None, {'name': 'Unknown'})
    
    @property
    def product(self):
        pid = self._data.get('product_id')
        if pid:
            d = db.collection('products').document(str(pid)).get()
            if d.exists: return Product(d.id, d.to_dict())
        return Product(None, {'name': 'Unknown'})
        
    @property
    def created_at(self):
        return parse_flutter_date(self._data.get('created_at'))

class Favorite(FirestoreModel):
    @property
    def customer(self):
        cid = self._data.get('customer_id')
        if cid:
            d = db.collection('customers').document(str(cid)).get()
            if d.exists: return Customer(d.id, d.to_dict())
        return Customer(None, {'name': 'Unknown'})
    
    @property
    def product(self):
        pid = self._data.get('product_id')
        if pid:
            d = db.collection('products').document(str(pid)).get()
            if d.exists: return Product(d.id, d.to_dict())
        return Product(None, {'name': 'Unknown'})
        
    @property
    def created_at(self):
        return parse_flutter_date(self._data.get('created_at'))

class PointRedemption(FirestoreModel):
    @property
    def customer(self):
        cid = self._data.get('customer_id')
        if cid:
            d = db.collection('customers').document(str(cid)).get()
            if d.exists: return Customer(d.id, d.to_dict())
        return Customer(None, {'name': 'Unknown'})
    
    @property
    def date(self):
        return parse_flutter_date(self._data.get('date'))

class SocialPost(FirestoreModel):
    @property
    def schedule_time(self):
        return parse_flutter_date(self._data.get('schedule_time'))

EARN_RATE = 5000 

def get_all_collection(collection_name, model_class):
    docs = db.collection(collection_name).stream()
    return [model_class(doc.id, doc.to_dict()) for doc in docs]

def get_doc_by_id(collection_name, doc_id, model_class):
    doc = db.collection(collection_name).document(str(doc_id)).get()
    if doc.exists: return model_class(doc.id, doc.to_dict())
    return None

# ==========================================
# 3. ROUTES (WEB ADMIN)
# ==========================================

@app.context_processor
def inject_theme():
    return dict(theme={'primary_color': '#2563eb', 'sidebar_color': '#1e3a8a', 'font_family': 'Poppins'})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        users_ref = db.collection('users').where('username', '==', username).limit(1).stream()
        user_data, user_id = None, None
        for doc in users_ref:
            user_data = doc.to_dict()
            user_id = doc.id
            break
            
        if user_data:
            user_obj = User(user_id, user_data)
            if user_obj.check_password(password):
                login_user(user_obj)
                return redirect(url_for('index'))
        flash("Username atau password salah.", "danger")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        check = db.collection('users').where('username', '==', username).get()
        if len(check) > 0:
            flash("Username sudah ada.", "warning")
            return redirect(url_for('register'))
            
        new_data = {
            'username': username,
            'password_hash': generate_password_hash(password),
            'full_name': 'Admin',
            'email': '', 'address': ''
        }
        user_id = generate_id()
        db.collection('users').document(user_id).set(new_data)
        
        flash("Akun dibuat. Silakan login.", "success")
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout(): logout_user(); return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    products = get_all_collection('products', Product)
    trx_docs = db.collection('transactions').stream()
    
    all_data = []
    for d in trx_docs:
        dd = d.to_dict()
        t_id = d.id
        if 'items' in dd and 'summary' in dd: 
             all_data.append({
                 'date': parse_flutter_date(dd.get('created_at')),
                 'final_price': int(dd['summary'].get('grand_total', 0)),
                 'customer_name': dd.get('customer_name', 'Pelanggan App'),
                 'product': {'name': f"{len(dd['items'])} Item"},
                 'quantity': sum(int(i.get('qty',0)) for i in dd['items']),
                 'status': dd.get('status', 'success')
             })
        else: 
             t = Transaction(t_id, dd)
             all_data.append({
                 'date': t.date, 
                 'final_price': t.final_price, 
                 'customer_name': t.customer_name,
                 'product': t.product,
                 'quantity': t.quantity,
                 'status': t.status
             })

    all_data.sort(key=lambda x: x['date'], reverse=True)
    latest = all_data[:5]
    
    customers_count = len(list(db.collection('customers').stream()))
    total_stock = sum(p.stock for p in products)
    
    return render_template('index.html', total_products=len(products), total_stock=total_stock, total_customers=customers_count, latest_transactions=latest)

@app.route('/products')
@login_required
def products():
    return render_template('products.html', products=get_all_collection('products', Product))

@app.route('/reset_products')
@login_required
def reset_products():
    try:
        for col in ['transactions', 'reviews', 'favorites', 'products']:
            for doc in db.collection(col).list_documents(): doc.delete()
        flash("Semua data produk telah direset.", "success")
    except Exception as e: flash(f"Gagal reset: {e}", "danger")
    return redirect(url_for('products'))

@app.route('/add', methods=['POST', 'GET'])
@login_required
def add():
    categories = get_all_collection('categories', Category)
    
    if request.method == 'POST':
        file = request.files.get('image')
        img_b64, mtype = None, None
        
        if file and file.filename != '':
            mtype = file.mimetype
            img_b64 = base64.b64encode(file.read()).decode('utf-8')
        
        raw_price = request.form['price'].replace('.', '') 
        price = int(raw_price) if raw_price else 0
        
        cat_id = request.form.get('category_id')
        cat_name = "Umum" 
        
        if cat_id:
            cat_doc = db.collection('categories').document(cat_id).get()
            if cat_doc.exists:
                cat_name = cat_doc.to_dict().get('name')

        new_prod = {
            'name': request.form['name'],
            'price': price,
            'stock': int(request.form['stock']), 
            'description': request.form['description'],
            'category_id': cat_id, 
            'category': cat_name,   
            'image_base64': img_b64,
            'mimetype': mtype,
            'created_at': datetime.now().isoformat()
        }
        
        prod_id = generate_id()
        db.collection('products').document(prod_id).set(new_prod)
        
        flash("Produk berhasil ditambahkan.", "success")
        return redirect(url_for('products'))
        
    return render_template('add.html', categories=categories)


@app.route('/api/add_review', methods=['POST'])
def api_add_review():
    try:
        data = request.json
        user_id = data.get('user_id')
        product_id = data.get('product_id')
        rating = int(data.get('rating'))
        comment = data.get('comment', '') 
        qty = int(data.get('qty', 1))
        
        if not user_id or not product_id:
            return api_response('error', 'User ID dan Product ID wajib')

        # Ambil Data Pelanggan
        customer_name = "Pengguna Tanpa Nama"
        customer_image = ""

        if user_id:
            user_ref = db.collection('customers').document(user_id)
            user_doc = user_ref.get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                customer_name = user_data.get('name', customer_name)
                # FIX: Cek ukuran gambar user agar tidak crash di review
                c_img = user_data.get('image_base64', '')
                if len(c_img) < 200 * 1024: # Limit 200KB untuk profil
                    customer_image = c_img

        review_data = {
            'user_id': user_id,
            'customer_name': customer_name,
            'customer_image': customer_image,
            'product_id': product_id,
            'rating': rating,
            'comment': comment,
            'qty': qty,
            'created_at': datetime.now().isoformat()
        }
        db.collection('reviews').add(review_data)

        # Hitung Rata-rata Rating Baru
        reviews = db.collection('reviews').where('product_id', '==', product_id).stream()
        
        total_rating = 0
        count = 0
        for r in reviews:
            rd = r.to_dict()
            total_rating += rd.get('rating', 0)
            count += 1
            
        new_average = round(total_rating / count, 1) if count > 0 else rating

        db.collection('products').document(product_id).update({
            'rating': new_average
        })

        return api_response('success', 'Rating berhasil disimpan', {'new_rating': new_average})

    except Exception as e:
        print(f"Error Review: {e}")
        return api_response('error', str(e))

@app.route('/edit/<id>', methods=['POST', 'GET'])
@login_required
def edit(id):
    p = get_doc_by_id('products', id, Product)
    if not p:
        flash("Produk tidak ditemukan", "danger")
        return redirect(url_for('products'))
        
    categories = get_all_collection('categories', Category)
    if request.method == 'POST':
        update_data = {}
        update_data['name'] = request.form['name']
        update_data['category_id'] = request.form.get('category_id')
        raw_price = request.form['price'].replace('.', '')
        update_data['price'] = int(raw_price) if raw_price else 0
        update_data['stock'] = int(request.form['stock'])
        update_data['description'] = request.form['description']
        
        file = request.files.get('image')
        if file and file.filename != '':
            update_data['image_base64'] = base64.b64encode(file.read()).decode('utf-8')
            update_data['mimetype'] = file.mimetype
            
        db.collection('products').document(id).update(update_data)
        flash("Produk diperbarui.", "info")
        return redirect(url_for('products'))
    return render_template('edit.html', product=p, categories=categories)

@app.route('/delete/<id>')
@login_required
def delete(id):
    try:
        # Hapus data terkait dulu
        for t in db.collection('transactions').where('product_id', '==', id).stream(): t.reference.delete()
        for r in db.collection('reviews').where('product_id', '==', id).stream(): r.reference.delete()
        for f in db.collection('favorites').where('product_id', '==', id).stream(): f.reference.delete()
        
        db.collection('products').document(id).delete()
        flash("Produk dihapus.", "success")
    except Exception as e: flash(f"Gagal hapus: {e}", "warning")
    return redirect(url_for('products'))

@app.route('/product_image/<id>')
def product_image(id):
    doc = db.collection('products').document(id).get()
    if doc.exists:
        data = doc.to_dict()
        if data.get('image_base64'):
            img_data = base64.b64decode(data['image_base64'])
            return send_file(BytesIO(img_data), mimetype=data.get('mimetype', 'image/jpeg'))
    return redirect("https://via.placeholder.com/150")

@app.route('/categories', methods=['GET', 'POST'])
@login_required
def categories():
    if request.method == 'POST':
        cat_id = generate_id()
        db.collection('categories').document(cat_id).set({'name': request.form['name']})
        flash("Kategori dibuat.", "success")
        return redirect(url_for('categories'))
    return render_template('categories.html', categories=get_all_collection('categories', Category))

@app.route('/delete_category/<id>')
@login_required
def delete_category(id):
    db.collection('categories').document(id).delete()
    return redirect(url_for('categories'))

@app.route('/customers')
@login_required
def customers():
    all_cust = get_all_collection('customers', Customer)
    all_cust.sort(key=lambda x: x.points, reverse=True)
    all_hist = get_all_collection('point_redemptions', PointRedemption)
    all_hist.sort(key=lambda x: x.date, reverse=True)
    return render_template('customers.html', customers=all_cust, history=all_hist)

@app.route('/customer/<id>')
@login_required
def customer_detail(id):
    c = get_doc_by_id('customers', id, Customer)
    if not c: return redirect(url_for('customers'))
    
    trx_docs = db.collection('transactions').stream()
    trx = []
    
    for d in trx_docs:
        dd = d.to_dict()
        match = False
        if dd.get('customer_phone') == c.phone: match = True
        elif dd.get('user_id') == c.id: match = True
        
        if match:
             trx.append(Transaction(d.id, dd))
    
    trx.sort(key=lambda x: x.date, reverse=True)
    
    rev = [Review(d.id, d.to_dict()) for d in db.collection('reviews').where('customer_id', '==', id).stream()]
    fav = [Favorite(d.id, d.to_dict()) for d in db.collection('favorites').where('customer_id', '==', id).stream()]
    
    return render_template('customer_detail.html', c=c, transactions=trx, reviews=rev, favorites=fav)

@app.route('/discounts', methods=['GET', 'POST'])
@login_required
def discounts():
    if request.method == 'POST':
        v_id = generate_id()
        db.collection('vouchers').document(v_id).set({
            'code': request.form['code'].upper(),
            'discount_amount': int(request.form['amount']),
            'is_active': True
        })
        flash("Voucher dibuat.", "success")
        return redirect(url_for('discounts'))
    
    docs = db.collection('vouchers').stream()
    vouchers = [FirestoreModel(d.id, d.to_dict()) for d in docs]
    return render_template('discounts.html', vouchers=vouchers)

@app.route('/delete_discount/<id>')
@login_required
def delete_discount(id):
    db.collection('vouchers').document(id).delete()
    return redirect(url_for('discounts'))

@app.route('/transactions')
@login_required
def transactions():
    docs = db.collection('transactions').stream()
    transactions_list = []
    grouped_old_data = {}

    for doc in docs:
        data = doc.to_dict()
        
        # --- FORMAT BARU (DARI APP/WEB NESTED) ---
        if 'items' in data and isinstance(data['items'], list):
            try:
                t_obj = {
                    'date': parse_flutter_date(data.get('created_at')),
                    'queue_number': data.get('order_id', '-')[-3:] if data.get('order_id') else '-',
                    'table_number': data.get('table_number', '-'),
                    'customer_name': data.get('customer_name', 'No Name'),
                    'list_belanja': [],
                    'total_discount': int(data.get('summary', {}).get('discount', 0)),
                    'total_final': int(data.get('summary', {}).get('grand_total', 0)),
                    'total_points': 0,
                    'status': data.get('status', 'success'),
                    'payment_method': data.get('payment_method', 'Cash') 
                }
                for item in data['items']:
                    qty = int(item.get('qty', 0))
                    t_obj['list_belanja'].append({
                        'name': item.get('product_name', 'Item'),
                        'qty': qty
                    })
                if t_obj['total_final'] > 0:
                    t_obj['total_points'] = int(t_obj['total_final'] / EARN_RATE)
                
                transactions_list.append(t_obj)
            except Exception as e:
                print(f"Error parsing new format {doc.id}: {e}")

        # --- FORMAT LAMA (FLAT) ---
        else:
            t = Transaction(doc.id, data)
            group_key = (str(t.date), t.customer_phone, str(t.queue_number or '-'))
            
            if group_key not in grouped_old_data:
                grouped_old_data[group_key] = {
                    'date': t.date,
                    'queue_number': t.queue_number or '-',
                    'table_number': t.table_number or '-',
                    'customer_name': t.customer_name,
                    'list_belanja': [],
                    'total_discount': 0, 'total_final': 0, 'total_points': 0,
                    'status': t.status,
                    'payment_method': 'Cash'
                }
            
            prod_name = t.product.name if t.product else 'Produk Terhapus'
            qty = int(t.quantity or 0)
            
            grouped_old_data[group_key]['list_belanja'].append({'name': prod_name, 'qty': qty})
            grouped_old_data[group_key]['total_discount'] += int(t.discount_voucher or 0)
            grouped_old_data[group_key]['total_final'] += int(t.final_price or 0)
            grouped_old_data[group_key]['total_points'] += int(t.points_earned or 0)

    transactions_list.extend(grouped_old_data.values())
    transactions_list.sort(key=lambda x: x['date'], reverse=True)
    
    return render_template('transactions.html', transactions=transactions_list)

@app.route('/profile')
@login_required
def profile():
    docs = db.collection('transactions').stream()
    trx = []
    for d in docs:
        trx.append(Transaction(d.id, d.to_dict()))
    trx.sort(key=lambda x: x.date, reverse=True)
    return render_template('profile.html', transactions=trx[:10])

@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    old = request.form['old_password']
    new = request.form['new_password']
    confirm = request.form['confirm_password']

    if not current_user.check_password(old):
        flash("Password lama salah.", "danger")
        return redirect(url_for('profile'))

    if new != confirm:
        flash("Konfirmasi password tidak cocok.", "danger")
        return redirect(url_for('profile'))

    current_user.set_password(new)
    db.collection('users').document(current_user.id).update({'password_hash': current_user._data['password_hash']})
    flash("Password berhasil diubah!", "success")
    return redirect(url_for('profile'))

@app.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    data = {'full_name': request.form['full_name'], 'email': request.form['email'], 'address': request.form['address']}
    db.collection('users').document(current_user.id).update(data)
    current_user._data.update(data)
    flash("Profil diperbarui.", "success")
    return redirect(url_for('profile'))

# [WEB ADMIN: SIMPAN TRANSAKSI & KURANGI STOK]
@app.route('/add_transaction', methods=['GET', 'POST'])
@login_required
def add_transaction():
    products = get_all_collection('products', Product)
    categories = get_all_collection('categories', Category)
    
    if request.method == 'POST':
        try:
            c_name = request.form['customer_name']
            c_phone = request.form['customer_phone']
            c_addr = request.form['customer_address']
            pay = request.form['payment_method']
            table_num = request.form.get('table_number', '-') 
            ivoucher = request.form.get('voucher_code', '').strip().upper()
            
            cart_json = request.form.get('cart_data')
            if not cart_json:
                flash("Keranjang kosong!", "danger")
                return redirect(url_for('add_transaction'))
            
            cart_items = json.loads(cart_json) 
            total_gross = 0
            product_map = {}
            
            # --- AGREGASI ITEM (PENTING) ---
            aggregated_items = {}
            for item in cart_items:
                pid = str(item['id'])
                qty = int(item['qty'])
                prod = get_doc_by_id('products', pid, Product)
                if not prod or prod.stock < qty:
                    flash(f"Stok produk {pid} tidak cukup/valid.", "danger")
                    return redirect(url_for('add_transaction'))
                
                product_map[pid] = prod
                total_gross += prod.price * qty

                if pid in aggregated_items: aggregated_items[pid]['qty'] += qty
                else: aggregated_items[pid] = {'qty': qty, 'name': prod.name, 'price': prod.price}

            disc_voucher_total = 0
            code = None
            if ivoucher:
                v_docs = db.collection('vouchers').where('code', '==', ivoucher).where('is_active', '==', True).stream()
                for doc in v_docs:
                    v = doc.to_dict()
                    disc_voucher_total = v['discount_amount']
                    code = ivoucher
                    break
            if disc_voucher_total > total_gross: disc_voucher_total = total_gross

            final_total_transaksi = total_gross - disc_voucher_total
            total_earn = int(final_total_transaksi / EARN_RATE)
            
            cust_ref = db.collection('customers').where('phone', '==', c_phone).limit(1).stream()
            cust_found = False
            for d in cust_ref:
                d.reference.update({'points': d.to_dict().get('points', 0) + total_earn})
                cust_found = True
                break
            
            if not cust_found:
                new_cust_id = generate_id()
                db.collection('customers').document(new_cust_id).set({
                    'name': c_name, 'phone': c_phone, 'address': c_addr, 'points': total_earn, 'email': ''
                })

            batch = db.batch()
            new_trx_id = "TRX-" + generate_id()
            new_queue = str(random.randint(1, 999)).zfill(3)
            now_time = datetime.now()
            
            trx_items_list = []
            
            for pid, info in aggregated_items.items():
                qty = info['qty']
                trx_items_list.append({
                    'product_id': pid,
                    'product_name': info['name'],
                    'price': info['price'],
                    'qty': qty,
                    'note': ''
                })
                prod_ref = db.collection('products').document(pid)
                batch.update(prod_ref, {'stock': firestore.Increment(-qty)})

            trx_ref = db.collection('transactions').document(new_trx_id)
            trx_data = {
                'order_id': new_trx_id,
                'created_at': now_time.isoformat(),
                'date': now_time.isoformat(),
                'customer_name': c_name,
                'customer_phone': c_phone,
                'customer_address': c_addr,
                'queue_number': new_queue,
                'table_number': table_num,
                'payment_method': pay,
                'voucher_code': code,
                'items': trx_items_list,
                'status': 'success', # [PERBAIKAN] Force success
                'summary': {
                    'sub_total': total_gross,
                    'discount': disc_voucher_total,
                    'grand_total': final_total_transaksi,
                    'tax': 0
                }
            }
            
            batch.set(trx_ref, trx_data)
            batch.commit()
            
            flash(f"Transaksi Berhasil! Antrian: {new_queue}, Total: Rp {final_total_transaksi:,}", "success")
            return redirect(url_for('transactions'))

        except Exception as e:
            flash(f"Error: {e}", "danger")
            return redirect(url_for('add_transaction'))
            
    return render_template('add_transaction.html', products=products, categories=categories)

# --- BAGIAN BANNERS ---
@app.route('/banners')
@login_required
def banners():
    docs = db.collection('banners').stream()
    banners = [FirestoreModel(d.id, d.to_dict()) for d in docs]
    return render_template('banners.html', banners=banners)

@app.route('/add_banner', methods=['POST'])
@login_required
def add_banner():
    file = request.files['image']
    if file:
        img_b64 = base64.b64encode(file.read()).decode('utf-8')
        b_id = generate_id()
        db.collection('banners').document(b_id).set({
            'title': request.form.get('title'), 
            'image_base64': img_b64, 'mimetype': file.mimetype, 'is_active': True
        })
        flash("Banner ditambahkan.", "success")
    else: flash("File gambar wajib diisi.", "danger")
    return redirect(url_for('banners'))

@app.route('/edit_banner', methods=['POST'])
@login_required
def edit_banner():
    try:
        b_id = request.form.get('banner_id')
        data = {
            'title': request.form.get('title'),
            'is_active': True if request.form.get('is_active') else False
        }
        file = request.files.get('image')
        if file and file.filename != '':
            data['image_base64'] = base64.b64encode(file.read()).decode('utf-8')
            data['mimetype'] = file.mimetype
        db.collection('banners').document(b_id).update(data)
        flash("Banner diperbarui.", "success")
    except Exception as e: flash(f"Gagal: {e}", "danger")
    return redirect(url_for('banners'))

@app.route('/delete_banner/<id>')
@login_required
def delete_banner(id):
    db.collection('banners').document(id).delete()
    return redirect(url_for('banners'))

@app.route('/banner_image/<id>')
def banner_image(id):
    doc = db.collection('banners').document(id).get()
    if doc.exists:
        data = doc.to_dict()
        if data.get('image_base64'):
            img_data = base64.b64decode(data['image_base64'])
            return send_file(BytesIO(img_data), mimetype=data.get('mimetype', 'image/jpeg'))
    return redirect("https://via.placeholder.com/300x150")

@app.route('/analytics')
@login_required
def analytics():
    all_trx = get_all_collection('transactions', Transaction)
    daily_sales = {}
    peak_hours = {}
    
    for t in all_trx:
        d_str = t.date.strftime('%Y-%m-%d')
        daily_sales[d_str] = daily_sales.get(d_str, 0) + int(t.final_price or 0)
        
        h = t.date.hour
        k = f"{h}:00"
        peak_hours[k] = peak_hours.get(k, 0) + 1
        
    sorted_dates = sorted(daily_sales.keys(), reverse=True)[:7]
    chart_dates = sorted_dates[::-1]
    chart_revenue = [daily_sales[d] for d in chart_dates]

    return render_template('analytics.html', 
                           dates=json.dumps(chart_dates), 
                           revenue=json.dumps(chart_revenue),
                           peak_hours=peak_hours, insights=[], campaigns=[])

@app.route('/marketing', methods=['GET', 'POST'])
@login_required
def marketing():
    if request.method == 'POST':
        pid = generate_id()
        db.collection('social_posts').document(pid).set({
            'platform': request.form['platform'], 'content': request.form['content'],
            'schedule_time': request.form['schedule_time'], 'status': 'Scheduled'
        })
        flash("Postingan dijadwalkan!", "success")
        return redirect(url_for('marketing'))
    
    posts = get_all_collection('social_posts', SocialPost)
    return render_template('marketing.html', posts=posts)

@app.route('/delete_post/<id>')
@login_required
def delete_post(id):
    db.collection('social_posts').document(id).delete()
    return redirect(url_for('marketing'))

@app.route('/reviews')
@login_required
def reviews():
    revs = get_all_collection('reviews', Review)
    revs.sort(key=lambda x: x.created_at, reverse=True)
    return render_template('reviews.html', reviews=revs)

@app.route('/delete_review/<id>')
@login_required
def delete_review(id):
    db.collection('reviews').document(id).delete()
    return redirect(url_for('reviews'))

@app.route('/favorites')
@login_required
def favorites():
    favs = get_all_collection('favorites', Favorite)
    favs.sort(key=lambda x: x.created_at, reverse=True)
    return render_template('favorites.html', favorites=favs)

@app.route('/update_customer', methods=['POST'])
@login_required
def update_customer():
    cid = request.form.get('customer_id')
    try:
        data = {
            'name': request.form.get('name'), 'phone': request.form.get('phone'),
            'email': request.form.get('email'), 'address': request.form.get('address')
        }
        if request.form.get('password'):
            data['password'] = generate_password_hash(request.form.get('password'))
        db.collection('customers').document(cid).update(data)
        flash("Pelanggan diperbarui.", "success")
    except Exception as e: flash(f"Error: {e}", "danger")
    return redirect(url_for('customer_detail', id=cid))

# [ROUTE REDEEM POINTS]
@app.route('/redeem_points', methods=['POST'])
@login_required
def redeem_points():
    cid = request.form.get('customer_id')
    pts = int(request.form.get('points_to_redeem'))
    desc = request.form.get('description')
    
    c_doc = db.collection('customers').document(cid).get()
    if c_doc.exists:
        curr = c_doc.to_dict().get('points', 0)
        if curr >= pts:
            db.collection('customers').document(cid).update({'points': curr - pts})
            rid = generate_id()
            db.collection('point_redemptions').document(rid).set({
                'customer_id': cid, 
                'points_spent': pts, 
                'description': desc, 
                'date': datetime.now().isoformat()
            })
            flash(f"Tukar {pts} poin berhasil.", "success")
        else:
            flash("Poin tidak cukup.", "danger")
    return redirect(url_for('customers'))

# ==========================================
# 4. API SERVICE
# ==========================================

def api_response(status, message, data=None):
    return jsonify({'status': status, 'message': message, 'data': data})

@app.route('/api/products', methods=['GET'])
def api_get_products():
    try:
        docs = db.collection('products').stream()
        all_products = []
        for doc in docs:
            p = doc.to_dict()
            p['id'] = doc.id
            if 'image_base64' in p: del p['image_base64'] 
            all_products.append(p)
            
        return api_response('success', 'Data produk ditemukan', all_products)
    except Exception as e:
        return api_response('error', str(e))

@app.route('/api/categories', methods=['GET'])
def api_categories():
    try:
        docs = db.collection('categories').stream()
        data = [{'id': d.id, 'name': d.to_dict().get('name')} for d in docs]
        return api_response('success', 'Data kategori berhasil', data)
    except Exception as e:
        return api_response('error', str(e))

@app.route('/api/products/<product_id>', methods=['GET'])
def api_product_detail(product_id):
    try:
        doc = db.collection('products').document(product_id).get()
        if not doc.exists:
            return api_response('error', 'Produk tidak ditemukan')
        
        p = doc.to_dict()
        p['id'] = doc.id
        if 'image_base64' in p: del p['image_base64'] 
        
        p['image_url'] = url_for('api_product_image', product_id=doc.id, _external=True)

        customer_id = request.args.get('customer_id')
        is_favorite = False
        if customer_id:
            favs = db.collection('favorites').where('product_id', '==', product_id)\
                     .where('customer_id', '==', customer_id).limit(1).stream()
            for _ in favs:
                is_favorite = True
                break
        
        p['is_favorite'] = is_favorite

        return api_response('success', 'Detail produk ditemukan', p)
    except Exception as e:
        return api_response('error', str(e))
    
@app.route('/api/product_image/<product_id>')
def api_product_image(product_id):
    try:
        doc = db.collection('products').document(product_id).get()
        if doc.exists:
            data = doc.to_dict()
            if data.get('image_base64'):
                img_data = base64.b64decode(data['image_base64'])
                return send_file(BytesIO(img_data), mimetype=data.get('mimetype', 'image/jpeg'))
    except Exception:
        pass
    return redirect("https://via.placeholder.com/300?text=No+Image")


@app.route('/api/banners', methods=['GET'])
def api_banners():
    docs = db.collection('banners').where('is_active', '==', True).stream()
    data = [{'id': d.id, 'title': d.to_dict().get('title'), 'image_url': url_for('banner_image', id=d.id, _external=True)} for d in docs]
    return api_response('success', 'Data banner berhasil', data)

@app.route('/api/loginpengguna', methods=['POST'])
def loginpengguna():
    try:
        data = request.get_json(silent=True)
        email = data.get('email') 
        password = data.get('password')
        
        docs = db.collection('customers').where('email', '==', email).limit(1).stream()
        user = None
        for d in docs: 
            user = Customer(d.id, d.to_dict())
            break
        
        if user and user._data.get('password'):
            if check_password_hash(user._data['password'], password):
                return jsonify({
                    'status': 'success', 
                    'message': 'Login Berhasil',
                    'data': {
                        'id': user.id,
                        'name': user.name, 
                        'email': user.email, 
                        'phone': user.phone,
                        'role': user._data.get('role', 'Member'),
                        'points': user.points
                    }
                })
        return jsonify({'status': 'error', 'message': 'Email atau password salah'})
    except Exception as e: 
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/api/registerpengguna', methods=['POST'])
def api_register():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        name = data.get('name', 'User Baru')
        phone = data.get('phone', '-')

        hashed_password = generate_password_hash(password)
        user_uid = None
        
        try:
            user_auth = auth.get_user_by_email(email)
            doc = db.collection('customers').document(user_auth.uid).get()
            if doc.exists:
                return api_response('error', 'Email sudah terdaftar. Silakan Login.')
            else:
                user_uid = user_auth.uid
        except auth.UserNotFoundError:
            new_user = auth.create_user(email=email, password=password, display_name=name)
            user_uid = new_user.uid

        user_data = {
            'id': user_uid,
            'name': name,
            'email': email,
            'phone': phone,
            'role': 'Member',
            'points': 0,
            'password': hashed_password,
            'created_at': datetime.now().isoformat()
        }
        db.collection('customers').document(user_uid).set(user_data)
        return api_response('success', 'Registrasi Berhasil', user_data)
    except Exception as e:
        return api_response('error', f"Gagal Daftar: {str(e)}")
    
@app.route('/api/vouchers', methods=['GET'])
def api_vouchers():
    try:
        docs = db.collection('vouchers').where('is_active', '==', True).stream()
        data = []
        for d in docs:
            v = d.to_dict()
            data.append({
                'id': d.id,
                'code': v.get('code'),
                'discount_amount': v.get('discount_amount'),
                'description': f"Potongan Rp {v.get('discount_amount'):,}"
            })
        return api_response('success', 'Data voucher berhasil', data)
    except Exception as e:
        return api_response('error', str(e))

@app.route('/api/rewards', methods=['GET'])
def api_rewards():
    try:
        products = get_all_collection('products', Product)
        data = []
        for p in products:
            poin_cost = int(p.price / 100) 
            if p.price <= 50000: 
                data.append({
                    'id': p.id,
                    'title': p.name,
                    'description': p.description or 'Tukar poinmu dengan ini!',
                    'point_cost': poin_cost,
                    'image_url': url_for('product_image', id=p.id, _external=True),
                    'stock': p.stock
                })
        return api_response('success', 'Data rewards berhasil', data)
    except Exception as e:
        return api_response('error', str(e))

@app.route('/api/user_points/<user_id>', methods=['GET'])
def api_user_points(user_id):
    try:
        # Cari dokumen user di collection 'customers'
        doc = db.collection('customers').document(str(user_id)).get()
        
        if doc.exists:
            data = doc.to_dict()
            # Ambil field 'points', default 0 jika tidak ada
            current_points = data.get('points', 0)
            return api_response('success', 'Poin ditemukan', {'points': current_points})
        else:
            return api_response('error', 'User tidak ditemukan')
            
    except Exception as e:
        return api_response('error', str(e))
    
# [API HISTORY PENUKARAN POIN]
@app.route('/api/point_history/<user_id>', methods=['GET'])
def api_point_history(user_id):
    try:
        print(f"DEBUG: Mengambil History untuk User ID: {user_id}")

        # 1. Query ke collection 'point_redemptions'
        # Filter berdasarkan field 'customer_id'
        docs = db.collection('point_redemptions')\
                 .where('customer_id', '==', str(user_id))\
                 .stream()
        
        history_data = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id # Sertakan ID dokumen
            
            # Pastikan field penting ada (untuk mencegah error di aplikasi)
            if 'description' not in data: data['description'] = 'Penukaran Poin'
            if 'points_spent' not in data: data['points_spent'] = 0
            if 'date' not in data: data['date'] = ''
            
            history_data.append(data)
            
        # 2. Urutkan dari yang Paling Baru (Descending by date)
        history_data.sort(key=lambda x: x.get('date', ''), reverse=True)

        return api_response('success', 'Data riwayat ditemukan', history_data)

    except Exception as e:
        print(f"Error History API: {e}")
        return api_response('error', str(e))
    
@app.route('/api/redeem_via_scan', methods=['POST'])
def api_redeem_via_scan():
    try:
        data = request.json
        user_id = data.get('user_id')
        points_to_deduct = int(data.get('points', 0))
        item_name = data.get('item_name', 'Scan QR Redemption')

        if not user_id or points_to_deduct <= 0:
            return api_response('error', 'Data tidak valid')

        # 1. Cek User & Poin Cukup?
        user_ref = db.collection('customers').document(user_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return api_response('error', 'User tidak ditemukan')

        current_points = user_doc.to_dict().get('points', 0)

        if current_points < points_to_deduct:
            return api_response('error', f'Poin tidak cukup. Anda punya {current_points}, butuh {points_to_deduct}.')

        # 2. Kurangi Poin & Simpan History (Batch Write agar aman)
        batch = db.batch()

        # Update Poin User
        batch.update(user_ref, {'points': firestore.Increment(-points_to_deduct)})

        # Simpan History Penukaran
        history_ref = db.collection('point_redemptions').document()
        history_data = {
            'customer_id': user_id,
            'points_spent': points_to_deduct,
            'description': f"Scan QR: {item_name}",
            'date': datetime.now().isoformat()
        }
        batch.set(history_ref, history_data)

        batch.commit()

        return api_response('success', 'Penukaran Berhasil!', {'sisa_poin': current_points - points_to_deduct})

    except Exception as e:
        print(f"Error Scan Redeem: {e}")
        return api_response('error', str(e))
    
@app.route('/api/update_profile', methods=['POST'])
def api_update_profile():
    try:
        user_id = request.form.get('user_id')
        if not user_id: return api_response('error', 'User ID tidak ditemukan')

        update_data = {
            'name': request.form.get('name'),
            'email': request.form.get('email')
        }
        password = request.form.get('password')
        if password and len(password) > 0:
            update_data['password'] = generate_password_hash(password)

        file = request.files.get('avatar')
        if file and file.filename != '':
            img_b64 = base64.b64encode(file.read()).decode('utf-8')
            update_data['image_base64'] = img_b64
            update_data['mimetype'] = file.mimetype

        doc_ref = db.collection('customers').document(user_id)
        if not doc_ref.get().exists: return api_response('error', 'User tidak ditemukan di database')
            
        doc_ref.update(update_data)
        return api_response('success', 'Profil berhasil diperbarui', update_data)
    except Exception as e:
        return api_response('error', f"Gagal update: {str(e)}")

@app.route('/api/customer_image/<id>')
def customer_image(id):
    try:
        doc = db.collection('customers').document(id).get()
        if doc.exists:
            data = doc.to_dict()
            if data.get('image_base64'):
                img_data = base64.b64decode(data['image_base64'])
                return send_file(BytesIO(img_data), mimetype=data.get('mimetype', 'image/jpeg'))
    except Exception: pass
    return redirect("https://cdn.pixabay.com/photo/2015/10/05/22/37/blank-profile-picture-973460_960_720.png")

@app.route('/api/transaction_history/<user_id>', methods=['GET'])
def api_transaction_history(user_id):
    try:
        # 1. Ambil daftar Produk ID yang SUDAH direview
        reviewed_pids = []
        reviews_ref = db.collection('reviews').where('user_id', '==', str(user_id)).stream()
        for doc in reviews_ref:
            rev = doc.to_dict()
            reviewed_pids.append(str(rev.get('product_id')))

        # 2. Ambil Transaksi
        transactions = []
        docs_1 = db.collection('transactions').where('user_id', '==', str(user_id)).stream()
        for d in docs_1:
            t = d.to_dict()
            t['id'] = d.id
            transactions.append(t)
            
        docs_2 = db.collection('transactions').where('customer_id', '==', str(user_id)).stream()
        for d in docs_2:
            if not any(x['id'] == d.id for x in transactions):
                t = d.to_dict()
                t['id'] = d.id
                transactions.append(t)

        # 3. Inject status 'has_reviewed'
        for trx in transactions:
            if 'items' in trx and isinstance(trx['items'], list):
                for item in trx['items']:
                    pid = str(item.get('product_id') or item.get('id') or '')
                    item['has_reviewed'] = pid in reviewed_pids

        transactions.sort(key=lambda x: x.get('created_at', x.get('date', '')), reverse=True)
        return api_response('success', 'Data riwayat berhasil', transactions)

    except Exception as e:
        return api_response('error', str(e))

# [MOBILE API] Endpoint Checkout (Kurangi Stok, Simpan Transaksi & Update Poin)
@app.route('/api/checkout', methods=['POST'])
def api_checkout():
    try:
        data = request.json
        print(f"DEBUG: Data Checkout Masuk: {data}")

        items = data.get('items', [])
        if not items:
            return api_response('error', 'Keranjang kosong')

        batch = db.batch()
        
        # 1. AGREGASI ITEM
        aggregated_items = {}
        for item in items:
            pid = str(item.get('product_id') or item.get('id')).strip()
            qty = int(item.get('qty') or item.get('quantity') or 0)
            if qty <= 0 or not pid: continue

            if pid in aggregated_items: aggregated_items[pid] += qty
            else: aggregated_items[pid] = qty

        # 2. VALIDASI & UPDATE STOK & HITUNG TOTAL (Server-Side)
        trx_items_list = []
        total_gross = 0 
        
        for pid, total_qty in aggregated_items.items():
            prod_ref = db.collection('products').document(pid)
            prod_doc = prod_ref.get()
            
            if not prod_doc.exists:
                return api_response('error', f'Produk ID {pid} tidak ditemukan!')
            
            prod_data = prod_doc.to_dict()
            price = int(prod_data.get('price', 0))
            current_stock = int(prod_data.get('stock', 0))
            
            if current_stock < total_qty:
                return api_response('error', f"Stok {prod_data.get('name')} tidak cukup (Sisa: {current_stock})")

            # Hitung subtotal item secara akurat di server
            total_gross += price * total_qty
            
            # --- [FIX CRASH] CEK UKURAN GAMBAR ---
            # Jika gambar terlalu besar (> 100KB), JANGAN simpan ke history transaksi
            # agar dokumen tidak melebihi 1MB limit.
            raw_img = prod_data.get('image_base64', '')
            safe_img = raw_img if len(raw_img) < 100 * 1024 else "" # Simpan string kosong jika berat

            trx_items_list.append({
                'product_id': pid,
                'product_name': prod_data.get('name'),
                'price': price,
                'qty': total_qty,
                'category': prod_data.get('category', '-'),
                'image_base64': safe_img, # Pake gambar aman
            })
            
            batch.update(prod_ref, {'stock': firestore.Increment(-total_qty)})
        
        # 3. HITUNG DISKON & GRAND TOTAL
        discount_amount = 0
        voucher_code = data.get('voucher_code')
        
        if 'summary' in data and 'discount' in data['summary']:
             discount_amount = int(data['summary']['discount'])

        grand_total = total_gross - discount_amount
        if grand_total < 0: grand_total = 0
        
        points_earned = int(grand_total / EARN_RATE)

        # 4. DATA PELANGGAN (AUTO FILL)
        user_id = data.get('user_id') or data.get('customer_id')
        customer_name = data.get('customer_name', 'Pelanggan Umum')
        
        if user_id:
            user_ref = db.collection('customers').document(user_id)
            user_doc = user_ref.get()
            
            if user_doc.exists:
                user_data = user_doc.to_dict()
                customer_name = user_data.get('name', customer_name)
                # Update Poin
                batch.update(user_ref, {'points': firestore.Increment(points_earned)})

        # 5. SIMPAN TRANSAKSI
        trx_id = data.get('order_id') or f"TRX-{generate_id()}"
        trx_ref = db.collection('transactions').document(trx_id)
        
        final_data = {
            'order_id': trx_id,
            'user_id': user_id,
            'customer_name': customer_name, # Pastikan ini tersimpan
            'table_number': data.get('table_number', '-'),
            'voucher_code': voucher_code,
            'payment_method': data.get('payment_method', 'Cash'),
            'status': 'success',
            'created_at': datetime.now().isoformat(),
            'items': trx_items_list,
            'summary': {
                'sub_total': total_gross,
                'discount': discount_amount,
                'grand_total': grand_total,
                'tax': 0
            },
            'points_earned': points_earned
        }
            
        batch.set(trx_ref, final_data)
        batch.commit()
        
        print(f"DEBUG: Transaksi Sukses {trx_id} | Total: {grand_total}")
        return api_response('success', 'Transaksi berhasil', {'order_id': trx_id})

    except Exception as e:
        print(f"Error Transaction API: {e}")
        return api_response('error', str(e))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)