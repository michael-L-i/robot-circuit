"""One process serves webcam and simulator, sharing a single model engine."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from arm_sim.app import combined_app
import arm_sim.resistor.app
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(combined_app,host='127.0.0.1',port=8000,workers=1)
