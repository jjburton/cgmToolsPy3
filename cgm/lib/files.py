import os
import re

def find_last_leading_number(directory):
    if not os.path.exists(directory):
        return -1
    
    files = os.listdir(directory)

    numbers = []
    for file in files:
        match = re.match(r'^(\d+)', file)  # Use regex to match leading digits
        if match:
            number = match.group(1)
            numbers.append(int(number))

    if numbers:
        sorted_numbers = sorted(numbers)
        return sorted_numbers[-1]
    else:
        return -1

def create_unique_filename(filename):
    # Remove or replace invalid characters
    path, basefilename = os.path.split(filename)
    filename = os.path.join(path, re.sub(r'[\\/:*?"<>|]', '_', basefilename))

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