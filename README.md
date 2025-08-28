# PCM Simulation with Multi-Factor Authentication

A secure Physics-Informed Neural Networks platform for Phase Change Material thermal simulations with enterprise-grade multi-factor authentication.

## Features

### 🔐 Multi-Factor Authentication System
- **TOTP Authentication**: Support for Google Authenticator, Microsoft Authenticator, and Authy
- **Backup Codes**: 8 single-use backup codes for account recovery
- **SMS Verification**: Mock SMS verification implementation (ready for production integration)
- **Email Verification**: Mock email verification implementation (ready for production integration)
- **Account Security**: Automatic account locking after failed login attempts
- **Session Management**: Secure session handling with expiration

### 🧪 Physics Simulation
- **Phase Change Material Modeling**: 1D heat equation with phase change
- **Implicit Finite Difference**: Numerical stability and accuracy
- **Customizable Parameters**: Boundary temperature, simulation time, save interval
- **Real-time Results**: Interactive visualization and data export
- **Training Data Generation**: For Physics-Informed Neural Networks

### 🌐 Web Interface
- **Responsive Design**: Bootstrap-based UI that works on all devices
- **User Dashboard**: Account management and security settings
- **Simulation Interface**: Easy-to-use parameter input and results visualization
- **Security Management**: MFA setup, backup code generation, password changes

## Quick Start

### Prerequisites
```bash
pip install flask flask-login pyotp qrcode[pil] bcrypt numpy matplotlib scipy pandas
```

### Running the Application
```bash
python app.py
```

The application will start on `http://localhost:5000` with a default admin account:
- **Username**: `admin`
- **Password**: `Admin123!`

### Setting Up MFA
1. Log in with your credentials
2. Navigate to "Setup MFA" from the dashboard
3. Install an authenticator app (Google Authenticator, Microsoft Authenticator, or Authy)
4. Scan the QR code or enter the secret manually
5. Enter the 6-digit verification code to complete setup
6. Generate backup codes for account recovery

## API Endpoints

### Authentication
- `POST /register` - User registration
- `POST /login` - User login with optional MFA
- `POST /mfa-verify` - Complete MFA verification
- `GET /logout` - User logout

### User Management
- `GET /dashboard` - User dashboard
- `GET /mfa-setup` - MFA setup page
- `POST /generate-backup-codes` - Generate new backup codes
- `POST /disable-mfa` - Disable MFA (requires password)
- `POST /change-password` - Change user password

### Simulation
- `GET /simulation` - Simulation interface
- `POST /simulation` - Run PCM simulation
- `POST /api/simulation` - JSON API for simulation

## Authentication Features

### Password Requirements
- Minimum 8 characters
- Must contain uppercase letter
- Must contain lowercase letter
- Must contain number
- Must contain special character

### Security Features
- **Account Locking**: 5 failed attempts lock account for 30 minutes
- **Session Security**: 24-hour session expiration with activity tracking
- **Password Hashing**: PBKDF2 with SHA256 and 100,000 iterations
- **Secure Sessions**: Cryptographically secure session tokens
- **Input Validation**: Comprehensive validation for all user inputs

### MFA Implementation
- **TOTP**: Time-based One-Time Password using RFC 6238
- **QR Code Generation**: Automatic QR code generation for easy setup
- **Backup Codes**: Single-use 8-character recovery codes
- **Multiple Devices**: Support for multiple authenticator devices

## File Structure

```
├── app.py                 # Main Flask application
├── auth_models.py         # User, Session, and storage models
├── auth_service.py        # Authentication service logic
├── Pinn.py               # Original PCM simulation code
├── test_auth.py          # Comprehensive test suite
├── templates/            # HTML templates
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html
│   ├── mfa_setup.html
│   ├── mfa_verify.html
│   ├── mfa_manage.html
│   ├── backup_codes.html
│   ├── change_password.html
│   └── simulation.html
├── static/               # Static files (CSS, JS, images)
└── users.json           # User database (file-based for demo)
```

## Testing

Run the comprehensive test suite:
```bash
python -m unittest test_auth.py -v
```

Tests cover:
- User registration and validation
- Password hashing and verification
- MFA setup and verification
- Session management
- Account security features
- Data persistence

## Security Considerations

### Production Deployment
1. **Secret Key**: Change the Flask secret key in production
2. **HTTPS**: Always use HTTPS in production
3. **Database**: Replace file-based storage with proper database
4. **Email/SMS**: Integrate with real email and SMS providers
5. **Rate Limiting**: Implement rate limiting for authentication endpoints
6. **Logging**: Add comprehensive security logging

### Environment Variables
```bash
export SECRET_KEY="your-production-secret-key"
export DATABASE_URL="your-database-url"
export EMAIL_API_KEY="your-email-provider-api-key"
export SMS_API_KEY="your-sms-provider-api-key"
```

## Integration with Existing Code

The authentication system was designed to integrate seamlessly with the existing PCM simulation code:

- **Minimal Changes**: No modifications to the original `Pinn.py` simulation code
- **Secure Access**: All simulation endpoints require authentication
- **User Context**: Simulations are run in the context of authenticated users
- **Data Export**: Authenticated users can download simulation results

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Run the test suite
5. Submit a pull request

## License

This project integrates multi-factor authentication with the existing PCM simulation codebase while maintaining all original functionality.