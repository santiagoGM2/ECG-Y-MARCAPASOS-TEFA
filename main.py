import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from src.appUI import ECGApp
if __name__ == "__main__":
    print("=== 📊 MONITOR ECG CON INTERFAZ TKINTER ===")
    app = ECGApp()
    app.mainloop()