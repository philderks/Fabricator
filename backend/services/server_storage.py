"""JSON-based storage for server data."""
import json
import uuid
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime


SERVERS_FILE = Path("servers.json")


def _ensure_file_exists():
    """Create servers.json if it doesn't exist."""
    if not SERVERS_FILE.exists():
        SERVERS_FILE.write_text("[]")


def load_servers() -> List[Dict[str, Any]]:
    """Load all servers from JSON file.
    
    Returns:
        List of server dictionaries
    """
    _ensure_file_exists()
    try:
        with open(SERVERS_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []


def save_servers(servers: List[Dict[str, Any]]) -> None:
    """Save servers list to JSON file.
    
    Args:
        servers: List of server dictionaries
    """
    with open(SERVERS_FILE, 'w') as f:
        json.dump(servers, f, indent=2)


def generate_server_id() -> str:
    """Generate a unique server ID.
    
    Returns:
        Server ID string (e.g., 'srv_abc123')
    """
    return f"srv_{uuid.uuid4().hex[:8]}"


def get_all_servers() -> List[Dict[str, Any]]:
    """Get all servers.
    
    Returns:
        List of all servers
    """
    return load_servers()


def get_server(server_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific server by ID.
    
    Args:
        server_id: Server ID
        
    Returns:
        Server dictionary or None if not found
    """
    servers = load_servers()
    return next((s for s in servers if s.get('id') == server_id), None)


def create_server(server_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new server.
    
    Args:
        server_data: Server configuration data
        
    Returns:
        Created server with generated ID and metadata
    """
    servers = load_servers()
    
    # Generate ID and add metadata
    new_server = {
        'id': generate_server_id(),
        'status': 'stopped',
        'createdAt': datetime.utcnow().isoformat() + 'Z',
        'updatedAt': datetime.utcnow().isoformat() + 'Z',
        **server_data
    }
    
    servers.append(new_server)
    save_servers(servers)
    
    return new_server


def update_server(server_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update an existing server.
    
    Args:
        server_id: Server ID
        updates: Dictionary of fields to update
        
    Returns:
        Updated server or None if not found
    """
    servers = load_servers()
    
    for server in servers:
        if server.get('id') == server_id:
            server.update(updates)
            server['updatedAt'] = datetime.utcnow().isoformat() + 'Z'
            save_servers(servers)
            return server
    
    return None


def delete_server(server_id: str) -> bool:
    """Delete a server.
    
    Args:
        server_id: Server ID
        
    Returns:
        True if deleted, False if not found
    """
    servers = load_servers()
    initial_count = len(servers)
    
    servers = [s for s in servers if s.get('id') != server_id]
    
    if len(servers) < initial_count:
        save_servers(servers)
        return True
    
    return False


def update_server_status(server_id: str, status: str) -> Optional[Dict[str, Any]]:
    """Update server status.
    
    Args:
        server_id: Server ID
        status: New status ('stopped', 'starting', 'running', 'stopping')
        
    Returns:
        Updated server or None if not found
    """
    return update_server(server_id, {'status': status})
