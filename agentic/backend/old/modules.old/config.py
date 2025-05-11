# modules/config.py

"""
A client module for interacting with the configuration microservice.
Instead of reading from a local .config.yml file directly, this module
uses HTTP calls to the config_service endpoints to retrieve, add, update,
and remove configuration entries. Additionally, for basic configuration
(e.g. the config service URL), this module supports loading a local "config.yaml"
file.

Precedence for the CONFIG_SERVICE_URL:
  1. Environment variable CONFIG_SERVICE_URL
  2. The "CONFIG_SERVICE_URL" entry in config.yaml (if present)
  3. Default: "http://localhost:8001"

The configuration microservice persists its entries in ".config.yml".
"""

import os
import requests
import yaml

# Local configuration file for basic configurations.
LOCAL_CONFIG_FILE = "config.yaml"

def load_local_config() -> dict:
    """
    Loads basic local configuration from config.yaml.
    If the file does not exist or is empty, returns an empty dict.
    """
    if os.path.exists(LOCAL_CONFIG_FILE):
        try:
            with open(LOCAL_CONFIG_FILE, "r") as f:
                data = yaml.safe_load(f)
                return data if data is not None else {}
        except Exception:
            pass
    return {}

# Determine the CONFIG_SERVICE_URL:
default_url = "http://localhost:8001"
env_url = os.environ.get("CONFIG_SERVICE_URL")
if env_url is not None:
    CONFIG_SERVICE_URL = env_url
else:
    local_config = load_local_config()
    CONFIG_SERVICE_URL = local_config.get("CONFIG_SERVICE_URL", default_url)


def get_config(key: str, default: str = None) -> str:
    """
    Retrieve a configuration value by key using the config microservice.
    If the key does not exist and a default is provided, returns the default;
    otherwise, raises an Exception.
    """
    try:
        response = requests.get(f"{CONFIG_SERVICE_URL}/config/get", params={"key": key})
        if response.status_code == 200:
            data = response.json()
            return data["value"]
        elif default is not None:
            return default
        else:
            raise Exception(f"Configuration key not found: {key}")
    except Exception as e:
        raise Exception("Error getting configuration: " + str(e))


def list_config() -> dict:
    """
    List all configuration entries and return them as a dictionary.
    """
    try:
        response = requests.get(f"{CONFIG_SERVICE_URL}/config/list")
        if response.status_code == 200:
            # Response format: list of entries {"key": key, "value": value}
            entries = response.json()
            return {entry["key"]: entry["value"] for entry in entries}
        else:
            raise Exception("Failed to list configuration, status code: " + str(response.status_code))
    except Exception as e:
        raise Exception("Error listing configuration: " + str(e))


def add_config(key: str, value: str) -> None:
    """
    Add a new configuration entry.
    Raises an Exception if the key already exists.
    """
    payload = {"key": key, "value": value}
    try:
        response = requests.post(f"{CONFIG_SERVICE_URL}/config/add", json=payload)
        if response.status_code != 200:
            detail = response.json().get("detail", "Unknown error")
            raise Exception(detail)
    except Exception as e:
        raise Exception("Error adding configuration: " + str(e))


def update_config(key: str, value: str) -> None:
    """
    Update an existing configuration entry.
    Raises an Exception if the key does not exist.
    """
    payload = {"key": key, "value": value}
    try:
        response = requests.put(f"{CONFIG_SERVICE_URL}/config/update", json=payload)
        if response.status_code != 200:
            detail = response.json().get("detail", "Unknown error")
            raise Exception(detail)
    except Exception as e:
        raise Exception("Error updating configuration: " + str(e))


def set_config(key: str, value: str) -> None:
    """
    Convenience function to set a configuration entry.
    If the key exists, it calls update_config; otherwise it calls add_config.
    """
    try:
        current = list_config()
        if key in current:
            update_config(key, value)
        else:
            add_config(key, value)
    except Exception as e:
        raise Exception("Error setting configuration: " + str(e))


def remove_config(key: str) -> None:
    """
    Remove a specific configuration entry by key.
    """
    try:
        response = requests.delete(f"{CONFIG_SERVICE_URL}/config/remove", params={"key": key})
        if response.status_code != 200:
            detail = response.json().get("detail", "Unknown error")
            raise Exception(detail)
    except Exception as e:
        raise Exception("Error removing configuration: " + str(e))


def remove_all_config() -> None:
    """
    Remove all configuration entries.
    """
    try:
        response = requests.delete(f"{CONFIG_SERVICE_URL}/config/remove_all")
        if response.status_code != 200:
            raise Exception("Failed to remove all configuration entries")
    except Exception as e:
        raise Exception("Error removing all configuration: " + str(e))


# Example usage (for local debugging)
if __name__ == "__main__":
    try:
        # Print the current basic configuration (from the config service)
        print("Current configuration: ")
        print(list_config())
    
        # Set a sample configuration key/value.
        set_config("example_key", "example_value")
        print("After setting 'example_key':")
        print(list_config())
    
        # Retrieve a configuration value.
        value = get_config("example_key")
        print("Retrieved 'example_key':", value)
    
        # Remove the configuration entry.
        remove_config("example_key")
        print("After removal of 'example_key':")
        print(list_config())
    
        # Also, print out the basic local configuration details (if any).
        print("Local basic configuration (from config.yaml):")
        print(load_local_config())
    except Exception as err:
        print("Error:", err)
