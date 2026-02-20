#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration loader and manager.

This module provides a unified way to load and access configuration
throughout the project, replacing hardcoded values with configurable settings.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages application configuration loaded from JSON files."""
    
    def __init__(self, config_file: Optional[Path] = None, default_config: Optional[Path] = None):
        """
        Initialize ConfigManager.
        
        Args:
            config_file: Path to user configuration file (overrides defaults)
            default_config: Path to default configuration file
        """
        self.config = {}
        self.config_file = config_file
        self.default_config = default_config
        self.load()
    
    def load(self):
        """Load configuration from files."""
        # First load default config
        if self.default_config and self.default_config.exists():
            self._load_file(self.default_config, "default")
        
        # Then load user config (overrides defaults)
        if self.config_file and self.config_file.exists():
            self._load_file(self.config_file, "user")
    
    def _load_file(self, config_path: Path, source: str = "unknown"):
        """Load a configuration file."""
        try:
            with open(config_path, 'r') as f:
                config_data = json.load(f)
            
            # Remove comment fields
            self._remove_comments(config_data)
            
            # Merge with existing config
            self.config = self._deep_merge(self.config, config_data)
            
            logger.info(f"Loaded {source} configuration from {config_path}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {config_path}: {e}")
        except Exception as e:
            logger.error(f"Failed to load configuration from {config_path}: {e}")
    
    @staticmethod
    def _remove_comments(obj: Any):
        """Remove 'comment' fields from configuration recursively."""
        if isinstance(obj, dict):
            obj.pop("comment", None)
            for v in obj.values():
                ConfigManager._remove_comments(v)
        elif isinstance(obj, list):
            for item in obj:
                ConfigManager._remove_comments(item)
    
    @staticmethod
    def _deep_merge(base: Dict, override: Dict) -> Dict:
        """Deep merge override config into base config."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = ConfigManager._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by dot-notation key.
        
        Example:
            config.get("opentrons.controller_ip")  # -> "169.254.179.32"
        """
        keys = key.split(".")
        value = self.config
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any):
        """Set configuration value by dot-notation key."""
        keys = key.split(".")
        obj = self.config
        
        for k in keys[:-1]:
            if k not in obj:
                obj[k] = {}
            obj = obj[k]
        
        obj[keys[-1]] = value
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """Get entire configuration section."""
        return self.config.get(section, {})
    
    def save(self, config_file: Path):
        """Save current configuration to file."""
        try:
            with open(config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            logger.info(f"Saved configuration to {config_file}")
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")


# Global config instance
_global_config: Optional[ConfigManager] = None


def initialize_config(config_file: Optional[Path] = None, default_config: Optional[Path] = None):
    """Initialize global configuration manager."""
    global _global_config
    _global_config = ConfigManager(config_file, default_config)
    return _global_config


def get_config() -> ConfigManager:
    """Get global configuration instance."""
    global _global_config
    if _global_config is None:
        # Initialize with defaults
        default_path = Path(__file__).parent / "default_config.json"
        _global_config = ConfigManager(default_config=default_path)
    return _global_config


def get(key: str, default: Any = None) -> Any:
    """Shortcut to get configuration value."""
    return get_config().get(key, default)


def get_section(section: str) -> Dict[str, Any]:
    """Shortcut to get configuration section."""
    return get_config().get_section(section)


if __name__ == "__main__":
    # Test configuration loading
    logging.basicConfig(level=logging.INFO)
    
    config = initialize_config(
        default_config=Path(__file__).parent / "default_config.json"
    )
    
    print("Configuration loaded:")
    print(f"  Opentrons IP: {config.get('opentrons.controller_ip')}")
    print(f"  ARM IP: {config.get('arm.controller_ip')}")
    print(f"  Arduino Baud Rate: {config.get('arduino.baud_rate')}")
