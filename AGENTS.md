# Project

Hodes Pytomator is an open-source automation tool designed to automate user interactions with any application.
Its basically a Python-based framework that allows users to create scripts to simulate mouse clicks, keyboard inputs, and other user actions to automate repetitive tasks across different applications.

## Requirements

- Python 3.12 or higher
- UV Python Package Manager

## Configuration and building

- check README.md

## Structure

The codebase is inside `src/pytomator`.
- config (Model): Contains configuration files and settings for the application, including user preferences and application settings.
- ui (View): Contains the user interface components of the application, including windows, dialogs, and other visual elements.
- core (Model, Controller): Contains the core logic and functionality of the application, including the main automation engine,
    - automator: Contains the core automation logic, including classes and functions for simulating user interactions, managing scripts, and executing automation tasks.
- resources (Model): Contains static resources used by the application, such as images, icons, and other media files.

## Core automation API

The core automation API is located in `src\pytomator\core\automator\api.py`.
- There are the functions exposed to the automation scripts
- They are described and documented using decorator @pytomator_api `src\pytomator\core\decorators.py`



## Code Architecture

- The design choosen for the project is based on the Model-View-Controller (MVC) pattern.
- Preferably, OOP (Object-Oriented Programming) 
    - Prefer one file for each class, and one file for each interface.


