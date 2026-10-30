"""Importing server folders Fabricator did not create."""
from __future__ import annotations

import importlib
import json
import time
import zipfile

import pytest


def _mod(name):
    # test_app_factory reloads backend.* — resolve through sys.modules so we
    # see the same module objects as the routes (see test_install_async_route).
    return importlib.import_module(f'backend.server.{name}')


def _vanilla_jar(path, mc='1.21.1'):
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('version.json', json.dumps({'id': mc}))


def _detect(path):
    return _mod('importer').inspect_folder(_mod('importer').validate_folder(str(path)))


def _wait_done(server_id, timeout=5.0):
    progress = _mod('install_progress')
    deadline = time.time() + timeout
    while progress.is_active(server_id) and time.time() < deadline:
        time.sleep(0.02)
    return progress.get(server_id)


@pytest.fixture
def fabric_server(tmp_path):
    root = tmp_path / 'external' / 'my-fabric'
    (root / 'mods').mkdir(parents=True)
    (root / 'server.properties').write_text('server-port=25600\nmotd=Hello\\u00A7r\npvp=false\nmax-players=7\n')
    (root / 'fabric-server-mc.1.21.1-loader.0.16.5-launcher.1.0.1.jar').write_bytes(b'x')
    (root / 'mods' / 'sodium.jar').write_bytes(b'sodium')
    (root / 'mods' / 'custom.jar').write_bytes(b'custom')
    return root


def test_detects_fabric_launcher(fabric_server):
    info = _detect(fabric_server)
    assert info['loader'] == 'fabric'
    assert info['version'] == '1.21.1'
    assert info['loaderVersion'] == '0.16.5'
    assert info['launch']['jar'].startswith('fabric-server-mc.')
    assert info['port'] == 25600
    assert info['modsCount'] == 2
    assert info['warnings'] == []


@pytest.mark.parametrize('lib,version,loader,mc', [
    ('libraries/net/neoforged/neoforge', '21.1.77', 'neoforge', '1.21.1'),
    ('libraries/net/minecraftforge/forge', '1.20.1-47.2.0', 'forge', '1.20.1'),
])
def test_detects_args_file_loaders(tmp_path, monkeypatch, lib, version, loader, mc):
    monkeypatch.setattr(_mod('importer'), 'is_windows', lambda: False)
    args = tmp_path / lib / version / 'unix_args.txt'
    args.parent.mkdir(parents=True)
    args.write_text('')
    (tmp_path / 'eula.txt').write_text('eula=true')
    info = _detect(tmp_path)
    assert (info['loader'], info['version']) == (loader, mc)
    assert info['launch'] == {
        'type': 'args_file', 'jar': None, 'jvm_args': [], 'program_args': ['nogui'],
        'args_file': f'{lib}/{version}/unix_args.txt',
    }


def test_detects_legacy_forge_jar(tmp_path):
    (tmp_path / 'forge-1.12.2-14.23.5.2860-universal.jar').write_bytes(b'x')
    (tmp_path / 'forge-1.12.2-14.23.5.2860-installer.jar').write_bytes(b'x')
    info = _detect(tmp_path)
    assert (info['loader'], info['version']) == ('forge', '1.12.2')
    assert info['launch']['jar'] == 'forge-1.12.2-14.23.5.2860-universal.jar'


def test_detects_paper_from_version_history(tmp_path):
    (tmp_path / 'version_history.json').write_text(json.dumps({'currentVersion': 'git-Purpur-2300 (MC: 1.21.1)'}))
    (tmp_path / 'purpur.jar').write_bytes(b'x')
    (tmp_path / 'plugins').mkdir()
    (tmp_path / 'plugins' / 'Essentials.jar').write_bytes(b'x')
    info = _detect(tmp_path)
    assert (info['loader'], info['version']) == ('purpur', '1.21.1')
    assert info['launch']['jar'] == 'purpur.jar'
    assert info['modsCount'] == 1


def test_detects_vanilla_from_jar_version(tmp_path):
    _vanilla_jar(tmp_path / 'server.jar', '1.20.4')
    info = _detect(tmp_path)
    assert (info['loader'], info['version']) == ('vanilla', '1.20.4')


def test_unknown_layout_warns_instead_of_guessing(tmp_path):
    (tmp_path / 'server.properties').write_text('')
    info = _detect(tmp_path)
    assert {'loader', 'version', 'launch'} <= set(info['warnings'])


@pytest.mark.parametrize('make_path', [
    lambda tmp: tmp / 'missing',
    lambda tmp: tmp,  # empty folder: nothing server-like in it
    lambda tmp: 'relative/path',
])
def test_rejects_non_server_folders(tmp_path, make_path):
    with pytest.raises(ValueError):
        _mod('importer').validate_folder(str(make_path(tmp_path)))


def test_inspect_route_rejects_bad_path(client, tmp_path):
    response = client.post('/api/servers/import/inspect', json={'path': str(tmp_path / 'nope')})
    assert response.status_code == 400


@pytest.fixture
def fake_modrinth(monkeypatch):
    from backend.modrinth import installed

    meta = {'projectId': 'AANobbMI', 'slug': 'sodium', 'title': 'Sodium', 'iconUrl': None,
            'versionId': 'v1', 'versionNumber': '0.6.0'}
    monkeypatch.setattr(
        installed, 'resolve_jar_files',
        lambda client, paths: {p.name: meta for p in paths if p.name == 'sodium.jar'},
    )


def test_copy_import_leaves_source_untouched(client, fabric_server, fake_modrinth):
    before = sorted(p.relative_to(fabric_server) for p in fabric_server.rglob('*'))
    response = client.post('/api/servers/import', json={'path': str(fabric_server), 'name': 'Copied'})
    assert response.status_code == 202, response.get_json()
    server = response.get_json()
    progress = _wait_done(server['id'])
    assert progress['phase'] == 'done', progress
    assert (progress['mods_total'], progress['mods_linked']) == (2, 1)
    assert progress['mods_unlinked'] == ['custom.jar']

    record = _mod('storage').get_server(server['id'])
    assert record['status'] == 'stopped'
    assert not record.get('external')
    assert record['loader'] == 'fabric' and record['port'] == 25600
    # server.properties values are carried into the record so a settings save
    # does not reset them.
    assert record['pvp'] is False and record['maxPlayers'] == 7
    assert record['modContent']['sodium.jar']['projectId'] == 'AANobbMI'

    copy_root = fabric_server.parents[1] / 'servers' / server['id']
    assert (copy_root / 'mods' / 'sodium.jar').is_file()
    assert sorted(p.relative_to(fabric_server) for p in fabric_server.rglob('*')) == before

    assert client.delete(f"/api/servers/{server['id']}").status_code == 200
    assert not copy_root.exists()
    assert fabric_server.is_dir()


def test_inplace_import_survives_delete(client, fabric_server, fake_modrinth):
    response = client.post('/api/servers/import', json={'path': str(fabric_server), 'mode': 'inplace'})
    assert response.status_code == 202, response.get_json()
    server_id = response.get_json()['id']
    assert _wait_done(server_id)['phase'] == 'done'
    assert _mod('storage').get_server(server_id)['external'] is True

    # The same folder cannot be registered twice.
    again = client.post('/api/servers/import', json={'path': str(fabric_server), 'mode': 'inplace', 'port': 25601})
    assert again.status_code == 400

    assert client.delete(f'/api/servers/{server_id}').status_code == 200
    assert (fabric_server / 'mods' / 'sodium.jar').is_file()


def test_create_route_cannot_claim_external(client):
    response = client.post('/api/servers', json={
        'name': 'x', 'version': '1.21.1', 'loader': 'fabric', 'port': 25570,
        'installPath': '', 'external': True,
    })
    assert response.status_code == 201
    assert 'external' not in _mod('storage').get_server(response.get_json()['id'])


def test_picks_the_forge_build_the_run_script_uses(tmp_path, monkeypatch):
    monkeypatch.setattr(_mod('importer'), 'is_windows', lambda: False)
    for build in ('1.20.1-47.1.0', '1.20.1-47.2.0'):
        args = tmp_path / 'libraries/net/minecraftforge/forge' / build / 'unix_args.txt'
        args.parent.mkdir(parents=True)
        args.write_text('')
    (tmp_path / 'run.sh').write_text('java @user_jvm_args.txt @libraries/net/minecraftforge/forge/1.20.1-47.1.0/unix_args.txt "$@"\n')
    (tmp_path / 'eula.txt').write_text('eula=true')
    info = _detect(tmp_path)
    assert info['loaderVersion'] == '47.1.0'
    assert '47.1.0' in info['launch']['args_file']


needs_non_root = pytest.mark.skipif(
    not hasattr(__import__('os'), 'geteuid') or __import__('os').geteuid() == 0,
    reason='permission bits are ignored for root / on Windows',
)


@needs_non_root
def test_unreadable_files_are_refused_not_a_500(client, fabric_server):
    secret = fabric_server / 'mods' / 'sodium.jar'
    secret.chmod(0o000)
    try:
        response = client.post('/api/servers/import/inspect', json={'path': str(fabric_server)})
    finally:
        secret.chmod(0o644)
    assert response.status_code == 400
    assert 'sodium.jar' in response.get_json()['error']


@needs_non_root
def test_read_only_files_only_warn(fabric_server):
    (fabric_server / 'server.properties').chmod(0o444)
    assert 'permissions' in _detect(fabric_server)['warnings']


def test_copy_does_not_share_symlinked_files_with_the_original(client, fabric_server, fake_modrinth):
    shared = fabric_server.parent / 'big-disk-world'
    shared.mkdir()
    (shared / 'level.dat').write_bytes(b'original')
    (fabric_server / 'world').symlink_to(shared, target_is_directory=True)

    response = client.post('/api/servers/import', json={'path': str(fabric_server)})
    assert response.status_code == 202, response.get_json()
    server_id = response.get_json()['id']
    assert _wait_done(server_id)['phase'] == 'done'

    copied_world = fabric_server.parents[1] / 'servers' / server_id / 'world'
    assert not copied_world.is_symlink()
    assert (copied_world / 'level.dat').read_bytes() == b'original'


def test_cannot_import_a_folder_containing_the_server_root(client, tmp_servers_root):
    # tmp_servers_root holds servers/ (the root); make it look like a server.
    (tmp_servers_root / 'server.jar').write_bytes(b'x')
    for mode in ('copy', 'inplace'):
        response = client.post('/api/servers/import', json={
            'path': str(tmp_servers_root), 'mode': mode, 'loader': 'vanilla', 'version': '1.21.1',
        })
        assert response.status_code == 400, mode


def test_symlink_back_to_an_ancestor_is_refused(tmp_path):
    (tmp_path / 'server.jar').write_bytes(b'x')
    (tmp_path / 'world').mkdir()
    (tmp_path / 'world' / 'loop').symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match='links back'):
        _detect(tmp_path)
