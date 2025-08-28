"""
Test suite for the PCM simulation authentication system.
Tests user registration, login, MFA functionality, and security features.
"""

import unittest
import tempfile
import os
import shutil
from datetime import datetime, timedelta

from auth_models import User, UserStore, Session, SessionManager
from auth_service import AuthService


class TestUser(unittest.TestCase):
    """Test User model functionality."""
    
    def setUp(self):
        self.user = User("testuser", "test@example.com", "+1234567890")
    
    def test_user_creation(self):
        """Test user creation with valid data."""
        self.assertEqual(self.user.username, "testuser")
        self.assertEqual(self.user.email, "test@example.com")
        self.assertEqual(self.user.phone, "+1234567890")
        self.assertTrue(self.user.is_active)
        self.assertFalse(self.user.is_mfa_enabled)
    
    def test_password_hashing(self):
        """Test password hashing and verification."""
        password = "TestPassword123!"
        self.user.set_password(password)
        
        self.assertIsNotNone(self.user.password_hash)
        self.assertTrue(self.user.check_password(password))
        self.assertFalse(self.user.check_password("wrongpassword"))
    
    def test_totp_setup(self):
        """Test TOTP setup and verification."""
        secret = self.user.enable_totp()
        
        self.assertIsNotNone(secret)
        self.assertTrue(self.user.is_mfa_enabled)
        self.assertIsNotNone(self.user.totp_secret)
        
        # Test QR code generation
        qr_code = self.user.generate_qr_code()
        self.assertIsInstance(qr_code, str)
        self.assertTrue(len(qr_code) > 100)  # Base64 image should be substantial
    
    def test_backup_codes(self):
        """Test backup code generation and usage."""
        backup_codes = self.user.generate_backup_codes()
        
        self.assertEqual(len(backup_codes), 8)
        self.assertEqual(len(self.user.backup_codes), 8)
        
        # Test using a backup code
        test_code = backup_codes[0]
        self.assertTrue(self.user.use_backup_code(test_code))
        self.assertEqual(len(self.user.backup_codes), 7)
        
        # Can't use the same code twice
        self.assertFalse(self.user.use_backup_code(test_code))
    
    def test_account_locking(self):
        """Test account locking after failed login attempts."""
        self.assertFalse(self.user.is_account_locked())
        
        # Record 5 failed attempts
        for _ in range(5):
            self.user.record_failed_login()
        
        self.assertTrue(self.user.is_account_locked())
        
        # Test successful login resets counter
        self.user.record_successful_login()
        self.assertFalse(self.user.is_account_locked())
        self.assertEqual(self.user.failed_login_attempts, 0)
    
    def test_user_serialization(self):
        """Test user to/from dictionary conversion."""
        self.user.set_password("TestPassword123!")
        self.user.enable_totp()
        
        user_dict = self.user.to_dict()
        restored_user = User.from_dict(user_dict)
        
        self.assertEqual(restored_user.username, self.user.username)
        self.assertEqual(restored_user.email, self.user.email)
        self.assertEqual(restored_user.phone, self.user.phone)
        self.assertEqual(restored_user.password_hash, self.user.password_hash)
        self.assertEqual(restored_user.is_mfa_enabled, self.user.is_mfa_enabled)


class TestUserStore(unittest.TestCase):
    """Test UserStore functionality."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_file = os.path.join(self.temp_dir, "test_users.json")
        self.user_store = UserStore(self.storage_file)
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
    
    def test_create_user(self):
        """Test user creation and storage."""
        user = self.user_store.create_user("testuser", "test@example.com", "TestPassword123!")
        
        self.assertIsInstance(user, User)
        self.assertEqual(user.username, "testuser")
        self.assertTrue(user.check_password("TestPassword123!"))
        
        # Test duplicate user creation fails
        with self.assertRaises(ValueError):
            self.user_store.create_user("testuser", "test2@example.com", "Password123!")
    
    def test_get_user(self):
        """Test user retrieval."""
        self.user_store.create_user("testuser", "test@example.com", "TestPassword123!")
        
        user = self.user_store.get_user("testuser")
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "testuser")
        
        # Test non-existent user
        user = self.user_store.get_user("nonexistent")
        self.assertIsNone(user)
    
    def test_persistence(self):
        """Test user data persistence across UserStore instances."""
        # Create user in first instance
        self.user_store.create_user("testuser", "test@example.com", "TestPassword123!")
        
        # Create new instance with same storage file
        new_store = UserStore(self.storage_file)
        user = new_store.get_user("testuser")
        
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "testuser")
        self.assertTrue(user.check_password("TestPassword123!"))


class TestSession(unittest.TestCase):
    """Test Session functionality."""
    
    def setUp(self):
        self.user = User("testuser", "test@example.com")
        self.session = Session(self.user)
    
    def test_session_creation(self):
        """Test session creation."""
        self.assertIsNotNone(self.session.session_id)
        self.assertEqual(self.session.user, self.user)
        self.assertFalse(self.session.is_authenticated)
        self.assertFalse(self.session.mfa_completed)
    
    def test_session_validity(self):
        """Test session validity checks."""
        # New session is not valid (not authenticated)
        self.assertFalse(self.session.is_valid())
        
        # Complete authentication
        self.session.is_authenticated = True
        self.session.mfa_completed = True
        self.assertTrue(self.session.is_valid())
        
        # Test expiration
        self.session.expires_at = datetime.now() - timedelta(hours=1)
        self.assertFalse(self.session.is_valid())


class TestAuthService(unittest.TestCase):
    """Test AuthService functionality."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        storage_file = os.path.join(self.temp_dir, "test_users.json")
        user_store = UserStore(storage_file)
        self.auth_service = AuthService(user_store)
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
    
    def test_user_registration(self):
        """Test user registration with validation."""
        # Valid registration
        success, message = self.auth_service.register_user(
            "testuser", "test@example.com", "TestPassword123!", "+1234567890"
        )
        self.assertTrue(success)
        
        # Invalid username
        success, message = self.auth_service.register_user(
            "ab", "test2@example.com", "TestPassword123!"
        )
        self.assertFalse(success)
        self.assertIn("Username", message)
        
        # Invalid email
        success, message = self.auth_service.register_user(
            "testuser2", "invalid-email", "TestPassword123!"
        )
        self.assertFalse(success)
        self.assertIn("email", message)
        
        # Weak password
        success, message = self.auth_service.register_user(
            "testuser3", "test3@example.com", "weak"
        )
        self.assertFalse(success)
        self.assertIn("Password", message)
        
        # Duplicate username
        success, message = self.auth_service.register_user(
            "testuser", "test4@example.com", "TestPassword123!"
        )
        self.assertFalse(success)
        self.assertIn("already exists", message)
    
    def test_authentication_without_mfa(self):
        """Test authentication for users without MFA."""
        # Register user
        self.auth_service.register_user("testuser", "test@example.com", "TestPassword123!")
        
        # Successful authentication
        success, message, session = self.auth_service.authenticate_user(
            "testuser", "TestPassword123!"
        )
        self.assertTrue(success)
        self.assertIsNotNone(session)
        self.assertTrue(session.is_valid())
        
        # Wrong password
        success, message, session = self.auth_service.authenticate_user(
            "testuser", "wrongpassword"
        )
        self.assertFalse(success)
        self.assertIsNone(session)
        
        # Non-existent user
        success, message, session = self.auth_service.authenticate_user(
            "nonexistent", "TestPassword123!"
        )
        self.assertFalse(success)
        self.assertIsNone(session)
    
    def test_authentication_with_mfa(self):
        """Test authentication for users with MFA enabled."""
        # Register user and enable MFA
        self.auth_service.register_user("testuser", "test@example.com", "TestPassword123!")
        user = self.auth_service.user_store.get_user("testuser")
        user.enable_totp()
        self.auth_service.user_store.update_user(user)
        
        # Authentication without MFA token should require MFA
        success, message, session = self.auth_service.authenticate_user(
            "testuser", "TestPassword123!"
        )
        self.assertFalse(success)
        self.assertIsNotNone(session)  # Partial session created
        self.assertIn("MFA", message)
        
        # Test backup code authentication
        backup_codes = user.generate_backup_codes()
        self.auth_service.user_store.update_user(user)
        
        success, message, session = self.auth_service.authenticate_user(
            "testuser", "TestPassword123!", backup_code=backup_codes[0]
        )
        self.assertTrue(success)
        self.assertIsNotNone(session)
        self.assertTrue(session.is_valid())
    
    def test_password_change(self):
        """Test password change functionality."""
        # Register user and authenticate
        self.auth_service.register_user("testuser", "test@example.com", "OldPassword123!")
        success, message, session = self.auth_service.authenticate_user(
            "testuser", "OldPassword123!"
        )
        
        # Change password
        success, message = self.auth_service.change_password(
            session.session_id, "OldPassword123!", "NewPassword123!"
        )
        self.assertTrue(success)
        
        # Test old password no longer works
        success, message, session = self.auth_service.authenticate_user(
            "testuser", "OldPassword123!"
        )
        self.assertFalse(success)
        
        # Test new password works
        success, message, session = self.auth_service.authenticate_user(
            "testuser", "NewPassword123!"
        )
        self.assertTrue(success)
    
    def test_mfa_setup_and_management(self):
        """Test MFA setup and management."""
        # Register user and authenticate
        self.auth_service.register_user("testuser", "test@example.com", "TestPassword123!")
        success, message, session = self.auth_service.authenticate_user(
            "testuser", "TestPassword123!"
        )
        
        # Setup TOTP
        success, message, qr_code = self.auth_service.setup_totp(session.session_id)
        self.assertTrue(success)
        self.assertIsNotNone(qr_code)
        self.assertIn("Secret:", message)
        
        # Generate backup codes
        success, message, backup_codes = self.auth_service.generate_backup_codes(session.session_id)
        self.assertTrue(success)
        self.assertIsNotNone(backup_codes)
        self.assertEqual(len(backup_codes), 8)
        
        # Disable MFA
        success, message = self.auth_service.disable_mfa(session.session_id, "TestPassword123!")
        self.assertTrue(success)
        
        # Verify MFA is disabled
        user_info = self.auth_service.get_user_info(session.session_id)
        self.assertFalse(user_info['is_mfa_enabled'])
    
    def test_validation_methods(self):
        """Test input validation methods."""
        # Username validation
        self.assertTrue(self.auth_service._validate_username("validuser123"))
        self.assertFalse(self.auth_service._validate_username("ab"))  # Too short
        self.assertFalse(self.auth_service._validate_username("user@invalid"))  # Invalid chars
        
        # Email validation
        self.assertTrue(self.auth_service._validate_email("test@example.com"))
        self.assertFalse(self.auth_service._validate_email("invalid-email"))
        
        # Password validation
        self.assertTrue(self.auth_service._validate_password("Password123!"))
        self.assertFalse(self.auth_service._validate_password("weak"))  # Too weak
        self.assertFalse(self.auth_service._validate_password("password"))  # No uppercase/number/special
        
        # Phone validation
        self.assertTrue(self.auth_service._validate_phone("+1234567890"))
        self.assertTrue(self.auth_service._validate_phone("1234567890"))
        self.assertFalse(self.auth_service._validate_phone("123"))  # Too short


if __name__ == '__main__':
    unittest.main()