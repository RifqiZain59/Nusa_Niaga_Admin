from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from io import BytesIO 
from sqlalchemy import func, extract, text
import json

app = Flask(__name__)
app.secret_key = "rahasia_nusa_niaga_blob_version" 

# ==========================================
# 1. KONFIGURASI DATABASE
# ==========================================
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+mysqlconnector://root:@localhost/nusa_niaga'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id): return User.query.get(int(user_id))

# ==========================================
# 2. MODEL DATABASE
# ==========================================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    address = db.Column(db.Text, nullable=True)
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    products = db.relationship('Product', backref='category', lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Integer, nullable=False) 
    stock = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text, nullable=True)
    image_data = db.Column(db.LargeBinary, nullable=True) 
    mimetype = db.Column(db.String(50), nullable=True)

    @property
    def final_price(self): return self.price

    reviews_rel = db.relationship('Review', backref='product_parent', cascade="all, delete-orphan", lazy=True)
    favorites_rel = db.relationship('Favorite', backref='product_parent', cascade="all, delete-orphan", lazy=True)

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), nullable=True)
    password = db.Column(db.String(255), nullable=True) 
    points = db.Column(db.Integer, default=0) 
    address = db.Column(db.Text, nullable=True)
    redemptions = db.relationship('PointRedemption', backref='customer', lazy=True)

class PointRedemption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    points_spent = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(200), nullable=False)
    date = db.Column(db.DateTime, default=datetime.now)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    product = db.relationship('Product', backref='transactions')
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(20), nullable=True)
    customer_address = db.Column(db.Text, nullable=True)
    quantity = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Integer, nullable=False)
    voucher_code = db.Column(db.String(20), nullable=True)
    discount_voucher = db.Column(db.Integer, default=0)
    points_earned = db.Column(db.Integer, default=0)
    final_price = db.Column(db.Integer, nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    
    # KOLOM MEJA DAN ANTRIAN (DIPERTAHANKAN)
    table_number = db.Column(db.String(10), nullable=True)
    queue_number = db.Column(db.String(10), nullable=True)
    
    date = db.Column(db.DateTime, default=datetime.now)

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    customer = db.relationship('Customer', backref='reviews')
    product = db.relationship('Product', backref='reviews')

class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    customer = db.relationship('Customer', backref='favorites')
    product = db.relationship('Product', backref='favorites')

class Banner(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    image_data = db.Column(db.LargeBinary, nullable=False) 
    mimetype = db.Column(db.String(50), nullable=False)
    is_active = db.Column(db.Boolean, default=True)

# [DIHAPUS] Model DesignSetting
# [DIHAPUS] Model AdCampaign

class SocialPost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    platform = db.Column(db.String(50), nullable=False) 
    content = db.Column(db.Text, nullable=False)
    schedule_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='Scheduled') 

class Voucher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False) 
    discount_amount = db.Column(db.Integer, nullable=False)      
    is_active = db.Column(db.Boolean, default=True)

# KONSTANTA POINT RATE
EARN_RATE = 5000 

with app.app_context():
    db.create_all()

# ==========================================
# 3. WEB ROUTES
# ==========================================

@app.context_processor
def inject_theme():
    # Mengembalikan tema STATIS (Hardcoded) karena tabel DB dihapus
    # Ini mencegah error di base.html yang memanggil {{ theme.primary_color }}
    theme = {
        'primary_color': '#2563eb', 
        'sidebar_color': '#1e3a8a', 
        'font_family': 'Poppins'
    }
    return dict(theme=theme)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            login_user(user); return redirect(url_for('index'))
        flash("Gagal login.", "danger")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        if User.query.filter_by(username=request.form['username']).first():
            flash("Username ada.", "warning"); return redirect(url_for('register'))
        new_user = User(username=request.form['username']); new_user.set_password(request.form['password'])
        db.session.add(new_user); db.session.commit(); flash("Akun dibuat.", "success"); return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout(): logout_user(); return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    products = Product.query.all()
    latest = Transaction.query.order_by(Transaction.date.desc()).limit(5).all()
    total_customers = Customer.query.count()
    total_stock = sum(p.stock for p in products)
    return render_template('index.html', total_products=len(products), total_stock=total_stock, total_customers=total_customers, latest_transactions=latest)

@app.route('/products')
@login_required
def products(): return render_template('products.html', products=Product.query.all())

# === RESET DATABASE ID ===
@app.route('/reset_products')
@login_required
def reset_products():
    try:
        Transaction.query.delete()
        Review.query.delete()
        Favorite.query.delete()
        Product.query.delete()
        db.session.commit()

        db.session.execute(text("ALTER TABLE product AUTO_INCREMENT = 1"))
        db.session.execute(text("ALTER TABLE transaction AUTO_INCREMENT = 1"))
        db.session.commit()
        
        flash("Semua produk dihapus. ID di-reset ke 1.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Gagal reset: {e}", "danger")
    
    return redirect(url_for('products'))

@app.route('/add', methods=['POST', 'GET'])
@login_required
def add():
    categories = Category.query.all()
    if request.method == 'POST':
        file = request.files.get('image')
        img_data = None
        mtype = None
        if file and file.filename != '':
            img_data = file.read()
            mtype = file.mimetype
        
        raw_price = request.form['price'].replace('.', '') 
        price = int(raw_price) if raw_price else 0
        
        new_prod = Product(
            name=request.form['name'], 
            category_id=request.form.get('category_id'), 
            price=price,
            stock=int(request.form['stock']), 
            description=request.form['description'],
            image_data=img_data,
            mimetype=mtype
        )
        db.session.add(new_prod)
        db.session.commit()
        flash("Produk ditambah.", "success")
        return redirect(url_for('products'))
    return render_template('add.html', categories=categories)

@app.route('/edit/<int:id>', methods=['POST', 'GET'])
@login_required
def edit(id):
    p = Product.query.get_or_404(id)
    categories = Category.query.all()
    if request.method == 'POST':
        p.name = request.form['name']
        p.category_id = request.form.get('category_id')
        
        raw_price = request.form['price'].replace('.', '')
        p.price = int(raw_price) if raw_price else 0
        
        p.stock = int(request.form['stock'])
        p.description = request.form['description']
        
        file = request.files.get('image')
        if file and file.filename != '':
            p.image_data = file.read()
            p.mimetype = file.mimetype
            
        db.session.commit()
        flash("Produk diperbarui.", "info")
        return redirect(url_for('products'))
    return render_template('edit.html', product=p, categories=categories)

@app.route('/delete/<int:id>')
@login_required
def delete(id):
    p = Product.query.get_or_404(id)
    try:
        Transaction.query.filter_by(product_id=id).delete()
        Review.query.filter_by(product_id=id).delete()
        Favorite.query.filter_by(product_id=id).delete()
        db.session.delete(p)
        db.session.commit()
        
        if Product.query.count() == 0:
            db.session.execute(text("ALTER TABLE product AUTO_INCREMENT = 1"))
            db.session.commit()
            flash(f"Produk dihapus. Data habis, ID di-reset ke 1.", "warning")
        else:
            flash(f"Produk '{p.name}' berhasil dihapus.", "success")
            
    except Exception as e:
        db.session.rollback()
        flash(f"Gagal hapus: {str(e)}", "warning")
    return redirect(url_for('products'))

@app.route('/product_image/<int:id>')
def product_image(id):
    p = Product.query.get_or_404(id)
    if p.image_data:
        return send_file(BytesIO(p.image_data), mimetype=p.mimetype)
    return redirect("https://via.placeholder.com/150")

@app.route('/categories', methods=['GET', 'POST'])
@login_required
def categories():
    if request.method == 'POST': db.session.add(Category(name=request.form['name'])); db.session.commit(); flash("Kategori dibuat.", "success"); return redirect(url_for('categories'))
    return render_template('categories.html', categories=Category.query.all())

@app.route('/delete_category/<int:id>')
@login_required
def delete_category(id):
    try: db.session.delete(Category.query.get_or_404(id)); db.session.commit()
    except: db.session.rollback()
    return redirect(url_for('categories'))

@app.route('/customers')
@login_required
def customers():
    return render_template('customers.html', customers=Customer.query.order_by(Customer.points.desc()).all(), history=PointRedemption.query.order_by(PointRedemption.date.desc()).all())

@app.route('/customer/<int:id>')
@login_required
def customer_detail(id):
    c = Customer.query.get_or_404(id)
    trx = Transaction.query.filter_by(customer_phone=c.phone).order_by(Transaction.date.desc()).all()
    rev = Review.query.filter_by(customer_id=id).all()
    fav = Favorite.query.filter_by(customer_id=id).all()
    return render_template('customer_detail.html', c=c, transactions=trx, reviews=rev, favorites=fav)

@app.route('/discounts', methods=['GET', 'POST'])
@login_required
def discounts():
    if request.method == 'POST': db.session.add(Voucher(code=request.form['code'].upper(), discount_amount=int(request.form['amount']))); db.session.commit(); flash("Voucher dibuat.", "success"); return redirect(url_for('discounts'))
    return render_template('discounts.html', vouchers=Voucher.query.all())

@app.route('/delete_discount/<int:id>')
@login_required
def delete_discount(id): db.session.delete(Voucher.query.get_or_404(id)); db.session.commit(); return redirect(url_for('discounts'))

@app.route('/transactions')
@login_required
def transactions():
    # 1. Ambil data mentah dari database
    raw_transactions = Transaction.query.order_by(Transaction.date.desc()).all()
    
    # 2. Logika Pengelompokan (Grouping)
    grouped_data = {}
    
    for t in raw_transactions:
        # Gunakan getattr untuk menghindari error jika kolom queue/table belum ada
        queue_num = getattr(t, 'queue_number', '-')
        table_num = getattr(t, 'table_number', '-')
        
        # KUNCI GROUPING: Waktu + No HP + Antrian
        group_key = (t.date, t.customer_phone, queue_num)
        
        if group_key not in grouped_data:
            grouped_data[group_key] = {
                'date': t.date,
                'queue_number': queue_num,
                'table_number': table_num,
                'customer_name': t.customer_name,
                'list_belanja': [],
                'total_discount': 0,
                'total_final': 0,
                'total_points': 0  # <--- [BARU] Inisialisasi Poin
            }
        
        # Masukkan item ke dalam grup list_belanja
        grouped_data[group_key]['list_belanja'].append({
            'name': t.product.name if t.product else 'Produk Terhapus',
            'qty': t.quantity
        })
        
        # Akumulasi total
        grouped_data[group_key]['total_discount'] += (t.discount_voucher or 0)
        grouped_data[group_key]['total_final'] += t.final_price
        grouped_data[group_key]['total_points'] += t.points_earned  # <--- [BARU] Jumlahkan Poin

    # 3. Ubah dictionary ke list
    transactions_list = list(grouped_data.values())
    
    # Urutkan berdasarkan tanggal terbaru
    transactions_list.sort(key=lambda x: x['date'], reverse=True)

    return render_template('transactions.html', transactions=transactions_list)

@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    old_pass = request.form['old_password']
    new_pass = request.form['new_password']
    confirm_pass = request.form['confirm_password']

    # 1. Cek apakah password lama benar
    if not current_user.check_password(old_pass):
        flash("Gagal ganti password: Password lama salah.", "danger")
        return redirect(url_for('profile'))

    # 2. Cek apakah password baru dan konfirmasi cocok
    if new_pass != confirm_pass:
        flash("Gagal ganti password: Konfirmasi password tidak cocok.", "danger")
        return redirect(url_for('profile'))

    # 3. Simpan password baru
    try:
        current_user.set_password(new_pass)
        db.session.commit()
        flash("Password berhasil diubah!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Terjadi kesalahan: {e}", "danger")
    
    return redirect(url_for('profile'))

@app.route('/add_transaction', methods=['GET', 'POST'])
@login_required
def add_transaction():
    products = Product.query.all()
    categories = Category.query.all()
    
    if request.method == 'POST':
        try:
            # AMBIL DATA UMUM
            c_name = request.form['customer_name']
            c_phone = request.form['customer_phone']
            c_addr = request.form['customer_address']
            pay = request.form['payment_method']
            table_num = request.form.get('table_number', '-') 
            ivoucher = request.form.get('voucher_code', '').strip().upper()
            
            # AMBIL DATA KERANJANG (JSON STRING)
            cart_json = request.form.get('cart_data')
            if not cart_json:
                flash("Keranjang kosong!", "danger")
                return redirect(url_for('add_transaction'))
            
            cart_items = json.loads(cart_json) # Parsing JSON ke List Python

            # 1. CEK STOK & HITUNG TOTAL KOTOR
            total_gross = 0
            product_map = {} # Simpan objek produk biar ga query ulang
            
            for item in cart_items:
                pid = int(item['id'])
                qty = int(item['qty'])
                prod = Product.query.get(pid)
                
                if not prod:
                    flash(f"Produk ID {pid} tidak ditemukan.", "danger")
                    return redirect(url_for('add_transaction'))
                
                if prod.stock < qty:
                    flash(f"Stok {prod.name} kurang! Sisa: {prod.stock}", "danger")
                    return redirect(url_for('add_transaction'))
                
                product_map[pid] = prod
                total_gross += prod.price * qty

            # 2. CEK VOUCHER (Berlaku untuk Total Transaksi)
            disc_voucher_total = 0
            code = None
            if ivoucher:
                v = Voucher.query.filter_by(code=ivoucher, is_active=True).first()
                if v:
                    disc_voucher_total = v.discount_amount
                    code = ivoucher
                    # Diskon tidak boleh melebihi total belanja
                    if disc_voucher_total > total_gross: 
                        disc_voucher_total = total_gross
                    flash(f"Voucher {code} dipakai! Hemat Rp {disc_voucher_total}", "success")
                else:
                    flash(f"Voucher '{ivoucher}' tidak valid.", "warning")

            # 3. PROSES PELANGGAN & POIN
            final_total_transaksi = total_gross - disc_voucher_total
            cust = Customer.query.filter_by(phone=c_phone).first()
            if not cust:
                cust = Customer(name=c_name, phone=c_phone, address=c_addr, points=0)
                db.session.add(cust)
            
            total_earn = int(final_total_transaksi / EARN_RATE)
            cust.points += total_earn

            # 4. GENERATE NOMOR ANTRIAN (Satu antrian untuk semua item)
            today_str = datetime.now().strftime('%Y-%m-%d')
            last_trx = Transaction.query.filter(
                func.date(Transaction.date) == today_str
            ).order_by(Transaction.id.desc()).first()

            new_queue = "001"
            if last_trx and last_trx.queue_number:
                try:
                    last_num = int(last_trx.queue_number)
                    new_queue = str(last_num + 1).zfill(3)
                except:
                    new_queue = "001"

            # 5. SIMPAN TRANSAKSI PER ITEM
            # Kita perlu membagi diskon voucher secara proporsional ke setiap item
            # agar laporan per item tetap valid.
            
            remaining_disc = disc_voucher_total
            
            for index, item in enumerate(cart_items):
                pid = int(item['id'])
                qty = int(item['qty'])
                prod = product_map[pid]
                
                item_gross = prod.price * qty
                
                # Hitung proporsi diskon untuk item ini
                if total_gross > 0:
                    # Jika ini item terakhir, ambil sisa diskon (untuk menghindari selisih pembulatan)
                    if index == len(cart_items) - 1:
                        item_disc = remaining_disc
                    else:
                        item_disc = int((item_gross / total_gross) * disc_voucher_total)
                        remaining_disc -= item_disc
                else:
                    item_disc = 0

                item_final = item_gross - item_disc
                
                # Kurangi Stok
                prod.stock -= qty
                
                # Simpan ke DB
                new_trx = Transaction(
                    product_id=pid, customer_name=c_name, customer_phone=c_phone, customer_address=c_addr,
                    quantity=qty, total_price=item_gross, 
                    voucher_code=code if item_disc > 0 else None, 
                    discount_voucher=item_disc,
                    points_earned=int(item_final / EARN_RATE), # Poin per item (estimasi)
                    final_price=item_final, payment_method=pay,
                    table_number=table_num, queue_number=new_queue 
                )
                db.session.add(new_trx)

            db.session.commit()
            flash(f"Transaksi Berhasil! Antrian: {new_queue}, Total: Rp {final_total_transaksi:,}", "success")
            return redirect(url_for('transactions'))

        except Exception as e:
            db.session.rollback()
            flash(f"Error: {e}", "danger")
            return redirect(url_for('add_transaction'))
            
    return render_template('add_transaction.html', products=products, categories=categories)

@app.route('/banners')
@login_required
def banners(): return render_template('banners.html', banners=Banner.query.all())

@app.route('/add_banner', methods=['POST'])
@login_required
def add_banner():
    title = request.form.get('title')
    file = request.files['image']
    if file: db.session.add(Banner(title=title, image_data=file.read(), mimetype=file.mimetype)); db.session.commit(); flash("Banner ditambahkan.", "success")
    else: flash("File gambar wajib diisi.", "danger")
    return redirect(url_for('banners'))

@app.route('/edit_banner', methods=['POST'])
@login_required
def edit_banner():
    try:
        b_id = request.form.get('banner_id')
        b = Banner.query.get_or_404(b_id)
        b.title = request.form.get('title')
        b.is_active = True if request.form.get('is_active') else False
        file = request.files.get('image')
        if file and file.filename != '':
            b.image_data = file.read()
            b.mimetype = file.mimetype
        db.session.commit(); flash("Banner diperbarui.", "success")
    except Exception as e: flash(f"Gagal update banner: {e}", "danger")
    return redirect(url_for('banners'))

@app.route('/delete_banner/<int:id>')
@login_required
def delete_banner(id):
    b = Banner.query.get_or_404(id); db.session.delete(b); db.session.commit(); flash("Banner dihapus.", "warning"); return redirect(url_for('banners'))

@app.route('/banner_image/<int:id>')
def banner_image(id):
    b = Banner.query.get_or_404(id)
    return send_file(BytesIO(b.image_data), mimetype=b.mimetype)

@app.route('/profile')
@login_required
def profile():
    recent_trx = Transaction.query.order_by(Transaction.date.desc()).limit(10).all()
    return render_template('profile.html', transactions=recent_trx)

@app.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    current_user.full_name = request.form['full_name']; current_user.email = request.form['email']; current_user.address = request.form['address']
    db.session.commit(); flash("Profil diperbarui.", "success"); return redirect(url_for('profile'))

@app.route('/update_customer', methods=['POST'])
@login_required
def update_customer():
    c = Customer.query.get_or_404(request.form.get('customer_id'))
    try:
        c.name = request.form.get('name'); c.phone = request.form.get('phone'); c.email = request.form.get('email'); c.address = request.form.get('address')
        if request.form.get('password'): c.password = generate_password_hash(request.form.get('password'))
        db.session.commit(); flash("Pelanggan diperbarui.", "success")
    except Exception as e: db.session.rollback(); flash(f"Error: {e}", "danger")
    return redirect(url_for('customer_detail', id=c.id))

@app.route('/redeem_points', methods=['POST'])
@login_required
def redeem_points():
    c = Customer.query.get_or_404(request.form.get('customer_id'))
    pts = int(request.form.get('points_to_redeem')); desc = request.form.get('description')
    if c.points >= pts:
        c.points -= pts; db.session.add(PointRedemption(customer_id=c.id, points_spent=pts, description=desc)); db.session.commit()
        flash(f"Tukar {pts} poin berhasil.", "success")
    else: flash("Poin tidak cukup.", "danger")
    return redirect(url_for('customers'))

@app.route('/reviews')
@login_required
def reviews(): return render_template('reviews.html', reviews=Review.query.order_by(Review.created_at.desc()).all())

@app.route('/delete_review/<int:id>')
@login_required
def delete_review(id): db.session.delete(Review.query.get_or_404(id)); db.session.commit(); flash("Ulasan dihapus.", "danger"); return redirect(url_for('reviews'))

@app.route('/favorites')
@login_required
def favorites(): return render_template('favorites.html', favorites=Favorite.query.order_by(Favorite.created_at.desc()).all())

@app.route('/analytics')
@login_required
def analytics():
    daily_sales = db.session.query(func.date(Transaction.date), func.sum(Transaction.final_price))\
        .group_by(func.date(Transaction.date))\
        .order_by(func.date(Transaction.date).desc()).limit(7).all()
    
    chart_dates = [str(d[0]) for d in daily_sales][::-1]
    chart_revenue = [int(d[1]) for d in daily_sales][::-1]

    top_products = db.session.query(Product.name, func.sum(Transaction.quantity))\
        .join(Transaction).group_by(Product.name)\
        .order_by(func.sum(Transaction.quantity).desc()).limit(5).all()

    peak_hours = db.session.query(extract('hour', Transaction.date), func.count(Transaction.id))\
        .group_by(extract('hour', Transaction.date))\
        .order_by(func.count(Transaction.id).desc()).all()
    
    peak_hour_data = {f"{int(h[0])}:00": h[1] for h in peak_hours}

    insights = []
    if not chart_revenue:
        insights.append("Belum ada data penjualan yang cukup.")
    else:
        if len(chart_revenue) > 1 and chart_revenue[-1] < chart_revenue[0]: 
            insights.append("Tren penjualan menurun.")
        if peak_hours and peak_hours[0][0] > 17:
            insights.append("Pelanggan aktif malam hari.")
    
    # [DIHAPUS] Query Kampanye Iklan
    campaigns = [] 

    return render_template('analytics.html', 
                           dates=json.dumps(chart_dates), 
                           revenue=json.dumps(chart_revenue),
                           top_products=top_products,
                           peak_hours=peak_hour_data,
                           insights=insights,
                           campaigns=campaigns)

@app.route('/marketing', methods=['GET', 'POST'])
@login_required
def marketing():
    if request.method == 'POST':
        platform = request.form['platform']
        content = request.form['content']
        time_str = request.form['schedule_time'] 
        sch_time = datetime.strptime(time_str, '%Y-%m-%dT%H:%M')
        
        new_post = SocialPost(platform=platform, content=content, schedule_time=sch_time)
        db.session.add(new_post)
        db.session.commit()
        flash("Postingan dijadwalkan!", "success")
        return redirect(url_for('marketing'))
        
    posts = SocialPost.query.order_by(SocialPost.schedule_time.asc()).all()
    return render_template('marketing.html', posts=posts)

@app.route('/edit_post/<int:id>', methods=['POST'])
@login_required
def edit_post(id):
    post = SocialPost.query.get_or_404(id)
    try:
        post.platform = request.form['platform']
        post.content = request.form['content']
        time_str = request.form['schedule_time']
        post.schedule_time = datetime.strptime(time_str, '%Y-%m-%dT%H:%M')
        
        db.session.commit()
        flash("Postingan diperbarui.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error update: {str(e)}", "danger")
    return redirect(url_for('marketing'))

@app.route('/delete_post/<int:id>')
@login_required
def delete_post(id):
    post = SocialPost.query.get_or_404(id)
    try:
        db.session.delete(post)
        db.session.commit()
        flash("Postingan dihapus.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error hapus: {str(e)}", "danger")
    return redirect(url_for('marketing'))

# [DIHAPUS] Route /add_campaign

# [DIUBAH] Route Design menjadi Redirect (Nonaktif)
@app.route('/design', methods=['GET', 'POST'])
@login_required
def design():
    # Route ini dipertahankan hanya agar url_for('design') di base.html tidak error
    # Namun fungsinya dimatikan dan akan redirect ke dashboard
    flash("Fitur Desain Tema telah dinonaktifkan (Database dihapus).", "warning")
    return redirect(url_for('index'))

# ==========================================
# 5. API SERVICE (MOBILE APP)
# ==========================================

def api_response(status, message, data=None):
    return jsonify({'status': status, 'message': message, 'data': data})

@app.route('/api/register', methods=['POST'])
def api_register():
    try:
        data = request.get_json(silent=True)
        if not data: return api_response('error', 'Data JSON tidak valid')
        name = data.get('name'); phone = data.get('phone'); password = data.get('password')
        if not name or not phone or not password: return api_response('error', 'Data tidak lengkap')
        if Customer.query.filter_by(phone=phone).first(): return api_response('error', 'Nomor HP sudah terdaftar')
        new_cust = Customer(name=name, phone=phone, password=generate_password_hash(password), points=0)
        db.session.add(new_cust); db.session.commit()
        return api_response('success', 'Registrasi berhasil', {'id': new_cust.id})
    except Exception as e: db.session.rollback(); return api_response('error', f'Error: {str(e)}')

@app.route('/api/login', methods=['POST'])
def api_login():
    try:
        data = request.get_json(silent=True)
        phone = data.get('phone'); password = data.get('password')
        cust = Customer.query.filter_by(phone=phone).first()
        if cust and cust.password and check_password_hash(cust.password, password):
            return api_response('success', 'Login berhasil', {
                'id': cust.id, 'name': cust.name, 'phone': cust.phone, 'points': cust.points, 'address': cust.address, 'email': cust.email
            })
        return api_response('error', 'Nomor HP atau Password salah')
    except Exception as e: return api_response('error', str(e))

@app.route('/api/products', methods=['GET'])
def api_products():
    try:
        products = Product.query.all()
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
    try:
        banners = Banner.query.filter_by(is_active=True).all()
        data = [{'id': b.id, 'title': b.title, 'image_url': url_for('banner_image', id=b.id, _external=True)} for b in banners]
        return api_response('success', 'Data banner berhasil', data)
    except Exception as e: return api_response('error', str(e))

@app.route('/api/checkout', methods=['POST'])
def api_checkout():
    try:
        data = request.get_json(silent=True)
        cust = Customer.query.get(data.get('customer_id'))
        if not cust: return api_response('error', 'Pelanggan tidak ditemukan')
        items = data.get('items')
        
        voucher_code = data.get('voucher_code'); discount_amount = 0; valid_voucher = None
        if voucher_code:
            v = Voucher.query.filter_by(code=voucher_code.upper(), is_active=True).first()
            if v: discount_amount = v.discount_amount; valid_voucher = v.code

        remaining_discount = discount_amount; total_pay = 0; total_points = 0
        for item in items:
            p = Product.query.get(item['product_id']); qty = int(item['qty'])
            if not p or p.stock < qty: return api_response('error', f'Stok {p.name if p else ""} habis/kurang')
            gross = p.price * qty; curr_disc = 0
            if remaining_discount > 0:
                curr_disc = gross if remaining_discount >= gross else remaining_discount
                remaining_discount -= curr_disc
            final = gross - curr_disc; earn = int(final / EARN_RATE)
            p.stock -= qty
            
            db.session.add(Transaction(
                product_id=p.id, customer_name=cust.name, customer_phone=cust.phone, customer_address=cust.address,
                quantity=qty, total_price=gross, voucher_code=valid_voucher if curr_disc > 0 else None,
                discount_voucher=curr_disc, points_earned=earn, final_price=final, payment_method=data.get('payment_method', 'Cash')
            ))
            total_pay += final; total_points += earn
        cust.points += total_points; db.session.commit()
        return api_response('success', 'Transaksi Berhasil', {'total_price': total_pay, 'points_earned': total_points, 'new_balance': cust.points})
    except Exception as e: db.session.rollback(); return api_response('error', str(e))

@app.route('/api/redeem', methods=['POST'])
def api_redeem():
    try:
        data = request.get_json(silent=True)
        cust_id = data.get('customer_id'); points = int(data.get('points'))
        cust = Customer.query.get(cust_id)
        if cust and cust.points >= points:
            cust.points -= points
            db.session.add(PointRedemption(customer_id=cust_id, points_spent=points, description=data.get('description', 'Penukaran')))
            db.session.commit()
            return api_response('success', 'Berhasil', {'new_balance': cust.points})
        return api_response('error', 'Gagal')
    except Exception as e: return api_response('error', str(e))

@app.route('/api/favorites/<int:customer_id>', methods=['GET'])
def api_get_favorites(customer_id):
    try:
        favs = Favorite.query.filter_by(customer_id=customer_id).all()
        data = [{'product_id': f.product.id, 'name': f.product.name, 'price': f.product.price, 'image_url': url_for('product_image', id=f.product.id, _external=True)} for f in favs if f.product]
        return api_response('success', 'OK', data)
    except Exception as e: return api_response('error', str(e))

@app.route('/api/products/<int:id>', methods=['GET'])
def api_product_detail(id):
    p = Product.query.get(id)
    if not p:
        return jsonify({'status': 'error', 'message': 'Data tidak ditemukan (404)'}), 404
    
    customer_id = request.args.get('customer_id', type=int)
    is_fav = False
    if customer_id:
        fav = Favorite.query.filter_by(customer_id=customer_id, product_id=id).first()
        is_fav = True if fav else False

    return jsonify({
        'id': p.id,
        'name': p.name,
        'price': p.price,
        'description': p.description,
        'is_favorite': is_fav,
        'status': 'success'
    })

@app.route('/api/toggle_favorite', methods=['POST'])
def api_toggle_favorite():
    try:
        data = request.get_json(silent=True)
        cust_id = data.get('customer_id'); prod_id = data.get('product_id')
        existing = Favorite.query.filter_by(customer_id=cust_id, product_id=prod_id).first()
        if existing:
            db.session.delete(existing); is_fav = False
        else:
            db.session.add(Favorite(customer_id=cust_id, product_id=prod_id)); is_fav = True
        db.session.commit()
        return api_response('success', 'Updated', {'is_favorite': is_fav})
    except Exception as e: return api_response('error', str(e))

@app.route('/api/vouchers', methods=['GET'])
def api_get_vouchers():
    try:
        vouchers = Voucher.query.filter_by(is_active=True).all()
        data = [{'id': v.id, 'code': v.code, 'discount_amount': v.discount_amount} for v in vouchers]
        return api_response('success', 'Daftar voucher berhasil diambil', data)
    except Exception as e:
        return api_response('error', str(e))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)