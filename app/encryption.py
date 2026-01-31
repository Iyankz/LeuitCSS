"""
LeuitCSS v1.0.0 - Encryption Module
AES-256 encryption for credential storage with master key from environment variable

Security Rules:
- Credential device disimpan terenkripsi
- Master key dari environment variable
- Principle of least privilege
"""

import os
import base64
import hashlib
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend


class CredentialEncryption:
    """
    AES-256 encryption handler for device credentials.
    Master key is derived from LEUITCSS_MASTER_KEY environment variable.
    """
    
    # Salt for key derivation (should be stored securely in production)
    SALT = b'leuitcss_v1_salt_2024'
    
    def __init__(self):
        self._fernet = None
        self._initialize_encryption()
    
    def _initialize_encryption(self):
        """Initialize Fernet encryption with derived key from master key"""
        master_key = os.environ.get('LEUITCSS_MASTER_KEY')
        
        if not master_key:
            raise EnvironmentError(
                "LEUITCSS_MASTER_KEY environment variable is not set. "
                "This is required for credential encryption."
            )
        
        # Derive a 32-byte key using PBKDF2
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.SALT,
            iterations=480000,  # OWASP recommended minimum
            backend=default_backend()
        )
        
        key = base64.urlsafe_b64encode(kdf.derive(master_key.encode()))
        self._fernet = Fernet(key)
    
    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt plaintext credential.
        
        Args:
            plaintext: The credential to encrypt (e.g., password)
            
        Returns:
            Base64 encoded encrypted string
        """
        if not plaintext:
            return ""
        
        encrypted = self._fernet.encrypt(plaintext.encode())
        return base64.urlsafe_b64encode(encrypted).decode()
    
    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt encrypted credential.
        
        Args:
            ciphertext: Base64 encoded encrypted string
            
        Returns:
            Decrypted plaintext credential
        """
        if not ciphertext:
            return ""
        
        encrypted = base64.urlsafe_b64decode(ciphertext.encode())
        decrypted = self._fernet.decrypt(encrypted)
        return decrypted.decode()


# Singleton instance
_encryption_instance = None

def get_encryption() -> CredentialEncryption:
    """Get singleton encryption instance"""
    global _encryption_instance
    if _encryption_instance is None:
        _encryption_instance = CredentialEncryption()
    return _encryption_instance


def encrypt_credential(plaintext: str) -> str:
    """Convenience function to encrypt a credential"""
    return get_encryption().encrypt(plaintext)


def decrypt_credential(ciphertext: str) -> str:
    """Convenience function to decrypt a credential"""
    return get_encryption().decrypt(ciphertext)


def generate_master_key() -> str:
    """
    Generate a secure random master key.
    This should be run once during initial setup and stored securely.
    
    Returns:
        A 32-character hex string suitable for LEUITCSS_MASTER_KEY
    """
    return os.urandom(32).hex()


if __name__ == "__main__":
    # Utility to generate a new master key
    print("Generated Master Key (store this securely):")
    print(generate_master_key())
