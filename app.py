from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from io import BytesIO # Wajib untuk membaca binary gambar

app = Flask(__name__)
app.secret_key = "rahasia_nusa_niaga_blob_version" 

# --- KONFIGURASI DATABASE ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+mysqlconnector://root:@localhost/nusa_niaga'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Max upload size (opsional, misal max 16MB)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 

db = SQLAlchemy(app)

# --- KONFIGURASI LAIN ---
POINT_VALUE = 5000      
EARN_RATE = 10000       

# --- LOGIN SETUP ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id): return User.query.get(int(user_id))

# ==========================================
# MODEL DATABASE
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
    transactions = db.relationship('Transaction', backref='product', lazy=True)
    reviews_rel = db.relationship('Review', backref='product', lazy=True)
    favorites_rel = db.relationship('Favorite', backref='product', lazy=True)

class Voucher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    discount_amount = db.Column(db.Integer, nullable=False)
    is_active = db.Column(db.Boolean, default=True)

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), nullable=True)
    password = db.Column(db.String(255), nullable=True) 
    points = db.Column(db.Integer, default=0) 
    address = db.Column(db.Text, nullable=True)
    redemptions = db.relationship('PointRedemption', backref='customer', lazy=True)
    reviews_rel = db.relationship('Review', backref='customer', lazy=True)
    favorites_rel = db.relationship('Favorite', backref='customer', lazy=True)

class PointRedemption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    points_spent = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(200), nullable=False)
    date = db.Column(db.DateTime, default=datetime.now)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
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
    date = db.Column(db.DateTime, default=datetime.now)

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

# --- MODEL BANNER BARU (BLOB) ---
class Banner(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    # Menyimpan Data Binary (Gambar)
    image_data = db.Column(db.LargeBinary, nullable=False) 
    # Menyimpan Tipe File (jpeg/png) agar browser tahu cara bacanya
    mimetype = db.Column(db.String(50), nullable=False)
    is_active = db.Column(db.Boolean, default=True)

with app.app_context():
    db.create_all()

# ==========================================
# ROUTES
# ==========================================

# --- AUTH & PROFIL ---
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

@app.route('/profile')
@login_required
def profile():
    recent_trx = Transaction.query.order_by(Transaction.date.desc()).limit(10).all()
    return render_template('profile.html', transactions=recent_trx)

@app.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    current_user.full_name = request.form['full_name']
    current_user.email = request.form['email']
    current_user.address = request.form['address']
    db.session.commit(); flash("Profil diperbarui.", "success"); return redirect(url_for('profile'))

@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    if not current_user.check_password(request.form['old_password']): flash("Password lama salah.", "danger"); return redirect(url_for('profile'))
    if request.form['new_password'] != request.form['confirm_password']: flash("Konfirmasi salah.", "warning"); return redirect(url_for('profile'))
    current_user.set_password(request.form['new_password']); db.session.commit(); flash("Password diganti.", "success"); return redirect(url_for('logout'))

# --- DASHBOARD ---
@app.route('/')
@login_required
def index():
    products = Product.query.all()
    latest = Transaction.query.order_by(Transaction.date.desc()).limit(5).all()
    total_customers = Customer.query.count()
    total_stock = sum(p.stock for p in products)
    return render_template('index.html', total_products=len(products), total_stock=total_stock, total_customers=total_customers, latest_transactions=latest)

# --- PRODUK & KATEGORI ---
@app.route('/products')
@login_required
def products(): return render_template('products.html', products=Product.query.all())

@app.route('/add', methods=['POST', 'GET'])
@login_required
def add():
    categories = Category.query.all()
    if request.method == 'POST':
        db.session.add(Product(name=request.form['name'], category_id=request.form.get('category_id'), price=int(request.form['price']), stock=int(request.form['stock']), description=request.form['description']))
        db.session.commit(); flash("Produk ditambah.", "success"); return redirect(url_for('products'))
    return render_template('add.html', categories=categories)

@app.route('/edit/<int:id>', methods=['POST', 'GET'])
@login_required
def edit(id):
    p = Product.query.get_or_404(id); categories = Category.query.all()
    if request.method == 'POST':
        p.name=request.form['name']; p.category_id=request.form.get('category_id'); p.price=int(request.form['price']); p.stock=int(request.form['stock']); p.description=request.form['description']; db.session.commit(); flash("Diupdate.", "info"); return redirect(url_for('products'))
    return render_template('edit.html', product=p, categories=categories)

@app.route('/delete/<int:id>')
@login_required
def delete(id):
    try: db.session.delete(Product.query.get_or_404(id)); db.session.commit(); flash("Dihapus.", "danger")
    except: db.session.rollback(); flash("Gagal hapus.", "warning")
    return redirect(url_for('products'))

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

# --- VOUCHER ---
@app.route('/discounts', methods=['GET', 'POST'])
@login_required
def discounts():
    if request.method == 'POST': db.session.add(Voucher(code=request.form['code'].upper(), discount_amount=int(request.form['amount']))); db.session.commit(); flash("Voucher dibuat.", "success"); return redirect(url_for('discounts'))
    return render_template('discounts.html', vouchers=Voucher.query.all())

@app.route('/delete_discount/<int:id>')
@login_required
def delete_discount(id): db.session.delete(Voucher.query.get_or_404(id)); db.session.commit(); return redirect(url_for('discounts'))

# --- CRM (PELANGGAN) ---
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

@app.route('/update_customer', methods=['POST'])
@login_required
def update_customer():
    c = Customer.query.get_or_404(request.form.get('customer_id'))
    try:
        c.name = request.form.get('name'); c.phone = request.form.get('phone')
        c.email = request.form.get('email'); c.address = request.form.get('address')
        if request.form.get('password'): c.password = request.form.get('password')
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

# --- TRANSAKSI (POS) ---
@app.route('/transactions')
@login_required
def transactions(): return render_template('transactions.html', transactions=Transaction.query.order_by(Transaction.date.desc()).all())

@app.route('/add_transaction', methods=['GET', 'POST'])
@login_required
def add_transaction():
    products = Product.query.all()
    if request.method == 'POST':
        try:
            pid = request.form['product_id']; qty = int(request.form['quantity']); c_name = request.form['customer_name']; c_phone = request.form['customer_phone']; c_addr = request.form['customer_address']; pay = request.form['payment_method']; ivoucher = request.form.get('voucher_code', '').strip().upper()
            prod = Product.query.get(pid)
            if prod.stock < qty: flash("Stok kurang!", "danger"); return redirect(url_for('add_transaction'))
            gross = prod.price * qty; disc = 0; code = None
            if ivoucher:
                v = Voucher.query.filter_by(code=ivoucher, is_active=True).first()
                if v: disc = v.discount_amount; code = ivoucher; disc = gross if disc > gross else disc
                else: flash("Kode Voucher Salah", "warning")
            final = gross - disc
            
            cust = Customer.query.filter_by(phone=c_phone).first()
            if not cust: cust = Customer(name=c_name, phone=c_phone, address=c_addr, points=0); db.session.add(cust)
            earn = int(final / EARN_RATE); cust.points += earn
            
            prod.stock -= qty
            db.session.add(Transaction(product_id=pid, customer_name=c_name, customer_phone=c_phone, customer_address=c_addr, quantity=qty, total_price=gross, voucher_code=code, discount_voucher=disc, points_earned=earn, final_price=final, payment_method=pay))
            db.session.commit()
            flash(f"Sukses! Poin +{earn}", "success"); return redirect(url_for('transactions'))
        except Exception as e: flash(f"Error: {e}", "danger"); return redirect(url_for('add_transaction'))
    return render_template('add_transaction.html', products=products)

@app.route('/generate_dummy')
@login_required
def generate_dummy():
    c = Customer.query.first(); p = Product.query.first()
    if c and p:
        if not Review.query.all(): db.session.add(Review(customer_id=c.id, product_id=p.id, rating=5, comment="Mantap!")); db.session.add(Review(customer_id=c.id, product_id=p.id, rating=4, comment="Ok."))
        if not Favorite.query.all(): db.session.add(Favorite(customer_id=c.id, product_id=p.id))
        db.session.commit(); flash("Dummy Data Dibuat!", "success")
    else: flash("Perlu data transaksi/produk dulu.", "warning")
    return redirect(url_for('index'))

# ==========================================
# BANNERS (GAMBAR DI DATABASE)
# ==========================================

# 1. Tampilkan Halaman
@app.route('/banners')
@login_required
def banners():
    return render_template('banners.html', banners=Banner.query.all())

# 2. Tambah Banner (Simpan BLOB)
@app.route('/add_banner', methods=['POST'])
@login_required
def add_banner():
    title = request.form.get('title')
    file = request.files['image']
    
    if file:
        new_banner = Banner(
            title=title,
            image_data=file.read(), # Baca binary file
            mimetype=file.mimetype  # Simpan tipe (jpg/png)
        )
        db.session.add(new_banner)
        db.session.commit()
        flash("Banner ditambahkan.", "success")
    else:
        flash("File gambar wajib diisi.", "danger")
        
    return redirect(url_for('banners'))

# 3. Edit Banner
@app.route('/edit_banner', methods=['POST'])
@login_required
def edit_banner():
    b = Banner.query.get_or_404(request.form.get('banner_id'))
    b.title = request.form.get('title')
    b.is_active = True if request.form.get('is_active') else False
    
    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename != '':
            b.image_data = file.read() # Timpa data lama
            b.mimetype = file.mimetype
            
    db.session.commit()
    flash("Banner diperbarui.", "success")
    return redirect(url_for('banners'))

# 4. Hapus Banner
@app.route('/delete_banner/<int:id>')
@login_required
def delete_banner(id):
    b = Banner.query.get_or_404(id)
    db.session.delete(b)
    db.session.commit()
    flash("Banner dihapus.", "warning")
    return redirect(url_for('banners'))

# 5. ROUTE KHUSUS: MENAMPILKAN GAMBAR DARI DB
@app.route('/banner_image/<int:id>')
def banner_image(id):
    b = Banner.query.get_or_404(id)
    return send_file(BytesIO(b.image_data), mimetype=b.mimetype)

if __name__ == "__main__":
    app.run(debug=True)