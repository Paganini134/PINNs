"""
User authentication models for the PCM simulation system.
Supports multi-factor authentication with TOTP, SMS, and email.
"""

import hashlib
import secrets
import pyotp
import qrcode
import io
import base64
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import json
import os


class User:
    """User model with multi-factor authentication support."""
    
    def __init__(self, username: str, email: str, phone: Optional[str] = None):
        self.username = username
        self.email = email
        self.phone = phone
        self.password_hash = None
        self.salt = secrets.token_hex(16)
        self.is_active = True
        self.is_mfa_enabled = False
        self.totp_secret = None
        self.backup_codes = []
        self.last_login = None
        self.failed_login_attempts = 0
        self.account_locked_until = None
        self.created_at = datetime.now()
        
    def set_password(self, password: str) -> None:
        """Set user password with secure hashing."""
        # Use PBKDF2 with SHA256
        self.password_hash = hashlib.pbkdf2_hmac(
            'sha256', 
            password.encode('utf-8'), 
            self.salt.encode('utf-8'), 
            100000  # 100k iterations
        ).hex()
    
    def check_password(self, password: str) -> bool:
        """Verify password against stored hash."""
        if not self.password_hash:
            return False
        
        password_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            self.salt.encode('utf-8'),
            100000
        ).hex()
        
        return password_hash == self.password_hash
    
    def enable_totp(self) -> str:
        """Enable TOTP authentication and return secret for QR code generation."""
        self.totp_secret = pyotp.random_base32()
        self.is_mfa_enabled = True
        return self.totp_secret
    
    def get_totp_uri(self, issuer_name: str = "PCM Simulation") -> str:
        """Get TOTP URI for QR code generation."""
        if not self.totp_secret:
            raise ValueError("TOTP not enabled for this user")
        
        totp = pyotp.TOTP(self.totp_secret)
        return totp.provisioning_uri(
            name=self.username,
            issuer_name=issuer_name
        )
    
    def generate_qr_code(self, issuer_name: str = "PCM Simulation") -> str:
        """Generate QR code for TOTP setup as base64 string."""
        uri = self.get_totp_uri(issuer_name)
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(uri)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        return img_str
    
    def verify_totp(self, token: str) -> bool:
        """Verify TOTP token."""
        if not self.totp_secret:
            return False
        
        totp = pyotp.TOTP(self.totp_secret)
        return totp.verify(token, valid_window=1)  # Allow 1 time step tolerance
    
    def generate_backup_codes(self, count: int = 8) -> List[str]:
        """Generate backup codes for account recovery."""
        self.backup_codes = [secrets.token_hex(8) for _ in range(count)]
        return self.backup_codes.copy()
    
    def use_backup_code(self, code: str) -> bool:
        """Use a backup code for authentication."""
        if code in self.backup_codes:
            self.backup_codes.remove(code)
            return True
        return False
    
    def is_account_locked(self) -> bool:
        """Check if account is locked due to failed login attempts."""
        if self.account_locked_until and datetime.now() < self.account_locked_until:
            return True
        elif self.account_locked_until and datetime.now() >= self.account_locked_until:
            # Unlock account
            self.account_locked_until = None
            self.failed_login_attempts = 0
        return False
    
    def record_failed_login(self) -> None:
        """Record a failed login attempt and lock account if necessary."""
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= 5:
            # Lock account for 30 minutes
            self.account_locked_until = datetime.now() + timedelta(minutes=30)
    
    def record_successful_login(self) -> None:
        """Record a successful login."""
        self.last_login = datetime.now()
        self.failed_login_attempts = 0
        self.account_locked_until = None
    
    def to_dict(self) -> Dict:
        """Convert user to dictionary for storage."""
        return {
            'username': self.username,
            'email': self.email,
            'phone': self.phone,
            'password_hash': self.password_hash,
            'salt': self.salt,
            'is_active': self.is_active,
            'is_mfa_enabled': self.is_mfa_enabled,
            'totp_secret': self.totp_secret,
            'backup_codes': self.backup_codes,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'failed_login_attempts': self.failed_login_attempts,
            'account_locked_until': self.account_locked_until.isoformat() if self.account_locked_until else None,
            'created_at': self.created_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'User':
        """Create user from dictionary."""
        user = cls(data['username'], data['email'], data.get('phone'))
        user.password_hash = data.get('password_hash')
        user.salt = data.get('salt', secrets.token_hex(16))
        user.is_active = data.get('is_active', True)
        user.is_mfa_enabled = data.get('is_mfa_enabled', False)
        user.totp_secret = data.get('totp_secret')
        user.backup_codes = data.get('backup_codes', [])
        user.failed_login_attempts = data.get('failed_login_attempts', 0)
        
        # Parse datetime fields
        if data.get('last_login'):
            user.last_login = datetime.fromisoformat(data['last_login'])
        if data.get('account_locked_until'):
            user.account_locked_until = datetime.fromisoformat(data['account_locked_until'])
        if data.get('created_at'):
            user.created_at = datetime.fromisoformat(data['created_at'])
        
        return user


class UserStore:
    """Simple file-based user storage for the PCM simulation system."""
    
    def __init__(self, storage_file: str = "users.json"):
        self.storage_file = storage_file
        self.users = {}
        self.load_users()
    
    def load_users(self) -> None:
        """Load users from storage file."""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r') as f:
                    data = json.load(f)
                    for username, user_data in data.items():
                        self.users[username] = User.from_dict(user_data)
            except (json.JSONDecodeError, FileNotFoundError):
                self.users = {}
    
    def save_users(self) -> None:
        """Save users to storage file."""
        data = {username: user.to_dict() for username, user in self.users.items()}
        with open(self.storage_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def create_user(self, username: str, email: str, password: str, phone: Optional[str] = None) -> User:
        """Create a new user."""
        if username in self.users:
            raise ValueError(f"User {username} already exists")
        
        user = User(username, email, phone)
        user.set_password(password)
        self.users[username] = user
        self.save_users()
        return user
    
    def get_user(self, username: str) -> Optional[User]:
        """Get user by username."""
        return self.users.get(username)
    
    def update_user(self, user: User) -> None:
        """Update user in storage."""
        self.users[user.username] = user
        self.save_users()
    
    def delete_user(self, username: str) -> bool:
        """Delete user from storage."""
        if username in self.users:
            del self.users[username]
            self.save_users()
            return True
        return False
    
    def list_users(self) -> List[str]:
        """List all usernames."""
        return list(self.users.keys())


class Session:
    """User session management."""
    
    def __init__(self, user: User):
        self.user = user
        self.session_id = secrets.token_urlsafe(32)
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.is_authenticated = False
        self.mfa_completed = False
        self.expires_at = datetime.now() + timedelta(hours=24)
    
    def is_valid(self) -> bool:
        """Check if session is still valid."""
        return (
            datetime.now() < self.expires_at and
            self.is_authenticated and
            (not self.user.is_mfa_enabled or self.mfa_completed)
        )
    
    def update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.now()
    
    def complete_mfa(self) -> None:
        """Mark MFA as completed for this session."""
        self.mfa_completed = True
        self.is_authenticated = True
    
    def to_dict(self) -> Dict:
        """Convert session to dictionary."""
        return {
            'session_id': self.session_id,
            'username': self.user.username,
            'created_at': self.created_at.isoformat(),
            'last_activity': self.last_activity.isoformat(),
            'is_authenticated': self.is_authenticated,
            'mfa_completed': self.mfa_completed,
            'expires_at': self.expires_at.isoformat()
        }


class SessionManager:
    """Manage user sessions."""
    
    def __init__(self):
        self.sessions = {}
    
    def create_session(self, user: User) -> Session:
        """Create a new session for user."""
        session = Session(user)
        self.sessions[session.session_id] = session
        return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID."""
        session = self.sessions.get(session_id)
        if session and session.is_valid():
            session.update_activity()
            return session
        elif session:
            # Remove expired session
            del self.sessions[session_id]
        return None
    
    def delete_session(self, session_id: str) -> bool:
        """Delete session."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False
    
    def cleanup_expired_sessions(self) -> None:
        """Remove expired sessions."""
        expired_sessions = [
            sid for sid, session in self.sessions.items()
            if not session.is_valid()
        ]
        for sid in expired_sessions:
            del self.sessions[sid]