import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from crypto_crash_bot.main import run_main_loop

if __name__ == "__main__":
    run_main_loop()
