"""Checkpoint management for resumable operations."""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Manages checkpoint data for resumable operations."""
    
    def __init__(self, checkpoint_file: Optional[Path] = None):
        """
        Initialize checkpoint manager.
        
        Args:
            checkpoint_file: Path to checkpoint file, or None to disable checkpointing
        """
        self.checkpoint_file = checkpoint_file
        self.data: Dict[str, Any] = {}
        self.enabled = checkpoint_file is not None
        
    def load(self) -> Dict[str, Any]:
        """
        Load checkpoint data from file.
        
        Returns:
            Dictionary containing checkpoint data, or empty dict if no checkpoint
        """
        if not self.enabled or not self.checkpoint_file.exists():
            return {}
            
        try:
            with open(self.checkpoint_file, 'r') as f:
                self.data = json.load(f)
                logger.info(f"Loaded checkpoint from {self.checkpoint_file}")
                return self.data
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}")
            return {}
    
    def save(self, data: Optional[Dict[str, Any]] = None) -> bool:
        """
        Save checkpoint data to file.
        
        Args:
            data: Data to save, or None to save current data
            
        Returns:
            True if saved successfully, False otherwise
        """
        if not self.enabled:
            return False
            
        if data is not None:
            self.data = data
            
        # Add timestamp
        self.data['last_updated'] = datetime.now().isoformat()
        
        try:
            with open(self.checkpoint_file, 'w') as f:
                json.dump(self.data, f, indent=2)
            logger.debug(f"Saved checkpoint to {self.checkpoint_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            return False
    
    def update(self, key: str, value: Any) -> None:
        """
        Update a single value in checkpoint data.
        
        Args:
            key: Key to update
            value: New value
        """
        self.data[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get value from checkpoint data.
        
        Args:
            key: Key to retrieve
            default: Default value if key not found
            
        Returns:
            Value from checkpoint or default
        """
        return self.data.get(key, default)
    
    def clear(self) -> None:
        """Clear checkpoint data and delete file if it exists."""
        self.data = {}
        if self.enabled and self.checkpoint_file and self.checkpoint_file.exists():
            try:
                self.checkpoint_file.unlink()
                logger.info(f"Deleted checkpoint file: {self.checkpoint_file}")
            except Exception as e:
                logger.error(f"Failed to delete checkpoint: {e}")
    
    def should_resume(self) -> bool:
        """
        Check if there's a valid checkpoint to resume from.
        
        Returns:
            True if checkpoint exists and is valid
        """
        if not self.enabled:
            return False
            
        if not self.checkpoint_file.exists():
            return False
            
        # Load and validate checkpoint
        data = self.load()
        return bool(data)
