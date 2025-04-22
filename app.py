from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory, make_response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import pytz
import serial
import serial.tools.list_ports
from threading import Lock, Thread
import time
from datetime import datetime, timedelta
import os
import logging
import pandas as pd
from io import BytesIO
from openpyxl import Workbook
from sqlalchemy import text

# Настройка временной зоны
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

def moscow_time():
    return datetime.now(MOSCOW_TZ)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'instance', 'site.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Модели базы данных
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    original_password = db.Column(db.String(50), nullable=False)
    role = db.Column(db.String(20), nullable=False)

class Equipment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), default="Arduino Station")
    temperature = db.Column(db.Float, default=0.0)
    pressure = db.Column(db.Float, default=0.0)
    vibration = db.Column(db.Float, default=0.0)
    spindle_speed = db.Column(db.Float, default=0.0)
    load = db.Column(db.Float, default=0.0)
    last_updated = db.Column(db.DateTime)
    is_running = db.Column(db.Boolean, default=False)
    start_time = db.Column(db.DateTime)
    stop_time = db.Column(db.DateTime)
    total_runtime = db.Column(db.BigInteger, default=0)

class EquipmentLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=moscow_time)
    temperature = db.Column(db.Float)
    pressure = db.Column(db.Float)
    vibration = db.Column(db.Float)
    spindle_speed = db.Column(db.Float)
    load = db.Column(db.Float)
    is_running = db.Column(db.Boolean)
    alert = db.Column(db.String(200))

def initialize_database():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin_user = User(
                username='admin',
                password=generate_password_hash('admin'),
                original_password='admin',
                role='admin'
            )
            db.session.add(admin_user)
            db.session.commit()
            logger.info("Создан пользователь admin с паролем admin")

initialize_database()

arduino_connected = False
arduino_port = None
arduino_lock = Lock()
serial_connection = None
alerts = []

def manage_arduino_connection():
    global arduino_connected, arduino_port, serial_connection, alerts
    while True:
        try:
            ports = serial.tools.list_ports.comports()
            found = any('Arduino' in p.description or 'USB' in p.description for p in ports)
            
            if found and not arduino_connected:
                for port in ports:
                    if 'Arduino' in port.description or 'USB' in port.description:
                        try:
                            with arduino_lock:
                                if serial_connection:
                                    serial_connection.close()
                                serial_connection = serial.Serial(port.device, 9600, timeout=1)
                                serial_connection.flushInput()
                            
                            arduino_port = port.device
                            arduino_connected = True
                            logger.info(f"Станок подключен к порту {port.device}")
                            
                            with app.app_context():
                                if not Equipment.query.first():
                                    equipment = Equipment(name="Station")
                                    db.session.add(equipment)
                                    db.session.commit()
                            break
                        except Exception as e:
                            logger.error(f"Ошибка подключения к станку: {e}")
                            continue
            
            elif not found and arduino_connected:
                with arduino_lock:
                    if serial_connection:
                        serial_connection.close()
                        serial_connection = None
                arduino_connected = False
                arduino_port = None
                logger.info("Станок отключен")
                
                with app.app_context():
                    equipment = Equipment.query.first()
                    if equipment:
                        db.session.delete(equipment)
                        db.session.commit()
            
            if arduino_connected and serial_connection:
                with arduino_lock:
                    try:
                        while serial_connection.in_waiting > 0:
                            line = serial_connection.readline().decode('utf-8').strip()
                            if line.startswith("ALERT:"):
                                alert_msg = line[6:].strip()
                                alerts.append(alert_msg)
                                logger.warning(f"Получено предупреждение: {alert_msg}")
                                
                                with app.app_context():
                                    equipment = Equipment.query.first()
                                    if equipment:
                                        log_entry = EquipmentLog(
                                            temperature=equipment.temperature,
                                            pressure=equipment.pressure,
                                            vibration=equipment.vibration,
                                            spindle_speed=equipment.spindle_speed,
                                            load=equipment.load,
                                            is_running=equipment.is_running,
                                            alert=alert_msg
                                        )
                                        db.session.add(log_entry)
                                        db.session.commit()
                    except Exception as e:
                        logger.error(f"Ошибка чтения предупреждений: {e}")
            
            time.sleep(3)
        except Exception as e:
            logger.error(f"Ошибка в фоновом процессе: {e}")
            time.sleep(5)

Thread(target=manage_arduino_connection, daemon=True).start()

@app.route('/')
def home():
    if 'username' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            session['username'] = user.username
            session['role'] = user.role
            flash('Успешный вход!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Неверный логин или пароль!', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('role', None)
    return redirect(url_for('login'))

@app.route('/index')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    equipment = Equipment.query.first()
    has_equipment = equipment is not None and arduino_connected
    
    return render_template('index.html', 
                         equipment=[equipment] if equipment else [],
                         role=session.get('role'),
                         has_equipment=has_equipment)

@app.route('/start_equipment', methods=['POST'])
def start_equipment():
    global serial_connection, alerts
    equipment = Equipment.query.first()
    if not equipment:
        return jsonify({'status': 'error', 'message': 'Станок не найден'}), 404
    
    if not arduino_connected:
        return jsonify({'status': 'error', 'message': 'Станок не подключен'}), 400
    
    try:
        with arduino_lock:
            if serial_connection is None:
                serial_connection = serial.Serial(arduino_port, 9600, timeout=1)
                time.sleep(1)
            
            serial_connection.flushInput()
            
            for _ in range(3):
                serial_connection.write(b'START\n')
                time.sleep(0.2)
                
                if serial_connection.in_waiting > 0:
                    response = serial_connection.readline().decode('utf-8').strip()
                    if "STATUS: Станок запущен" in response:
                        equipment.is_running = True
                        equipment.start_time = datetime.utcnow()
                        equipment.last_updated = datetime.utcnow()
                        db.session.commit()
                        
                        log_entry = EquipmentLog(
                            is_running=True,
                            alert="Станок запущен"
                        )
                        db.session.add(log_entry)
                        db.session.commit()
                        
                        return jsonify({'status': 'success'})
            
            return jsonify({'status': 'error', 'message': 'Нет ответа от станка'}), 500
            
    except Exception as e:
        logger.error(f"Ошибка при запуске станка: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/stop_equipment', methods=['POST'])
def stop_equipment():
    global serial_connection, alerts
    equipment = Equipment.query.first()
    if not equipment:
        return jsonify({'status': 'error', 'message': 'Станок не найден'}), 404
    
    try:
        with arduino_lock:
            if serial_connection:
                serial_connection.write(b'STOP\n')
                time.sleep(0.2)
            
            if equipment.is_running and equipment.start_time:
                runtime = (datetime.utcnow() - equipment.start_time).total_seconds() * 1000
                equipment.total_runtime += int(runtime)
            
            equipment.is_running = False
            equipment.stop_time = datetime.utcnow()
            db.session.commit()
            
            log_entry = EquipmentLog(
                is_running=False,
                alert="Станок остановлен"
            )
            db.session.add(log_entry)
            db.session.commit()
            
            return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Ошибка при остановке станка: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/get_equipment_data')
def get_equipment_data():
    global serial_connection, alerts
    equipment = Equipment.query.first()
    if not equipment:
        return jsonify({})
    
    current_alerts = []
    if alerts:
        current_alerts = alerts.copy()
        alerts.clear()
    
    if equipment.is_running and arduino_connected and serial_connection:
        try:
            with arduino_lock:
                serial_connection.write(b'GETDATA\n')
                time.sleep(0.1)
                if serial_connection.in_waiting > 0:
                    data = serial_connection.readline().decode('utf-8').strip()
                    if data and data != "0,0,0,0,0":
                        values = data.split(',')
                        if len(values) == 5:
                            equipment.temperature = float(values[0])
                            equipment.pressure = float(values[1])
                            equipment.vibration = float(values[2])
                            equipment.spindle_speed = float(values[3])
                            equipment.load = float(values[4])
                            equipment.last_updated = datetime.utcnow()
                            db.session.commit()
                            
                            log_entry = EquipmentLog(
                                temperature=equipment.temperature,
                                pressure=equipment.pressure,
                                vibration=equipment.vibration,
                                spindle_speed=equipment.spindle_speed,
                                load=equipment.load,
                                is_running=True
                            )
                            db.session.add(log_entry)
                            db.session.commit()
        except Exception as e:
            logger.error(f"Ошибка чтения данных: {e}")
    
    current_runtime = equipment.total_runtime
    if equipment.is_running and equipment.start_time:
        current_runtime += (datetime.utcnow() - equipment.start_time).total_seconds() * 1000
    
    return jsonify({
        'temperature': equipment.temperature,
        'pressure': equipment.pressure,
        'vibration': equipment.vibration,
        'spindle_speed': equipment.spindle_speed,
        'load': equipment.load,
        'is_running': equipment.is_running,
        'arduino_connected': arduino_connected,
        'alerts': current_alerts,
        'start_time': equipment.start_time.isoformat() if equipment.start_time else None,
        'stop_time': equipment.stop_time.isoformat() if equipment.stop_time else None,
        'total_runtime': current_runtime,
        'last_updated': equipment.last_updated.isoformat() if equipment.last_updated else None
    })

@app.route('/admin/update_data')
def admin_update_data():
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'status': 'error'})
    
    equipment = Equipment.query.first()
    if not equipment:
        return jsonify({'status': 'error'})
    
    data = get_equipment_data().json
    
    return jsonify({
        'temperature': equipment.temperature,
        'pressure': equipment.pressure,
        'vibration': equipment.vibration,
        'spindle_speed': equipment.spindle_speed,
        'load': equipment.load,
        'is_running': equipment.is_running,
        'start_time': equipment.start_time.isoformat() if equipment.start_time else None,
        'stop_time': equipment.stop_time.isoformat() if equipment.stop_time else None,
        'total_runtime': data['total_runtime'],
        'last_updated': equipment.last_updated.isoformat() if equipment.last_updated else None
    })

@app.route('/admin/clear_logs', methods=['POST'])
def clear_logs():
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403
    
    try:
        # Удаляем все записи логов
        num_deleted = db.session.query(EquipmentLog).delete()
        db.session.commit()
        
        # Безопасная проверка и сброс счетчика
        try:
            # Проверяем существует ли таблица sqlite_sequence
            result = db.session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'")
            ).fetchone()
            
            if result:
                # Проверяем существует ли запись для нашей таблицы
                seq_exists = db.session.execute(
                    text("SELECT 1 FROM sqlite_sequence WHERE name='equipment_log'")
                ).fetchone()
                
                if seq_exists:
                    db.session.execute(
                        text("UPDATE sqlite_sequence SET seq = 0 WHERE name='equipment_log'")
                    )
                    db.session.commit()
        except Exception as e:
            logger.warning(f"Не удалось сбросить счетчик: {e}")
        
        return jsonify({'status': 'success', 'count': num_deleted})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ошибка при очистке логов: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/generate_report')
def generate_report():
    if 'username' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    get_equipment_data()
    equipment = Equipment.query.first()
    logs = EquipmentLog.query.order_by(EquipmentLog.timestamp).all()
    
    output = BytesIO()
    workbook = Workbook()
    
    log_sheet = workbook.active
    log_sheet.title = "Equipment Log"
    log_sheet.append(['Timestamp', 'Temperature', 'Pressure', 'Vibration', 'Spindle Speed', 'Load', 'Status', 'Alert'])
    
    for log in logs:
        log_sheet.append([
            log.timestamp + timedelta(hours=3) if log.timestamp else '',
            log.temperature if log.temperature is not None else '',
            log.pressure if log.pressure is not None else '',
            log.vibration if log.vibration is not None else '',
            log.spindle_speed if log.spindle_speed is not None else '',
            log.load if log.load is not None else '',
            'Running' if log.is_running else 'Stopped',
            log.alert if log.alert else ''
        ])
    
    if equipment:
        current_sheet = workbook.create_sheet("Current State")
        current_sheet.append(['Parameter', 'Value'])
        current_sheet.append(['Temperature', f"{equipment.temperature:.1f} °C"])
        current_sheet.append(['Pressure', f"{equipment.pressure:.1f} бар"])
        current_sheet.append(['Vibration', f"{equipment.vibration:.1f} мм/с"])
        current_sheet.append(['Spindle Speed', f"{equipment.spindle_speed:.0f} об/мин"])
        current_sheet.append(['Load', f"{equipment.load:.0f}%"])
        current_sheet.append(['Status', 'Running' if equipment.is_running else 'Stopped'])
        current_sheet.append(['Last Start', (equipment.start_time + timedelta(hours=3)).strftime('%Y-%m-%d %H:%M:%S') if equipment.start_time else ''])
        current_sheet.append(['Last Stop', (equipment.stop_time + timedelta(hours=3)).strftime('%Y-%m-%d %H:%M:%S') if equipment.stop_time else ''])
        current_sheet.append(['Total Runtime', f"{equipment.total_runtime / 1000 / 60:.1f} minutes"])
    
    workbook.save(output)
    output.seek(0)
    
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    response.headers['Content-Disposition'] = 'attachment; filename=equipment_report.xlsx'
    return response

@app.route('/admin')
def admin():
    if 'username' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    equipment = Equipment.query.first()
    logs = EquipmentLog.query.order_by(EquipmentLog.timestamp.desc()).limit(10).all()
    users = User.query.all()
    
    return render_template('admin.html', 
                         users=users, 
                         equipment=equipment,
                         arduino_connected=arduino_connected,
                         logs=logs,
                         now=moscow_time())

@app.route('/admin/add_user', methods=['POST'])
def add_user():
    if 'username' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    username = request.form['username']
    password = request.form['password']
    role = request.form['role']
    
    logger.info(f"Попытка создания пользователя: {username}, роль: {role}")
    
    if User.query.filter_by(username=username).first():
        flash('Пользователь уже существует!', 'danger')
        logger.warning(f"Пользователь {username} уже существует")
    else:
        try:
            new_user = User(
                username=username,
                password=generate_password_hash(password),
                original_password=password,
                role=role
            )
            db.session.add(new_user)
            db.session.commit()
            flash('Пользователь успешно создан!', 'success')
            logger.info(f"Создан новый пользователь: {username}")
        except Exception as e:
            db.session.rollback()
            flash('Ошибка при создании пользователя!', 'danger')
            logger.error(f"Ошибка при создании пользователя {username}: {str(e)}")
    
    return redirect(url_for('admin'))

@app.route('/admin/delete_user/<int:user_id>')
def delete_user(user_id):
    if 'username' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    user = User.query.get(user_id)
    if user:
        # Проверяем, является ли пользователь последним администратором
        admin_count = User.query.filter_by(role='admin').count()
        if user.role == 'admin' and admin_count <= 1:
            flash('Нельзя удалить последнего администратора!', 'danger')
            logger.warning(f"Попытка удалить последнего администратора: {user.username}")
        else:
            try:
                db.session.delete(user)
                db.session.commit()
                flash('Пользователь удален!', 'success')
                logger.info(f"Пользователь {user.username} удален")
            except Exception as e:
                db.session.rollback()
                flash('Ошибка при удалении пользователя!', 'danger')
                logger.error(f"Ошибка при удаления пользователя: {str(e)}")
    
    return redirect(url_for('admin'))

@app.route('/styles/<path:filename>')
def serve_styles(filename):
    return send_from_directory('styles', filename)

@app.route('/scripts/<path:filename>')
def serve_scripts(filename):
    return send_from_directory('scripts', filename)

if __name__ == '__main__':
    os.makedirs('instance', exist_ok=True)
    os.makedirs('styles', exist_ok=True)
    os.makedirs('scripts', exist_ok=True)
    os.makedirs('templates', exist_ok=True)
    app.run(debug=True, host='0.0.0.0')