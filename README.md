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
   poetry install
   ```

3. Build resources

   ```bash
   poetry run build_resources
   ```

4. Run the Application
   ```bash
   python -m pytomator.app
   ```
