import os

def create_unique_filename(filename):
    if not os.path.exists(filename):
        return filename
    
    base, ext = os.path.splitext(filename)
    i = 1
    while True:
        new_filename = f"{base}_{i}{ext}"
        if not os.path.exists(new_filename):
            return new_filename
        i += 1

def rename_file(old_path, new_name):
    """
    Renames a file from its old path to a new name.

    Parameters:
    old_path (str): The full path of the current file.
    new_name (str): The new name to give the file.

    Returns:
    None.
    """
    # Extract the directory and file name from the old path
    dir_path, file_name = os.path.split(old_path)

    # Construct the new path by joining the directory path and new file name
    new_path = os.path.join(dir_path, new_name)

    # Rename the file by moving it to the new path
    os.rename(old_path, new_path)