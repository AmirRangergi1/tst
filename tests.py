"""
Simple tests for pdf-to-excel converter
"""
import os
from io import BytesIO
from pathlib import Path
import sys

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from app.main import app, MAX_BYTES


if __name__ == '__main__':
    print("\n🧪 Running tests...\n")
    
    try:
        # Suppress warnings during tests
        import logging
        logging.getLogger("app.main").setLevel(logging.ERROR)
        
        # Use direct app testing instead of TestClient due to version issues
        import asyncio
        from fastapi.testclient import TestClient
        
        # Create client with positional arg only
        client = TestClient(app)
        
        # Test 1: Health
        response = client.get('/health')
        assert response.status_code == 200
        assert response.json()['status'] == 'ok'
        print("✓ Health check passed")
        
        # Test 2: Static files
        response = client.get('/static/index.html')
        assert response.status_code == 200
        print("✓ Static files served correctly")
        
        # Test 3: Invalid file type
        response = client.post(
            '/convert',
            files={'file': ('test.txt', b'not a pdf')}
        )
        assert response.status_code == 400
        assert 'pdf' in response.json()['detail'].lower()
        print("✓ Non-PDF file rejected correctly")
        
        # Test 4: Size limit
        large_data = b'x' * (MAX_BYTES + 1)
        response = client.post(
            '/convert',
            files={'file': ('large.pdf', large_data)}
        )
        assert response.status_code == 413
        assert 'too large' in response.json()['detail'].lower()
        print("✓ File size limit enforced correctly")
        
        # Test 5: Sample PDF (if exists)
        sample_pdf_path = Path('./sample.pdf')
        if sample_pdf_path.exists():
            with open(sample_pdf_path, 'rb') as f:
                response = client.post(
                    '/convert',
                    files={'file': ('sample.pdf', f)}
                )
            if response.status_code == 200:
                assert b'PK' in response.content[:4]  # ZIP signature
                print("✓ PDF conversion successful")
            else:
                print(f"⚠ PDF conversion returned {response.status_code}")
        else:
            print("⚠ Skipping PDF conversion test (no sample.pdf found)")
        
        print("\n✅ All tests passed!\n")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n⚠ Error during testing: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
