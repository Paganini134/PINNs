"""
Authentication service for the PCM simulation system.
Handles login, registration, MFA setup and verification.
"""

import secrets
import urllib.parse
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timedelta
import re

from auth_models import User, UserStore, Session, SessionManager


class AuthenticationError(Exception):
    """Base exception for authentication errors."""
    pass


class InvalidCredentialsError(AuthenticationError):
    """Raised when credentials are invalid."""
    pass


class AccountLockedError(AuthenticationError):
    """Raised when account is locked."""
    pass


class MFARequiredError(AuthenticationError):
    """Raised when MFA is required but not provided."""
    pass


class AuthService:
    """Main authentication service."""
    
    def __init__(self, user_store: Optional[UserStore] = None):
        self.user_store = user_store or UserStore()
        self.session_manager = SessionManager()
        self.email_verification_codes = {}  # In-memory store for demo
        self.sms_verification_codes = {}    # In-memory store for demo
    
    def register_user(self, username: str, email: str, password: str, 
                     phone: Optional[str] = None) -> Tuple[bool, str]:
        """
        Register a new user.
        
        Returns:
            Tuple of (success, message)
        """
        # Validate input
        if not self._validate_username(username):
            return False, "Username must be 3-20 characters, alphanumeric and underscore only"
        
        if not self._validate_email(email):
            return False, "Invalid email format"
        
        if not self._validate_password(password):
            return False, "Password must be at least 8 characters with uppercase, lowercase, number and special character"
        
        if phone and not self._validate_phone(phone):
            return False, "Invalid phone number format"
        
        try:
            user = self.user_store.create_user(username, email, password, phone)
            return True, f"User {username} registered successfully"
        except ValueError as e:
            return False, str(e)
    
    def authenticate_user(self, username: str, password: str, 
                         mfa_token: Optional[str] = None,
                         backup_code: Optional[str] = None) -> Tuple[bool, str, Optional[Session]]:
        """
        Authenticate user with optional MFA.
        
        Returns:
            Tuple of (success, message, session)
        """
        user = self.user_store.get_user(username)
        if not user:
            return False, "Invalid credentials", None
        
        if user.is_account_locked():
            return False, "Account is locked due to failed login attempts", None
        
        if not user.is_active:
            return False, "Account is disabled", None
        
        # Check password
        if not user.check_password(password):
            user.record_failed_login()
            self.user_store.update_user(user)
            return False, "Invalid credentials", None
        
        # Create session
        session = self.session_manager.create_session(user)
        
        # Check MFA requirement
        if user.is_mfa_enabled:
            if backup_code:
                if user.use_backup_code(backup_code):
                    session.complete_mfa()
                    user.record_successful_login()
                    self.user_store.update_user(user)
                    return True, "Authentication successful (backup code)", session
                else:
                    return False, "Invalid backup code", None
            
            elif mfa_token:
                if user.verify_totp(mfa_token):
                    session.complete_mfa()
                    user.record_successful_login()
                    self.user_store.update_user(user)
                    return True, "Authentication successful", session
                else:
                    user.record_failed_login()
                    self.user_store.update_user(user)
                    return False, "Invalid MFA token", None
            else:
                # Password correct but MFA required
                session.is_authenticated = True  # Partial auth
                return False, "MFA token required", session
        else:
            # No MFA required
            session.complete_mfa()
            user.record_successful_login()
            self.user_store.update_user(user)
            return True, "Authentication successful", session
    
    def complete_mfa(self, session_id: str, mfa_token: Optional[str] = None,
                    backup_code: Optional[str] = None) -> Tuple[bool, str]:
        """
        Complete MFA authentication for an existing session.
        """
        session = self.session_manager.get_session(session_id)
        if not session:
            return False, "Invalid session"
        
        if not session.is_authenticated:
            return False, "Session not authenticated"
        
        if session.mfa_completed:
            return True, "MFA already completed"
        
        user = session.user
        
        if backup_code:
            if user.use_backup_code(backup_code):
                session.complete_mfa()
                user.record_successful_login()
                self.user_store.update_user(user)
                return True, "MFA completed with backup code"
            else:
                return False, "Invalid backup code"
        
        elif mfa_token:
            if user.verify_totp(mfa_token):
                session.complete_mfa()
                user.record_successful_login()
                self.user_store.update_user(user)
                return True, "MFA completed"
            else:
                user.record_failed_login()
                self.user_store.update_user(user)
                return False, "Invalid MFA token"
        
        return False, "MFA token or backup code required"
    
    def setup_totp(self, session_id: str) -> Tuple[bool, str, Optional[str]]:
        """
        Setup TOTP for a user.
        
        Returns:
            Tuple of (success, message, qr_code_base64)
        """
        session = self.session_manager.get_session(session_id)
        if not session or not session.is_valid():
            return False, "Invalid session", None
        
        user = session.user
        secret = user.enable_totp()
        qr_code = user.generate_qr_code()
        
        self.user_store.update_user(user)
        
        return True, f"TOTP enabled. Secret: {secret}", qr_code
    
    def generate_backup_codes(self, session_id: str) -> Tuple[bool, str, Optional[list]]:
        """
        Generate backup codes for a user.
        """
        session = self.session_manager.get_session(session_id)
        if not session or not session.is_valid():
            return False, "Invalid session", None
        
        user = session.user
        if not user.is_mfa_enabled:
            return False, "MFA not enabled", None
        
        backup_codes = user.generate_backup_codes()
        self.user_store.update_user(user)
        
        return True, "Backup codes generated", backup_codes
    
    def send_email_verification(self, email: str) -> Tuple[bool, str]:
        """
        Send email verification code (mock implementation).
        In production, this would integrate with an actual email service.
        """
        # Generate 6-digit code
        code = f"{secrets.randbelow(1000000):06d}"
        
        # Store code with expiration (5 minutes)
        self.email_verification_codes[email] = {
            'code': code,
            'expires_at': datetime.now() + timedelta(minutes=5)
        }
        
        # Mock email sending
        print(f"[EMAIL SIMULATION] Sending verification code {code} to {email}")
        
        return True, "Verification code sent to email"
    
    def verify_email_code(self, email: str, code: str) -> bool:
        """Verify email verification code."""
        stored_data = self.email_verification_codes.get(email)
        if not stored_data:
            return False
        
        if datetime.now() > stored_data['expires_at']:
            del self.email_verification_codes[email]
            return False
        
        if stored_data['code'] == code:
            del self.email_verification_codes[email]
            return True
        
        return False
    
    def send_sms_verification(self, phone: str) -> Tuple[bool, str]:
        """
        Send SMS verification code (mock implementation).
        In production, this would integrate with an SMS service like Twilio.
        """
        # Generate 6-digit code
        code = f"{secrets.randbelow(1000000):06d}"
        
        # Store code with expiration (5 minutes)
        self.sms_verification_codes[phone] = {
            'code': code,
            'expires_at': datetime.now() + timedelta(minutes=5)
        }
        
        # Mock SMS sending
        print(f"[SMS SIMULATION] Sending verification code {code} to {phone}")
        
        return True, "Verification code sent via SMS"
    
    def verify_sms_code(self, phone: str, code: str) -> bool:
        """Verify SMS verification code."""
        stored_data = self.sms_verification_codes.get(phone)
        if not stored_data:
            return False
        
        if datetime.now() > stored_data['expires_at']:
            del self.sms_verification_codes[phone]
            return False
        
        if stored_data['code'] == code:
            del self.sms_verification_codes[phone]
            return True
        
        return False
    
    def logout(self, session_id: str) -> bool:
        """Logout user by destroying session."""
        return self.session_manager.delete_session(session_id)
    
    def get_user_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get user information for a valid session."""
        session = self.session_manager.get_session(session_id)
        if not session or not session.is_valid():
            return None
        
        user = session.user
        return {
            'username': user.username,
            'email': user.email,
            'phone': user.phone,
            'is_mfa_enabled': user.is_mfa_enabled,
            'last_login': user.last_login.isoformat() if user.last_login else None,
            'created_at': user.created_at.isoformat(),
            'backup_codes_remaining': len(user.backup_codes)
        }
    
    def change_password(self, session_id: str, current_password: str, 
                       new_password: str) -> Tuple[bool, str]:
        """Change user password."""
        session = self.session_manager.get_session(session_id)
        if not session or not session.is_valid():
            return False, "Invalid session"
        
        user = session.user
        
        if not user.check_password(current_password):
            return False, "Current password is incorrect"
        
        if not self._validate_password(new_password):
            return False, "New password must be at least 8 characters with uppercase, lowercase, number and special character"
        
        user.set_password(new_password)
        self.user_store.update_user(user)
        
        return True, "Password changed successfully"
    
    def disable_mfa(self, session_id: str, password: str) -> Tuple[bool, str]:
        """Disable MFA for user."""
        session = self.session_manager.get_session(session_id)
        if not session or not session.is_valid():
            return False, "Invalid session"
        
        user = session.user
        
        if not user.check_password(password):
            return False, "Password is incorrect"
        
        user.is_mfa_enabled = False
        user.totp_secret = None
        user.backup_codes = []
        self.user_store.update_user(user)
        
        return True, "MFA disabled successfully"
    
    # Validation methods
    def _validate_username(self, username: str) -> bool:
        """Validate username format."""
        return bool(re.match(r'^[a-zA-Z0-9_]{3,20}$', username))
    
    def _validate_email(self, email: str) -> bool:
        """Validate email format."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    def _validate_password(self, password: str) -> bool:
        """Validate password strength."""
        if len(password) < 8:
            return False
        
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password)
        
        return has_upper and has_lower and has_digit and has_special
    
    def _validate_phone(self, phone: str) -> bool:
        """Validate phone number format."""
        # Simple validation for demo - accepts formats like +1234567890 or 1234567890
        pattern = r'^\+?[1-9]\d{9,14}$'
        return bool(re.match(pattern, phone.replace('-', '').replace(' ', '')))