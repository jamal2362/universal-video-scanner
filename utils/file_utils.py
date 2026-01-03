"""
File utility functions for cleaning up files
"""
import os
import shutil
import stat


def cleanup_temp_directory(temp_dir):
    """Clean up temporary directory to prevent accumulation of orphaned files"""
    try:
        if os.path.exists(temp_dir):
            for item in os.listdir(temp_dir):
                item_path = os.path.join(temp_dir, item)
                try:
                    if os.path.isfile(item_path) or os.path.islink(item_path):
                        os.unlink(item_path)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                except Exception as e:
                    print(f"Error deleting {item_path}: {e}")
            print(f"Cleaned up temp directory: {temp_dir}")
    except Exception as e:
        print(f"Error cleaning temp directory: {e}")


def make_writable(path):
    """Make a file or directory writable by adding write permissions"""
    try:
        current_permissions = os.stat(path).st_mode
        os.chmod(path, current_permissions | stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
    except Exception as e:
        print(f"Warning: Could not make {path} writable: {e}")


def copy_directory_with_writable_permissions(src_dir, dest_dir):
    """
    Copy a directory recursively and ensure all files are writable.
    
    Args:
        src_dir: Source directory path
        dest_dir: Destination directory path
    """
    try:
        if not os.path.exists(src_dir):
            print(f"Warning: Source directory does not exist: {src_dir}")
            return False
            
        # If destination exists, remove it first to ensure clean copy
        if os.path.exists(dest_dir):
            shutil.rmtree(dest_dir)
            
        # Copy the directory
        shutil.copytree(src_dir, dest_dir)
        
        # Make all files and directories writable
        for root, dirs, files in os.walk(dest_dir):
            # Make directory writable
            make_writable(root)
            
            # Make all files writable
            for file in files:
                file_path = os.path.join(root, file)
                make_writable(file_path)
        
        return True
    except Exception as e:
        print(f"Error copying directory from {src_dir} to {dest_dir}: {e}")
        return False


def copy_static_and_templates_to_data_dir(static_src, templates_src, data_dir):
    """
    Copy static and templates directories to the data directory where scanned_files.json is stored.
    This allows users to access and modify these files from the host system.
    
    Args:
        static_src: Path to source static directory (e.g., /app/static)
        templates_src: Path to source templates directory (e.g., /app/templates)
        data_dir: Path to data directory (e.g., /app/data)
    """
    print("=" * 50)
    print("Copying static and templates to data directory...")
    
    static_dest = os.path.join(data_dir, 'static')
    templates_dest = os.path.join(data_dir, 'templates')
    
    # Copy static directory
    if copy_directory_with_writable_permissions(static_src, static_dest):
        print(f"✓ Copied static/ to {static_dest}")
    else:
        print(f"✗ Failed to copy static/ to {static_dest}")
    
    # Copy templates directory
    if copy_directory_with_writable_permissions(templates_src, templates_dest):
        print(f"✓ Copied templates/ to {templates_dest}")
    else:
        print(f"✗ Failed to copy templates/ to {templates_dest}")
    
    print("=" * 50)
