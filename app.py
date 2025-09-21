from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
import os
import secrets
import string
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecretkey")

# Database
DB_FILE = "stokvel_sami.db"

# Upload folder
UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ---------------- Database Setup ---------------- #
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            surname TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            phone TEXT,
            province TEXT,
            address TEXT,
            profile_picture TEXT
        )
    ''')

    # Stokvels table
    c.execute('''
        CREATE TABLE IF NOT EXISTS stokvels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT NOT NULL,
            description TEXT,
            category TEXT,
            target_amount REAL,
            duration_months INTEGER,
            max_members INTEGER,
            current_amount REAL DEFAULT 0,
            current_members INTEGER DEFAULT 0,
            grow_with_sami INTEGER,
            join_code TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')

    # Stokvel members table
    c.execute('''
        CREATE TABLE IF NOT EXISTS stokvel_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            stokvel_id INTEGER,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(stokvel_id) REFERENCES stokvels(id)
        )
    ''')

    conn.commit()
    conn.close()

init_db()

# ---------------- Utility Functions ---------------- #
def generate_join_code(length=6):
    """Generates a random alphanumeric code for joining a stokvel."""
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(length))


# ---------------- Routes ---------------- #
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create-account', methods=['GET', 'POST'])
def create_account():
    if request.method == 'POST':
        first_name = request.form['first_name']
        surname = request.form['surname']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        phone = request.form['phone']
        province = request.form['province']
        address = request.form['address']
        profile_picture = request.files.get('profile_picture')

        if not all([first_name, surname, email, password, confirm_password, phone, province, address]):
            flash("Please fill in all fields.")
            return redirect(url_for('create_account'))

        if password != confirm_password:
            flash("Passwords do not match.")
            return redirect(url_for('create_account'))

        pic_filename = None
        if profile_picture and profile_picture.filename != '':
            filename = secure_filename(profile_picture.filename)
            pic_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            profile_picture.save(pic_path)
            pic_filename = filename

        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''
                INSERT INTO users (first_name, surname, email, password, phone, province, address, profile_picture)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (first_name, surname, email, password, phone, province, address, pic_filename))
            conn.commit()
            conn.close()
            flash("Account created successfully! You can now log in.")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Email already exists.")
            return redirect(url_for('create_account'))

    return render_template('create_account.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, first_name FROM users WHERE email=? AND password=?", (email, password))
        user = c.fetchone()
        conn.close()

        if user:
            session['user_id'] = user[0]
            flash(f"Welcome back, {user[1]}!")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid email or password.")
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash("Logged out successfully.")
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT first_name, profile_picture FROM users WHERE id=?", (user_id,))
    user = cursor.fetchone()

    cursor.execute("""
        SELECT id, name, description, category, target_amount, duration_months, max_members,
               current_amount, current_members, grow_with_sami, join_code, created_at
        FROM stokvels WHERE user_id=?
    """, (user_id,))
    stokvels = cursor.fetchall()
    conn.close()

    firstname, profile_pic = (user if user else ("Member", None))

    stokvel_list = []
    for s in stokvels:
        (stokvel_id, name, description, category, target_amount, duration, max_members,
         current_amount, current_members, grow_with_sami, join_code, created_at) = s
        monthly_contribution = round(target_amount / duration, 2) if duration else 0
        progress_percentage = round((current_amount / target_amount) * 100, 0) if target_amount else 0

        stokvel_list.append({
            'id': stokvel_id,
            'name': name,
            'description': description,
            'category': category,
            'target_amount': target_amount,
            'duration': duration,
            'max_members': max_members,
            'grow_with_sami': grow_with_sami,
            'join_code': join_code,
            'created_at': created_at,
            'monthly_contribution': monthly_contribution,
            'current_amount': current_amount,
            'current_members': current_members,
            'progress_percentage': progress_percentage
        })

    return render_template('dashboard.html', firstname=firstname, profile_pic=profile_pic, stokvels=stokvel_list)

# Create stokvel
@app.route('/create-stokvel', methods=['GET', 'POST'])
def create_stokvel():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        user_id = session['user_id']
        name = request.form['name']
        description = request.form['description']
        category = request.form['category']
        target_amount = float(request.form['target_amount'])
        duration_months = int(request.form['duration_months'])
        max_members = int(request.form['max_members'])
        grow_with_sami = 1 if request.form.get('grow_with_sami') else 0

        join_code = generate_join_code()

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            INSERT INTO stokvels (user_id, name, description, category, target_amount,
                                  duration_months, max_members, grow_with_sami, join_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, name, description, category, target_amount, duration_months, max_members, grow_with_sami, join_code))
        new_stokvel_id = c.lastrowid
        conn.commit()
        conn.close()

        flash("Stokvel group created successfully!")
        return redirect(url_for('invite_friends', stokvel_id=new_stokvel_id))

    return render_template('create_stokvel.html')

# Invite friends via SMS
@app.route('/invite/<int:stokvel_id>', methods=['GET', 'POST'])
def invite_friends(stokvel_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT name, join_code FROM stokvels WHERE id=?", (stokvel_id,))
    stokvel = cursor.fetchone()
    conn.close()

    if not stokvel:
        flash("Stokvel not found.")
        return redirect(url_for('dashboard'))

    stokvel_name, join_code = stokvel

    if request.method == 'POST':
        phone_number = request.form['phone_number']
        send_sms_invite(phone_number, stokvel_name, join_code)
        flash(f"Invite sent to {phone_number}!")
        return redirect(url_for('dashboard'))

    return render_template('invite_friends.html', stokvel_name=stokvel_name, join_code=join_code)

@app.route('/learn-more')
def learn_more():
    return render_template('learn_more.html')

@app.route('/join-stokvel', methods=['GET', 'POST'])
def join_stokvel():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('join_stokvel.html')

if __name__ == '__main__':
    app.run(debug=True)
