from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json
import sys, os

# Ajustar rutas de plantillas y estáticos para PyInstaller
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__,
            template_folder=os.path.join(base_path, 'templates'),
            static_folder=os.path.join(base_path, 'static'))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///caja.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class CashInventory(db.Model):
    denomination = db.Column(db.Integer, primary_key=True)
    count = db.Column(db.Integer, default=0)

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    for_whom = db.Column(db.String(100))
    description = db.Column(db.String(200))
    amount = db.Column(db.Integer)
    used_bills = db.Column(db.String)  # JSON serializado

class Income(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    used_bills = db.Column(db.String)  # JSON serializado

DENOMINATIONS = [1000, 500, 200, 100, 50, 20, 10, 5, 2, 1]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/ingreso', methods=['GET', 'POST'])
def ingreso():
    if request.method == 'POST':
        bills = {}
        for denom in DENOMINATIONS:
            cnt = int(request.form.get(f'count_{denom}', 0))
            bills[denom] = cnt
            inv = CashInventory.query.get(denom)
            inv.count += cnt
        income = Income(used_bills=json.dumps(bills))
        db.session.add(income)
        db.session.commit()
        return redirect(url_for('ingreso'))
    inventories = CashInventory.query.filter(CashInventory.denomination.in_(DENOMINATIONS)).order_by(CashInventory.denomination.desc()).all()
    # Lista de ingresos para mostrar historial
    incomes = Income.query.order_by(Income.date.desc()).all()
    incomes_data = []
    for inc in incomes:
        bb = json.loads(inc.used_bills)
        total = sum(int(d) * c for d, c in bb.items())
        incomes_data.append({'id': inc.id, 'date': inc.date, 'bills': bb, 'total': total})
    return render_template('ingreso.html', inventories=inventories, incomes_data=incomes_data)

@app.route('/ingreso/edit/<int:income_id>', methods=['GET', 'POST'])
def edit_ingreso(income_id):
    income = Income.query.get_or_404(income_id)
    if request.method == 'POST':
        old_bills = json.loads(income.used_bills)
        for denom, cnt in old_bills.items():
            inv = CashInventory.query.get(int(denom))
            inv.count -= cnt
        new_bills = {}
        for denom in DENOMINATIONS:
            cnt = int(request.form.get(f'count_{denom}', 0))
            new_bills[denom] = cnt
            inv = CashInventory.query.get(denom)
            inv.count += cnt
        income.used_bills = json.dumps(new_bills)
        income.date = datetime.utcnow()
        db.session.commit()
        return redirect(url_for('ingreso'))
    # Cargar billetes originales y convertir keys a enteros
    raw_bills = json.loads(income.used_bills)
    bills = {int(k): v for k, v in raw_bills.items()}
    return render_template('edit_ingreso.html', bills=bills, income=income, denominations=DENOMINATIONS)

@app.route('/ingreso/delete/<int:income_id>')
def delete_ingreso(income_id):
    # Eliminar un ingreso y revertir el inventario
    income = Income.query.get_or_404(income_id)
    # Revertir inventario
    raw_bills = json.loads(income.used_bills)
    for denom_str, cnt in raw_bills.items():
        inv = CashInventory.query.get(int(denom_str))
        inv.count -= cnt
    # Borrar registro
    db.session.delete(income)
    db.session.commit()
    return redirect(url_for('ingreso'))

@app.route('/gasto', methods=['GET', 'POST'])
def gasto():
    if request.method == 'POST':
        for_whom = request.form['for_whom']
        description = request.form['description']
        amount = int(request.form['amount'])
        used_bills = request.form.get('used_bills')
        import json
        bills = json.loads(used_bills)
        # Actualizar inventario
        for denom, cnt in bills.items():
            inv = CashInventory.query.get(int(denom))
            inv.count -= cnt
        expense = Expense(for_whom=for_whom, description=description, amount=amount, used_bills=used_bills)
        db.session.add(expense)
        db.session.commit()
        return redirect(url_for('index'))
    inventories = {inv.denomination: inv.count for inv in CashInventory.query.filter(CashInventory.denomination.in_(DENOMINATIONS)).all()}
    return render_template('gasto.html', inventories=inventories)

@app.route('/sugerencia')
def sugerencia():
    amount = int(request.args.get('amount', 0))
    # Obtener inventario y calcular sugerencia solo para denominaciones con stock
    inv = {row.denomination: row.count for row in CashInventory.query.all()}
    remaining = amount
    suggestion = {}
    for denom in DENOMINATIONS:
        available = inv.get(denom, 0)
        if available <= 0:
            continue
        max_use = min(available, remaining // denom)
        suggestion[denom] = max_use
        remaining -= denom * max_use
    return jsonify(suggestion)

@app.route('/corte')
def corte():
    inventories = CashInventory.query.filter(CashInventory.denomination.in_(DENOMINATIONS)).order_by(CashInventory.denomination.desc()).all()
    return render_template('corte.html', inventories=inventories)

@app.context_processor
def inject_total_efectivo():
    # Total en efectivo disponible
    invs = CashInventory.query.filter(CashInventory.denomination.in_(DENOMINATIONS)).all()
    total = sum(inv.denomination * inv.count for inv in invs)
    return dict(total_efectivo=total)

def init_db():
    db.create_all()
    # Inicializar inventario si está vacío
    for denom in DENOMINATIONS:
        if not CashInventory.query.get(denom):
            db.session.add(CashInventory(denomination=denom, count=0))
    db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True) 