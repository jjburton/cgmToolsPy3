## Installation

To install `cgmTools`, follow these steps:

### 1. Clone the Repository

Open a terminal and run:

```
git clone https://github.com/jjburton/cgmTools.git
```

### 2. Set Up the Environment

You’ll need to add the `cgmTools` directory to your Python or Maya script path.

#### For Maya

1. Locate your `maya.env` file. Common locations:

    - **Windows:**  
      Documents/maya/<version>/maya.env

    - **macOS/Linux:**  
      ~/Library/Preferences/Autodesk/maya/<version>/maya.env

2. Add this line to the file, replacing the path with where you cloned the repo:

```
REPOSPATH = D:/path/to/cgmTools
MAYA_SCRIPT_PATH = %REPOSPATH%/;
PYTHONPATH = %REPOSPATH%;
```

### 3. Launch Maya

Once Maya starts, verify installation by running this in the Script Editor (Python tab):

    import cgm
    print(cgm.__path__)

If installed correctly, it will print the path to the `cgmTools` directory.

### 4. Load the Tools

To open the cgmToolbox UI and finish setup, run the following command in the MEL tab of the Script Editor:

    cgmToolbox

This will launch the main cgmTools interface.

---

## Updating

To update your local copy of `cgmTools`:

1. Navigate to the folder where you cloned the repo:

    cd /path/to/cgmTools

2. Pull the latest changes:

    git pull

3. Restart Maya to apply the updates.

If you encounter any issues after updating, try deleting Maya’s script cache or preferences.
