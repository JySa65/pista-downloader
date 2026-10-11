import multiprocessing

from pista.ui.app import run_app

if __name__ == "__main__":
    multiprocessing.freeze_support()  # required for the frozen (PyInstaller) build
    run_app()
