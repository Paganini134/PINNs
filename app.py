"""
Flask web application for PCM simulation with multi-factor authentication.
"""

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import os
import json
from functools import wraps
from datetime import datetime

from auth_service import AuthService
from Pinn import PCMSimulation, generate_training_data


app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Initialize authentication service
auth_service = AuthService()

# Create templates directory if it doesn't exist
os.makedirs('templates', exist_ok=True)
os.makedirs('static', exist_ok=True)


def login_required(f):
    """Decorator to require authentication for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        session_id = session.get('session_id')
        if not session_id:
            return redirect(url_for('login'))
        
        user_session = auth_service.session_manager.get_session(session_id)
        if not user_session or not user_session.is_valid():
            session.clear()
            return redirect(url_for('login'))
        
        return f(*args, **kwargs)
    return decorated_function


@app.route('/')
def index():
    """Home page."""
    session_id = session.get('session_id')
    if session_id:
        user_session = auth_service.session_manager.get_session(session_id)
        if user_session and user_session.is_valid():
            return redirect(url_for('dashboard'))
    
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration."""
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        phone = request.form.get('phone') or None
        
        success, message = auth_service.register_user(username, email, password, phone)
        
        if success:
            flash(message, 'success')
            return redirect(url_for('login'))
        else:
            flash(message, 'error')
    
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login."""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        mfa_token = request.form.get('mfa_token')
        backup_code = request.form.get('backup_code')
        
        success, message, user_session = auth_service.authenticate_user(
            username, password, mfa_token, backup_code
        )
        
        if success:
            session['session_id'] = user_session.session_id
            flash(message, 'success')
            return redirect(url_for('dashboard'))
        else:
            if user_session and user_session.is_authenticated and not user_session.mfa_completed:
                # MFA required
                session['session_id'] = user_session.session_id
                return redirect(url_for('mfa_verify'))
            flash(message, 'error')
    
    return render_template('login.html')


@app.route('/mfa-verify', methods=['GET', 'POST'])
def mfa_verify():
    """MFA verification page."""
    session_id = session.get('session_id')
    if not session_id:
        return redirect(url_for('login'))
    
    user_session = auth_service.session_manager.get_session(session_id)
    if not user_session or not user_session.is_authenticated:
        return redirect(url_for('login'))
    
    if user_session.mfa_completed:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        mfa_token = request.form.get('mfa_token')
        backup_code = request.form.get('backup_code')
        
        success, message = auth_service.complete_mfa(session_id, mfa_token, backup_code)
        
        if success:
            flash(message, 'success')
            return redirect(url_for('dashboard'))
        else:
            flash(message, 'error')
    
    return render_template('mfa_verify.html')


@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard."""
    session_id = session.get('session_id')
    user_info = auth_service.get_user_info(session_id)
    return render_template('dashboard.html', user=user_info)


@app.route('/simulation', methods=['GET', 'POST'])
@login_required
def simulation():
    """PCM simulation page."""
    if request.method == 'POST':
        try:
            # Get simulation parameters
            boundary_temp = float(request.form.get('boundary_temp', 30))
            max_time = float(request.form.get('max_time', 1000))
            save_interval = float(request.form.get('save_interval', 10))
            
            # Run simulation
            sim = PCMSimulation()
            time_array, melt_fraction_array = sim.solve_heat_equation(
                T_boundary=boundary_temp,
                max_time=max_time,
                save_interval=save_interval
            )
            
            # Convert to lists for JSON serialization
            results = {
                'time': time_array.tolist(),
                'melt_fraction': melt_fraction_array.tolist(),
                'boundary_temp': boundary_temp,
                'max_time': max_time,
                'save_interval': save_interval
            }
            
            flash('Simulation completed successfully!', 'success')
            return render_template('simulation.html', results=results)
            
        except Exception as e:
            flash(f'Simulation error: {str(e)}', 'error')
    
    return render_template('simulation.html')


@app.route('/mfa-setup')
@login_required
def mfa_setup():
    """MFA setup page."""
    session_id = session.get('session_id')
    user_info = auth_service.get_user_info(session_id)
    
    if user_info['is_mfa_enabled']:
        return redirect(url_for('mfa_manage'))
    
    # Generate TOTP setup
    success, message, qr_code = auth_service.setup_totp(session_id)
    
    if success:
        return render_template('mfa_setup.html', qr_code=qr_code, message=message)
    else:
        flash(message, 'error')
        return redirect(url_for('dashboard'))


@app.route('/mfa-manage')
@login_required
def mfa_manage():
    """MFA management page."""
    session_id = session.get('session_id')
    user_info = auth_service.get_user_info(session_id)
    
    if not user_info['is_mfa_enabled']:
        return redirect(url_for('mfa_setup'))
    
    return render_template('mfa_manage.html', user=user_info)


@app.route('/generate-backup-codes', methods=['POST'])
@login_required
def generate_backup_codes():
    """Generate backup codes."""
    session_id = session.get('session_id')
    success, message, backup_codes = auth_service.generate_backup_codes(session_id)
    
    if success:
        return render_template('backup_codes.html', backup_codes=backup_codes)
    else:
        flash(message, 'error')
        return redirect(url_for('mfa_manage'))


@app.route('/disable-mfa', methods=['POST'])
@login_required
def disable_mfa():
    """Disable MFA."""
    session_id = session.get('session_id')
    password = request.form.get('password')
    
    success, message = auth_service.disable_mfa(session_id, password)
    flash(message, 'success' if success else 'error')
    
    return redirect(url_for('dashboard'))


@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change password page."""
    if request.method == 'POST':
        session_id = session.get('session_id')
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if new_password != confirm_password:
            flash('New passwords do not match', 'error')
        else:
            success, message = auth_service.change_password(
                session_id, current_password, new_password
            )
            flash(message, 'success' if success else 'error')
            
            if success:
                return redirect(url_for('dashboard'))
    
    return render_template('change_password.html')


@app.route('/logout')
def logout():
    """User logout."""
    session_id = session.get('session_id')
    if session_id:
        auth_service.logout(session_id)
    
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))


@app.route('/api/simulation', methods=['POST'])
@login_required
def api_simulation():
    """API endpoint for running simulations."""
    try:
        data = request.get_json()
        boundary_temp = data.get('boundary_temp', 30)
        max_time = data.get('max_time', 1000)
        save_interval = data.get('save_interval', 10)
        
        sim = PCMSimulation()
        time_array, melt_fraction_array = sim.solve_heat_equation(
            T_boundary=boundary_temp,
            max_time=max_time,
            save_interval=save_interval
        )
        
        return jsonify({
            'success': True,
            'time': time_array.tolist(),
            'melt_fraction': melt_fraction_array.tolist(),
            'boundary_temp': boundary_temp
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400


if __name__ == '__main__':
    # Create a default admin user if no users exist
    if not auth_service.user_store.list_users():
        auth_service.register_user('admin', 'admin@example.com', 'Admin123!', '+1234567890')
        print("Created default admin user: admin / Admin123!")
    
    app.run(debug=True, host='0.0.0.0', port=5000)