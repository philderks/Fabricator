"""Test script for Fabricator API."""
from backend.core import create_app

app = create_app()
client = app.test_client()

print("=" * 60)
print("Fabricator API Tests")
print("=" * 60)


def assert_modrinth_status(response):
	if response.status_code == 200:
		return True
	assert response.status_code in (429, 502, 503, 504)
	data = response.get_json() or {}
	assert 'error' in data
	return False


# Test 1: Health Check
print("\n✓ Health Check")
response = client.get('/api/health')
assert response.status_code == 200

# Test 2: Server Status
print("✓ Server Status")
response = client.get('/api/status')
assert response.status_code in (200, 410)

# Test 3: Search Mods
print("✓ Search Mods (Sodium, Fabric, MC 1.20.1)")
response = client.get('/api/modrinth/search?query=sodium&mc_version=1.20.1&loader=fabric&limit=3')
if assert_modrinth_status(response):
	data = response.get_json()
	assert 'hits' in data and len(data['hits']) > 0

# Test 4: Get Mod Details
print("✓ Get Mod Details (Sodium)")
response = client.get('/api/modrinth/mod/sodium')
if assert_modrinth_status(response):
	data = response.get_json()
	assert 'title' in data

# Test 5: Get Mod Versions
print("✓ Get Mod Versions")
response = client.get('/api/modrinth/mod/sodium/versions?loaders=fabric&game_versions=1.20.1')
if assert_modrinth_status(response):
	data = response.get_json()
	assert isinstance(data, list) and len(data) > 0

# Test 6: Get Download URL
print("✓ Get Download URL")
response = client.get('/api/modrinth/mod/sodium/download-url?mc_version=1.20.1&loader=fabric')
if assert_modrinth_status(response):
	data = response.get_json()
	assert 'download_url' in data

# Test 7: Get Categories
print("✓ Get Categories")
response = client.get('/api/modrinth/categories')
if assert_modrinth_status(response):
	assert isinstance(response.get_json(), list)

# Test 8: Search Modpacks
print("✓ Search Modpacks (All of Fabric)")
response = client.get('/api/modrinth/modpacks/search?query=all%20of%20fabric&mc_version=1.20.1&loader=fabric&limit=3')
if assert_modrinth_status(response):
	data = response.get_json()
	assert 'hits' in data

# Test 9: Get Project Details
print("✓ Get Project Details (Sodium)")
response = client.get('/api/modrinth/project/sodium')
if assert_modrinth_status(response):
	data = response.get_json()
	assert 'title' in data

# Test 10: Resolve Project Version
print("✓ Resolve Project Version (Modpack)")
response = client.get('/api/modrinth/project/fabulously-optimized/resolve-version?mc_version=1.20.1&loader=fabric')
if response.status_code == 200:
	data = response.get_json()
	assert 'version' in data
elif response.status_code == 404:
	data = response.get_json()
	assert 'error' in data
else:
	raise AssertionError(f"Unexpected status for resolve-version: {response.status_code}")

# Test 11: Get Loaders
print("✓ Get Loaders")
response = client.get('/api/modrinth/loaders')
if assert_modrinth_status(response):
	assert isinstance(response.get_json(), list)

# Test 12: Install Validation
print("✓ Install Endpoint Validation")
response = client.post('/api/modrinth/mod/sodium/install', json={})
assert response.status_code == 400  # Should fail without mc_version

# Test 13: Modpack Install Validation
print("✓ Modpack Install Validation")
response = client.post('/api/modrinth/modpack/fabulously-optimized/install', json={})
assert response.status_code == 400  # Should fail without server_id

print("\n" + "=" * 60)
print("All tests passed! ✓")
print("=" * 60)
