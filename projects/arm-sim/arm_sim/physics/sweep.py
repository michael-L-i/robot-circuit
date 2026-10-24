"""Placement-tolerance sweep: how far off can the jumper land and still close the circuit?

    python -m arm_sim.physics.sweep        (from projects/arm-sim)
"""
import numpy as np
from .bench import Bench
from . import scene


def trial(dx, dy):
    bench = Bench(jumper_xy=scene.JUMPER_START)
    bench.pick('jumper')
    bench.place_jumper(dx, dy)
    bench.settle(.5)
    return bench.circuit_closed()


if __name__ == '__main__':
    offsets = np.arange(-20, 21, 4)
    print(f"mesh {2*scene.MESH['size'][0]*1000:.0f} x {2*scene.MESH['size'][1]*1000:.0f} mm; rows = y error, cols = x error (mm)")
    print('      ' + ''.join(f'{x:>4d}' for x in offsets))
    for dy in offsets:
        print(f'{dy:>5d} ' + ''.join('   #' if trial(dx/1000, dy/1000) else '   .' for dx in offsets))
