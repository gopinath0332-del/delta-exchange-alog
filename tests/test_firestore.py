#!/usr/bin/env python3
"""Test Firestore integration."""
from core.config import get_config
from core.logger import setup_logging
from core.firestore_client import get_firestore_status

setup_logging(log_level='INFO')

print('')
print('=== Firestore Integration Test ===')
print('')

config = get_config()

print('')
status = get_firestore_status()
print('')

if status['connected']:
    print('✅ SUCCESS! Firestore is connected and ready')
    print(f'   Collection: {status["collection"]}')
    print('   All trades will be automatically journaled to Firestore.')
else:
    print('❌ Firestore not connected')
    print(f'   Enabled: {status["enabled"]}')
    print(f'   Collection: {status["collection"]}')
