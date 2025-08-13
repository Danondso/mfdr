"""Tests for CheckpointManager."""

import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
from datetime import datetime

from mfdr.services.checkpoint_manager import CheckpointManager


class TestCheckpointManagerInit:
    """Test initialization of CheckpointManager."""
    
    def test_init_with_checkpoint_file(self, temp_dir):
        """Test initialization with checkpoint file."""
        checkpoint_file = temp_dir / "checkpoint.json"
        manager = CheckpointManager(checkpoint_file)
        
        assert manager.checkpoint_file == checkpoint_file
        assert manager.enabled is True
        assert manager.data == {}
    
    def test_init_without_checkpoint_file(self):
        """Test initialization without checkpoint file (disabled)."""
        manager = CheckpointManager(None)
        
        assert manager.checkpoint_file is None
        assert manager.enabled is False
        assert manager.data == {}


class TestCheckpointManagerLoad:
    """Test loading checkpoint data."""
    
    @pytest.fixture
    def manager(self, temp_dir):
        """Create manager with temp checkpoint file."""
        checkpoint_file = temp_dir / "checkpoint.json"
        return CheckpointManager(checkpoint_file)
    
    def test_load_disabled_manager(self):
        """Test load when checkpointing is disabled."""
        manager = CheckpointManager(None)
        result = manager.load()
        
        assert result == {}
        assert manager.data == {}
    
    def test_load_nonexistent_file(self, manager):
        """Test load when checkpoint file doesn't exist."""
        result = manager.load()
        
        assert result == {}
        assert manager.data == {}
    
    def test_load_existing_file(self, manager, temp_dir):
        """Test load from existing checkpoint file."""
        checkpoint_data = {
            "processed_files": ["file1.mp3", "file2.mp3"],
            "stats": {"total": 2, "good": 2},
            "last_updated": "2025-01-01T12:00:00"
        }
        
        # Create checkpoint file
        checkpoint_file = temp_dir / "checkpoint.json"
        checkpoint_file.write_text(json.dumps(checkpoint_data))
        
        result = manager.load()
        
        assert result == checkpoint_data
        assert manager.data == checkpoint_data
    
    def test_load_corrupted_file(self, manager, temp_dir):
        """Test load from corrupted checkpoint file."""
        # Create corrupted JSON file
        checkpoint_file = temp_dir / "checkpoint.json"
        checkpoint_file.write_text("invalid json{")
        
        with patch('mfdr.services.checkpoint_manager.logger') as mock_logger:
            result = manager.load()
        
        assert result == {}
        assert manager.data == {}
        mock_logger.warning.assert_called_once()
    
    def test_load_permission_error(self, manager, temp_dir):
        """Test load when file cannot be read."""
        checkpoint_file = temp_dir / "checkpoint.json"
        checkpoint_file.write_text('{"test": "data"}')
        
        with patch('builtins.open', side_effect=PermissionError("Access denied")):
            with patch('mfdr.services.checkpoint_manager.logger') as mock_logger:
                result = manager.load()
        
        assert result == {}
        mock_logger.warning.assert_called_once()


class TestCheckpointManagerSave:
    """Test saving checkpoint data."""
    
    @pytest.fixture
    def manager(self, temp_dir):
        """Create manager with temp checkpoint file."""
        checkpoint_file = temp_dir / "checkpoint.json"
        return CheckpointManager(checkpoint_file)
    
    def test_save_disabled_manager(self):
        """Test save when checkpointing is disabled."""
        manager = CheckpointManager(None)
        result = manager.save({"test": "data"})
        
        assert result is False
    
    def test_save_with_data_parameter(self, manager, temp_dir):
        """Test save with data parameter."""
        test_data = {"processed": ["file1.mp3"], "stats": {"total": 1}}
        
        result = manager.save(test_data)
        
        assert result is True
        assert manager.data["processed"] == ["file1.mp3"]
        assert manager.data["stats"] == {"total": 1}
        assert "last_updated" in manager.data
        
        # Verify file was written
        checkpoint_file = temp_dir / "checkpoint.json"
        assert checkpoint_file.exists()
        saved_data = json.loads(checkpoint_file.read_text())
        assert saved_data["processed"] == ["file1.mp3"]
        assert "last_updated" in saved_data
    
    def test_save_current_data(self, manager, temp_dir):
        """Test save without data parameter (save current data)."""
        manager.data = {"current": "data"}
        
        result = manager.save()
        
        assert result is True
        assert "last_updated" in manager.data
        
        # Verify file was written
        checkpoint_file = temp_dir / "checkpoint.json"
        assert checkpoint_file.exists()
        saved_data = json.loads(checkpoint_file.read_text())
        assert saved_data["current"] == "data"
    
    def test_save_permission_error(self, manager):
        """Test save when file cannot be written."""
        with patch('builtins.open', side_effect=PermissionError("Access denied")):
            with patch('mfdr.services.checkpoint_manager.logger') as mock_logger:
                result = manager.save({"test": "data"})
        
        assert result is False
        mock_logger.error.assert_called_once()
    
    def test_save_adds_timestamp(self, manager, temp_dir):
        """Test that save adds a timestamp."""
        with patch('mfdr.services.checkpoint_manager.datetime') as mock_datetime:
            mock_datetime.now.return_value.isoformat.return_value = "2025-01-01T12:00:00"
            
            result = manager.save({"test": "data"})
        
        assert result is True
        assert manager.data["last_updated"] == "2025-01-01T12:00:00"


class TestCheckpointManagerUpdate:
    """Test updating checkpoint data."""
    
    @pytest.fixture
    def manager(self, temp_dir):
        """Create manager with temp checkpoint file."""
        checkpoint_file = temp_dir / "checkpoint.json"
        return CheckpointManager(checkpoint_file)
    
    def test_update_new_key(self, manager):
        """Test updating a new key."""
        manager.update("test_key", "test_value")
        
        assert manager.data["test_key"] == "test_value"
    
    def test_update_existing_key(self, manager):
        """Test updating an existing key."""
        manager.data = {"existing": "old_value"}
        manager.update("existing", "new_value")
        
        assert manager.data["existing"] == "new_value"
    
    def test_update_complex_value(self, manager):
        """Test updating with complex data types."""
        complex_data = {"nested": {"data": [1, 2, 3]}}
        manager.update("complex", complex_data)
        
        assert manager.data["complex"] == complex_data


class TestCheckpointManagerGet:
    """Test getting checkpoint data."""
    
    @pytest.fixture
    def manager(self, temp_dir):
        """Create manager with temp checkpoint file."""
        checkpoint_file = temp_dir / "checkpoint.json"
        manager = CheckpointManager(checkpoint_file)
        manager.data = {
            "existing_key": "existing_value",
            "number": 42,
            "list": [1, 2, 3]
        }
        return manager
    
    def test_get_existing_key(self, manager):
        """Test getting an existing key."""
        result = manager.get("existing_key")
        assert result == "existing_value"
    
    def test_get_nonexistent_key_no_default(self, manager):
        """Test getting nonexistent key without default."""
        result = manager.get("nonexistent")
        assert result is None
    
    def test_get_nonexistent_key_with_default(self, manager):
        """Test getting nonexistent key with default."""
        result = manager.get("nonexistent", "default_value")
        assert result == "default_value"
    
    def test_get_complex_data(self, manager):
        """Test getting complex data types."""
        result = manager.get("list")
        assert result == [1, 2, 3]


class TestCheckpointManagerClear:
    """Test clearing checkpoint data."""
    
    @pytest.fixture
    def manager(self, temp_dir):
        """Create manager with temp checkpoint file."""
        checkpoint_file = temp_dir / "checkpoint.json"
        return CheckpointManager(checkpoint_file)
    
    def test_clear_disabled_manager(self):
        """Test clear when checkpointing is disabled."""
        manager = CheckpointManager(None)
        manager.data = {"test": "data"}
        
        manager.clear()
        
        assert manager.data == {}
    
    def test_clear_with_existing_file(self, manager, temp_dir):
        """Test clear when checkpoint file exists."""
        # Create checkpoint file and set data
        checkpoint_file = temp_dir / "checkpoint.json"
        checkpoint_file.write_text('{"test": "data"}')
        manager.data = {"test": "data"}
        
        manager.clear()
        
        assert manager.data == {}
        assert not checkpoint_file.exists()
    
    def test_clear_nonexistent_file(self, manager):
        """Test clear when checkpoint file doesn't exist."""
        manager.data = {"test": "data"}
        
        manager.clear()
        
        assert manager.data == {}
    
    def test_clear_permission_error(self, manager, temp_dir):
        """Test clear when file cannot be deleted."""
        checkpoint_file = temp_dir / "checkpoint.json"
        checkpoint_file.write_text('{"test": "data"}')
        manager.data = {"test": "data"}
        
        # Patch the unlink method at the Path class level
        with patch('pathlib.Path.unlink', side_effect=PermissionError("Access denied")):
            with patch('mfdr.services.checkpoint_manager.logger') as mock_logger:
                manager.clear()
        
        assert manager.data == {}
        mock_logger.error.assert_called_once()


class TestCheckpointManagerShouldResume:
    """Test should_resume functionality."""
    
    @pytest.fixture
    def manager(self, temp_dir):
        """Create manager with temp checkpoint file."""
        checkpoint_file = temp_dir / "checkpoint.json"
        return CheckpointManager(checkpoint_file)
    
    def test_should_resume_disabled_manager(self):
        """Test should_resume when checkpointing is disabled."""
        manager = CheckpointManager(None)
        
        result = manager.should_resume()
        
        assert result is False
    
    def test_should_resume_nonexistent_file(self, manager):
        """Test should_resume when checkpoint file doesn't exist."""
        result = manager.should_resume()
        
        assert result is False
    
    def test_should_resume_valid_checkpoint(self, manager, temp_dir):
        """Test should_resume with valid checkpoint data."""
        checkpoint_data = {
            "processed_files": ["file1.mp3"],
            "stats": {"total": 1},
            "last_updated": "2025-01-01T12:00:00"
        }
        
        # Create checkpoint file
        checkpoint_file = temp_dir / "checkpoint.json"
        checkpoint_file.write_text(json.dumps(checkpoint_data))
        
        result = manager.should_resume()
        
        assert result is True
        assert manager.data == checkpoint_data
    
    def test_should_resume_empty_checkpoint(self, manager, temp_dir):
        """Test should_resume with empty checkpoint data."""
        # Create empty checkpoint file
        checkpoint_file = temp_dir / "checkpoint.json"
        checkpoint_file.write_text('{}')
        
        result = manager.should_resume()
        
        assert result is False
    
    def test_should_resume_corrupted_checkpoint(self, manager, temp_dir):
        """Test should_resume with corrupted checkpoint file."""
        # Create corrupted checkpoint file
        checkpoint_file = temp_dir / "checkpoint.json"
        checkpoint_file.write_text('invalid json')
        
        result = manager.should_resume()
        
        assert result is False


class TestCheckpointManagerIntegration:
    """Test integration scenarios."""
    
    def test_full_workflow(self, temp_dir):
        """Test complete checkpoint workflow."""
        checkpoint_file = temp_dir / "test_checkpoint.json"
        manager = CheckpointManager(checkpoint_file)
        
        # Initially should not resume
        assert manager.should_resume() is False
        
        # Update some data
        manager.update("processed", ["file1.mp3"])
        manager.update("stats", {"total": 1, "good": 1})
        
        # Save checkpoint
        assert manager.save() is True
        assert checkpoint_file.exists()
        
        # Create new manager and load
        manager2 = CheckpointManager(checkpoint_file)
        assert manager2.should_resume() is True
        
        data = manager2.load()
        assert data["processed"] == ["file1.mp3"]
        assert data["stats"]["total"] == 1
        
        # Clear checkpoint
        manager2.clear()
        assert not checkpoint_file.exists()
        assert manager2.data == {}
    
    def test_disabled_workflow(self):
        """Test workflow when checkpointing is disabled."""
        manager = CheckpointManager(None)
        
        # All operations should be safe but inactive
        assert manager.should_resume() is False
        assert manager.load() == {}
        assert manager.save({"test": "data"}) is False
        
        manager.update("key", "value")
        assert manager.get("key") == "value"
        
        manager.clear()
        assert manager.data == {}