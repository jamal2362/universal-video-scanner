# Copyright (c) 2026 U3knOwn
# Licensed under the MIT License. See LICENSE file in the project root for full license information.
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
    """Make a file or directory writable by adding write permissions for user and group"""
    try:
        current_permissions = os.stat(path).st_mode
        os.chmod(path, current_permissions | stat.S_IWUSR | stat.S_IWGRP)
    except Exception as e:
        print(f"Warning: Could not make {path} writable: {e}")


def copy_directory_with_writable_permissions(src_dir, dest_dir, force=False):
    """
    Copy a directory recursively and ensure all files are writable.
    
    Args:
        src_dir: Source directory path
        dest_dir: Destination directory path
        force: If True, always overwrite. If False, skip if destination exists.
        
    Returns:
        bool: True if copy was successful, False otherwise
    """
    try:
        if not os.path.exists(src_dir):
            print(f"Warning: Source directory does not exist: {src_dir}")
            return False
        
        # If destination exists and force is False, skip copy
        if os.path.exists(dest_dir) and not force:
            return True  # Already exists, consider it a success
        
        # Safety check: ensure dest_dir is a subdirectory within a data/config directory
        # to prevent accidental deletion of important system files
        dest_dir_abs = os.path.abspath(dest_dir)
        if os.path.exists(dest_dir):
            # Additional safety: only remove if destination is within expected paths
            safe_paths = ['/app/data', '/tmp', os.path.expanduser('~')]
            is_safe = any(dest_dir_abs.startswith(os.path.abspath(p)) for p in safe_paths)
            if not is_safe:
                print(f"Warning: Refusing to remove directory outside safe paths: {dest_dir}")
                return False
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


def get_directory_version(directory):
    """
    Calculate a version hash for a directory based on file names and sizes.
    This is used to detect when the container's bundled files have been updated.
    
    Args:
        directory: Path to directory to hash
        
    Returns:
        str: SHA256 hash representing the directory version, or empty string if directory doesn't exist
    """
    import hashlib
    
    if not os.path.exists(directory):
        return ""
    
    hash_obj = hashlib.sha256()
    
    # Walk through directory and hash file paths and sizes
    # We use size instead of content for performance
    for root, dirs, files in sorted(os.walk(directory)):
        # Sort for consistent ordering
        dirs.sort()
        for filename in sorted(files):
            filepath = os.path.join(root, filename)
            try:
                # Hash relative path and file size
                rel_path = os.path.relpath(filepath, directory)
                hash_obj.update(rel_path.encode())
                hash_obj.update(str(os.path.getsize(filepath)).encode())
            except Exception:
                continue
    
    return hash_obj.hexdigest()


def copy_static_and_templates_to_data_dir(static_src, templates_src, data_dir):
    """
    Copy static and templates directories to the data directory where scanned_files.json is stored.
    This allows users to access and modify these files from the host system.
    
    Files are only copied if:
    - The destination directories don't exist (first run), OR
    - The source directories have changed (Docker container update)
    
    This preserves user customizations across container restarts while ensuring
    updates are applied when the container is updated.
    
    Args:
        static_src: Path to source static directory (e.g., /app/static)
        templates_src: Path to source templates directory (e.g., /app/templates)
        data_dir: Path to data directory (e.g., /app/data)
        
    Returns:
        tuple: (static_success, templates_success) - boolean values indicating if each copy succeeded
    """
    print("=" * 50)
    print("Checking static and templates directories...")
    
    static_dest = os.path.join(data_dir, 'static')
    templates_dest = os.path.join(data_dir, 'templates')
    version_file = os.path.join(data_dir, '.static_templates_version')
    
    # Calculate current version of source directories
    static_version = get_directory_version(static_src)
    templates_version = get_directory_version(templates_src)
    
    # Handle case where directories don't exist (return empty string)
    if not static_version and not templates_version:
        print("Warning: Source directories not found")
        return False, False
    
    current_version = f"{static_version}:{templates_version}"
    
    # Check if we need to update
    stored_version = None
    need_update = False
    
    if os.path.exists(version_file):
        try:
            with open(version_file, 'r') as f:
                stored_version = f.read().strip()
        except Exception:
            pass
    
    # Determine if update is needed
    if not os.path.exists(static_dest) or not os.path.exists(templates_dest):
        print("First run detected - copying directories...")
        need_update = True
    elif stored_version != current_version:
        print("Container update detected - updating directories...")
        print(f"  Previous version: {stored_version[:16] if stored_version else 'none'}...")
        print(f"  Current version:  {current_version[:16]}...")
        need_update = True
    else:
        print("Directories up to date - preserving user customizations")
        print("=" * 50)
        return True, True
    
    # Copy directories (force=True to overwrite)
    static_success = copy_directory_with_writable_permissions(static_src, static_dest, force=need_update)
    if static_success:
        print(f"[OK] Copied static/ to {static_dest}")
    else:
        print(f"[ERROR] Failed to copy static/ to {static_dest}")
    
    templates_success = copy_directory_with_writable_permissions(templates_src, templates_dest, force=need_update)
    if templates_success:
        print(f"[OK] Copied templates/ to {templates_dest}")
    else:
        print(f"[ERROR] Failed to copy templates/ to {templates_dest}")
    
    # Save version file
    if static_success and templates_success:
        try:
            with open(version_file, 'w') as f:
                f.write(current_version)
            print(f"[OK] Version tracking updated")
        except Exception as e:
            print(f"Warning: Could not save version file: {e}")
    
    print("=" * 50)
    
    return static_success, templates_success
