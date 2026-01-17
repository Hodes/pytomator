# Hodes Pytomator

A Python application to run automations

## Installation

1. Virtual Environment (optional but recommended)

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
   ```

2. Install Dependencies

   ### Poetry

   Install Poetry if you haven't already:

   ```bash
   pip install poetry
   ```

   Then install dependencies:

   ```bash
   poetry install --with dev
   ```

3. Build resources

   ```bash
   poetry run build-resources
   ```

4. Run the Application

   ```bash
   poetry run pytomator
   ```

5. Packaging

   To create a standalone executable, use build script:

   ```bash
   poetry run build
   ```

   The executable will be located in the `dist` directory.

## Usage

Run the application and use the GUI to write and execute Python scripts for automating tasks.

It has an api of wrappers around common operations to facilitate automation.
Check 'src/pytomator/core/automator/api.py' for available functions.
