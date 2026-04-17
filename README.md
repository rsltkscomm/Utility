# UtilitiesPy

This is a shared helper library designed to be used across multiple related testing projects.

## Installation

### Option 1: Install from GitHub (Recommended for shared projects)
To install this library directly from your GitHub repository into your other projects, you can run:

```bash
pip install git+https://github.com/rsltkscomm/Utility.git
```
*(Make sure to replace `AutoUtilities` with your actual GitHub username and use the correct repository URL).*

You can also add it directly to the `requirements.txt` of your 3 other projects like this:
```txt
utilities-py @ git+https://github.com/rsltkscomm/Utility.git@main
```

### Option 2: Install Locally (For local development)
If you are actively developing this library and want changes to be reflected immediately in your other projects locally, use editable mode:

```bash
pip install -e c:\Users\VijayManoharan\PycharmProjects\UtilitiesPy
```

## Usage

In your other projects, you can import tools from this library using the `utilities_py` package:

```python
from utilities_py.excel_helper.excel_reader import ExcelReader
from utilities_py.baseclass.PW_BaseClass import PlaywrightActions
```
