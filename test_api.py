"""Test script for Fabricator API."""
from backend.app import create_app

app = create_app()
client = app.test_client()

print("=" * 60)
print("Fabricator API Tests")
print("=" * 60)

# Test 1: Health Check
print("\n✓ Health Check")
response = client.get('/api/health')
assert response.status_code == 200

# Test 2: Server Status
print("✓ Server Status")
response = client.get('/api/status')
assert response.status_code == 200

# Test 3: Search Mods
print("✓ Search Mods (Sodium, Fabric, MC 1.20.1)")
response = client.get('/api/modrinth/search?query=sodium&mc_version=1.20.1&loader=fabric&limit=3')
assert response.status_code == 200
data = response.get_json()
assert 'hits' in data and len(data['hits']) > 0

# Test 4: Get Mod Details
print("✓ Get Mod Details (Sodium)")
response = client.get('/api/modrinth/mod/sodium')
assert response.status_code == 200
data = response.get_json()
assert 'title' in data

# Test 5: Get Mod Versions
print("✓ Get Mod Versions")
response = client.get('/api/modrinth/mod/sodium/versions?loaders=fabric&game_versions=1.20.1')
assert response.status_code == 200
data = response.get_json()
assert isinstance(data, list) and len(data) > 0

# Test 6: Get Download URL
print("✓ Get Download URL")
response = client.get('/api/modrinth/mod/sodium/download-url?mc_version=1.20.1&loader=fabric')
assert response.status_code == 200
data = response.get_json()
assert 'download_url' in data

# Test 7: Get Categories
print("✓ Get Categories")
response = client.get('/api/modrinth/categories')
assert response.status_code == 200
assert isinstance(response.get_json(), list)

# Test 8: Get Loaders
print("✓ Get Loaders")
response = client.get('/api/modrinth/loaders')
assert response.status_code == 200
assert isinstance(response.get_json(), list)

# Test 9: Install Validation
print("✓ Install Endpoint Validation")
response = client.post('/api/modrinth/mod/sodium/install', json={})
assert response.status_code == 400  # Should fail without mc_version

print("\n" + "=" * 60)
print("All tests passed! ✓")
print("=" * 60)
