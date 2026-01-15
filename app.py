from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify, session
# Hapus komponen MySQL/SQLAlchemy
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
# Pastikan file 'serviceAccountKey.json' ada di folder yang sama
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
        print("✅ Firebase Admin & Firestore berhasil diinisialisasi.")
    except Exception as e:
        print(f"⚠️ Gagal inisialisasi Firebase: {e}")

db = firestore.client()
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# ==========================================
# 1. GENERATOR ID ANGKA (PENGGANTI UUID)
# ==========================================
def generate_id():
    """
    Menghasilkan ID string angka unik berbasis waktu.
    Format: Timestamp detik (10 digit) + 3 digit acak.
    Contoh hasil: '1705221234567'
    """
    timestamp = int(time.time())
    random_part = random.randint(100, 999)
    return f"{timestamp}{random_part}"

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

class Customer(FirestoreModel):
    @property
    def points(self): return int(self._data.get('points', 0))

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
        d = self._data.get('date')
        if isinstance(d, str):
            try: return datetime.fromisoformat(d)
            except: pass
        return datetime.now()

class Review(FirestoreModel):
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
        d = self._data.get('created_at')
        try: return datetime.fromisoformat(str(d))
        except: return datetime.now()

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
        d = self._data.get('date')
        try: return datetime.fromisoformat(str(d))
        except: return datetime.now()

EARN_RATE = 5000 

def get_all_collection(collection_name, model_class):
    docs = db.collection(collection_name).stream()
    return [model_class(doc.id, doc.to_dict()) for doc in docs]

def get_doc_by_id(collection_name, doc_id, model_class):
    doc = db.collection(collection_name).document(str(doc_id)).get()
    if doc.exists: return model_class(doc.id, doc.to_dict())
    return None

# ==========================================
# 3. ROUTES
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
        # PENGGUNAAN ID MANUAL
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
    all_trx = [Transaction(d.id, d.to_dict()) for d in trx_docs]
    all_trx.sort(key=lambda x: x.date, reverse=True)
    latest = all_trx[:5]
    
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
        
        new_prod = {
            'name': request.form['name'], 
            'category_id': request.form.get('category_id'), 
            'price': price,
            'stock': int(request.form['stock']), 
            'description': request.form['description'],
            'image_base64': img_b64, 'mimetype': mtype
        }
        
        # PENGGUNAAN ID MANUAL
        prod_id = generate_id()
        db.collection('products').document(prod_id).set(new_prod)
        
        flash("Produk ditambah.", "success")
        return redirect(url_for('products'))
    return render_template('add.html', categories=categories)

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
        # Cascade delete manual
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
    
    trx = [Transaction(d.id, d.to_dict()) for d in db.collection('transactions').where('customer_phone', '==', c.phone).stream()]
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
    raw_transactions = get_all_collection('transactions', Transaction)
    raw_transactions.sort(key=lambda x: x.date, reverse=True)
    
    grouped_data = {}
    for t in raw_transactions:
        # Grouping key
        group_key = (str(t.date), t.customer_phone, str(t.queue_number or '-'))
        
        if group_key not in grouped_data:
            grouped_data[group_key] = {
                'date': t.date,
                'queue_number': t.queue_number or '-',
                'table_number': t.table_number or '-',
                'customer_name': t.customer_name,
                'list_belanja': [],
                'total_discount': 0, 'total_final': 0, 'total_points': 0
            }
        
        prod_name = t.product.name if t.product else 'Produk Terhapus'
        grouped_data[group_key]['list_belanja'].append({'name': prod_name, 'qty': int(t.quantity or 0)})
        grouped_data[group_key]['total_discount'] += int(t.discount_voucher or 0)
        grouped_data[group_key]['total_final'] += int(t.final_price or 0)
        grouped_data[group_key]['total_points'] += int(t.points_earned or 0)

    transactions_list = list(grouped_data.values())
    transactions_list.sort(key=lambda x: x['date'], reverse=True)
    return render_template('transactions.html', transactions=transactions_list)

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
            
            for item in cart_items:
                pid = str(item['id'])
                qty = int(item['qty'])
                prod = get_doc_by_id('products', pid, Product)
                if not prod or prod.stock < qty:
                    flash(f"Stok produk {pid} tidak cukup/valid.", "danger")
                    return redirect(url_for('add_transaction'))
                product_map[pid] = prod
                total_gross += prod.price * qty

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
            
            # Upsert Customer
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

            new_queue = str(random.randint(1, 999)).zfill(3)
            remaining_disc = disc_voucher_total
            now_time = datetime.now()
            batch = db.batch()
            
            for index, item in enumerate(cart_items):
                pid = str(item['id'])
                qty = int(item['qty'])
                prod = product_map[pid]
                item_gross = prod.price * qty
                
                if total_gross > 0:
                    if index == len(cart_items) - 1: item_disc = remaining_disc
                    else:
                        item_disc = int((item_gross / total_gross) * disc_voucher_total)
                        remaining_disc -= item_disc
                else: item_disc = 0
                
                item_final = item_gross - item_disc
                
                # Update Stock
                prod_ref = db.collection('products').document(pid)
                batch.update(prod_ref, {'stock': prod.stock - qty})
                
                # Add Transaction (ID MANUAL)
                # Tambahkan random suffix agar unik per item dalam 1 transaksi
                trx_id = generate_id() + str(index) 
                trx_ref = db.collection('transactions').document(trx_id)
                
                batch.set(trx_ref, {
                    'product_id': pid, 'customer_name': c_name, 'customer_phone': c_phone, 'customer_address': c_addr,
                    'quantity': qty, 'total_price': item_gross, 
                    'voucher_code': code if item_disc > 0 else None, 
                    'discount_voucher': item_disc,
                    'points_earned': int(item_final / EARN_RATE),
                    'final_price': item_final, 'payment_method': pay,
                    'table_number': table_num, 'queue_number': new_queue,
                    'date': now_time.isoformat()
                })

            batch.commit()
            flash(f"Transaksi Berhasil! Antrian: {new_queue}, Total: Rp {final_total_transaksi:,}", "success")
            return redirect(url_for('transactions'))

        except Exception as e:
            flash(f"Error: {e}", "danger")
            return redirect(url_for('add_transaction'))
            
    return render_template('add_transaction.html', products=products, categories=categories)

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

@app.route('/profile')
@login_required
def profile():
    docs = db.collection('transactions').stream()
    trx = [Transaction(d.id, d.to_dict()) for d in docs]
    trx.sort(key=lambda x: x.date, reverse=True)
    return render_template('profile.html', transactions=trx[:10])

@app.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    data = {'full_name': request.form['full_name'], 'email': request.form['email'], 'address': request.form['address']}
    db.collection('users').document(current_user.id).update(data)
    current_user._data.update(data)
    flash("Profil diperbarui.", "success")
    return redirect(url_for('profile'))

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
                'customer_id': cid, 'points_spent': pts, 'description': desc, 'date': datetime.now().isoformat()
            })
            flash(f"Tukar {pts} poin berhasil.", "success")
        else: flash("Poin tidak cukup.", "danger")
    return redirect(url_for('customers'))

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
    
    posts = get_all_collection('social_posts', FirestoreModel)
    return render_template('marketing.html', posts=posts)

@app.route('/delete_post/<id>')
@login_required
def delete_post(id):
    db.collection('social_posts').document(id).delete()
    return redirect(url_for('marketing'))

# ==========================================
# 4. API SERVICE
# ==========================================

def api_response(status, message, data=None):
    return jsonify({'status': status, 'message': message, 'data': data})

@app.route('/api/products', methods=['GET'])
def api_products():
    try:
        products = get_all_collection('products', Product)
        data = []
        for p in products:
            data.append({
                'id': p.id, 'name': p.name, 'category': p.category.name if p.category else 'Umum',
                'price': p.price, 'stock': p.stock, 'description': p.description,
                'image_url': url_for('product_image', id=p.id, _external=True) 
            })
        return api_response('success', 'Data produk berhasil', data)
    except Exception as e: return api_response('error', str(e))

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
        for d in docs: user = Customer(d.id, d.to_dict()); break
        
        if user and user._data.get('password'):
            if check_password_hash(user._data['password'], password):
                return jsonify({
                    'status': 'success', 'message': 'Login Berhasil',
                    'data': {'user_id': user.id, 'name': user.name, 'email': user.email, 'points': user.points}
                })
        return jsonify({'status': 'error', 'message': 'Email atau password salah'})
    except Exception as e: return jsonify({'status': 'error', 'message': str(e)})

@app.route('/api/registerpengguna', methods=['POST'])
def api_register():
    try:
        # 1. Ambil Data dari Flutter
        data = request.get_json()
        if not data:
            return api_response('error', 'Data tidak boleh kosong')

        email = data.get('email')
        password = data.get('password')
        name = data.get('name', 'User Baru')
        phone = data.get('phone', '-')

        # 2. VALIDASI: Cek apakah user sudah ada di Firebase Auth?
        try:
            # Coba cari user by email
            user_check = auth.get_user_by_email(email)
            # Jika baris ini berhasil (tidak error), berarti USER SUDAH ADA.
            # Maka kita harus MENOLAK registrasi.
            return api_response('error', 'Email sudah terdaftar. Silakan Login.')
        except auth.UserNotFoundError:
            # Jika error "UserNotFoundError", BERARTI AMAN (User belum ada).
            # Lanjut buat user baru.
            pass

        # 3. Buat User Baru di Authentication
        user = auth.create_user(
            email=email,
            password=password,
            display_name=name
        )

        # 4. Simpan Data Profil ke Firestore (Database)
        # Gunakan UID dari auth sebagai ID dokumen agar sinkron
        user_data = {
            'id': user.uid, # Simpan ID juga di dalam field
            'name': name,
            'email': email,
            'phone': phone,
            'role': 'Member',
            'points': 0, # Default 0 (Jangan Null)
            'created_at': datetime.now().isoformat()
        }
        
        # .set() akan menimpa/membuat baru dengan rapi
        db.collection('customers').document(user.uid).set(user_data)

        # 5. Kembalikan Data Asli ke Flutter (Supaya bisa langsung Auto-Login)
        return api_response('success', 'Registrasi Berhasil', user_data)

    except Exception as e:
        print(f"Register Error: {e}")
        return api_response('error', f"Gagal Daftar: {str(e)}")

@app.route('/api/vouchers', methods=['GET'])
def api_vouchers():
    try:
        # Ambil voucher yang aktif saja
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

# 2. API UNTUK LIST HADIAH PENUKARAN POIN (REWARDS)
@app.route('/api/rewards', methods=['GET'])
def api_rewards():
    try:
        # PENTING: Karena belum ada menu Admin Rewards, kita ambil dari collection 'products'
        # yang harganya di bawah 50.000 sebagai contoh barang yang bisa ditukar poin.
        # Atau Anda bisa membuat collection 'rewards' manual di Firestore.
        
        products = get_all_collection('products', Product)
        data = []
        for p in products:
            # Logika konversi: Harga / 100 = Poin yang dibutuhkan
            poin_cost = int(p.price / 100) 
            
            # Hanya tampilkan produk murah sebagai reward
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

# 3. API CEK POIN USER TERBARU
@app.route('/api/user_points/<uid>', methods=['GET'])
def api_user_points(uid):
    try:
        # 1. Cari Dokumen User berdasarkan UID
        doc_ref = db.collection('customers').document(uid)
        doc = doc_ref.get()
        
        points = 0
        if doc.exists:
            # 2. Ambil field 'points', default 0 jika belum ada
            user_data = doc.to_dict()
            points = user_data.get('points', 0)
        
        # 3. Kembalikan data JSON yang benar
        return api_response('success', 'Data Poin', {'points': points})
        
    except Exception as e:
        print(f"Error Get Points: {e}")
        return api_response('error', str(e), {'points': 0})

@app.route('/api/checkout', methods=['POST'])
def api_checkout():
    try:
        data = request.get_json(silent=True)
        if not data:
            return api_response('error', 'Data kosong')

        # 1. Ambil Data
        c_id = data.get('customer_id') 
        c_name = data.get('customer_name', 'Pelanggan')
        payment_method = data.get('payment_method', 'Cash')
        items = data.get('items', [])
        voucher_code = data.get('voucher_code')
        final_price = float(data.get('final_price', 0))
        table_number = data.get('table_number', 'Take Away')

        if not items:
            return api_response('error', 'Keranjang kosong')

        # 2. Batch Write
        batch = db.batch()
        now_time = datetime.now().isoformat()
        queue_no = str(random.randint(1, 999)).zfill(3)
        
        points_earned = int(final_price / EARN_RATE) 

        # --- PERBAIKAN UTAMA DISINI (MENCEGAH ERROR 404) ---
        # Cek apakah ID valid
        if c_id and c_id != "Guest" and c_id != "":
            user_ref = db.collection('customers').document(c_id)
            user_doc = user_ref.get()

            if user_doc.exists:
                # Jika User ADA, update (tambah poin)
                batch.update(user_ref, {'points': firestore.Increment(points_earned)})
            else:
                # Jika User TIDAK ADA (404), buat baru (Set)
                batch.set(user_ref, {
                    'name': c_name,
                    'points': points_earned,
                    'role': 'Member',
                    'email': '-', # Placeholder
                    'created_at': now_time
                })
        # ---------------------------------------------------

        # 4. Loop Barang & Simpan Transaksi
        for item in items:
            pid = str(item['id'])
            qty = int(item['qty'])
            
            # Cek Produk
            prod_ref = db.collection('products').document(pid)
            prod_doc = prod_ref.get()
            
            # Jika produk dihapus admin, skip agar tidak error 404 produk
            if not prod_doc.exists: 
                continue 
            
            # Kurangi Stok
            p_data = prod_doc.to_dict()
            current_stock = p_data.get('stock', 0)
            if current_stock < qty:
                return api_response('error', f"Stok {p_data.get('name')} habis")
            
            batch.update(prod_ref, {'stock': current_stock - qty})
            
            # Simpan History Transaksi
            trx_id = generate_id() + str(random.randint(10,99))
            trx_ref = db.collection('transactions').document(trx_id)
            
            batch.set(trx_ref, {
                'customer_id': c_id,
                'customer_name': c_name,
                'product_id': pid,
                'quantity': qty,
                'final_price': final_price,
                'total_price': p_data.get('price', 0) * qty,
                'payment_method': payment_method,
                'table_number': table_number,
                'points_earned': points_earned,
                'queue_number': queue_no,
                'date': now_time,
                'status': 'PAID'
            })

        batch.commit()
        
        return api_response('success', 'Transaksi Berhasil', {
            'order_id': queue_no,
            'points': points_earned
        })

    except Exception as e:
        print(f"Checkout Error: {e}")
        return api_response('error', str(e))
    
@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    try:
        # Ambil filter nama customer dari URL (opsional)
        customer_name = request.args.get('customer_name')
        
        # Ambil referensi collection
        docs_ref = db.collection('transactions')
        
        # Jika ada filter nama, pakai query
        # (Catatan: Ini case-sensitive, untuk tes bisa dimatikan dulu if-nya agar muncul semua)
        if customer_name and customer_name != "Guest":
            docs = docs_ref.where('customer_name', '==', customer_name).stream()
        else:
            # Ambil semua data (limit 50 biar tidak berat)
            docs = docs_ref.limit(50).stream()
            
        history_data = []
        for doc in docs:
            t = doc.to_dict()
            t['id'] = doc.id
            history_data.append(t)
            
        # Urutkan berdasarkan tanggal (Terbaru di atas)
        # Asumsi format date ISO string
        try:
            history_data.sort(key=lambda x: x.get('date', ''), reverse=True)
        except:
            pass # Skip jika format tanggal error

        return api_response('success', 'Data ditemukan', history_data)

    except Exception as e:
        print(f"Error Get Transactions: {e}")
        return api_response('error', str(e))
    
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)