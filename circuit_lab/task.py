"""Physical task context; geometry and electrical values require commissioning."""
TASK = {
    'id': 'resistor_swap',
    'title': 'Probe → replace resistor → verify',
    'description': 'The wiring is intended to be correct. Replace the faulty resistor module with the good spare using their enlarged rectangular grips.',
    'steps': [
        'Identify the board, copper-mesh test surface, probe, faulty module and spare.',
        'Verify supply/reference and valid probe contact; record the initial voltage.',
        'Dock the probe and disconnect circuit power before replacing the module.',
        'Remove the faulty resistor module and install the good spare in the same socket.',
        'Restore circuit power, probe the same test net again and check LED illumination.',
    ],
    'measurement_transport': 'Bluetooth',
    'measurement_configured': False,
    'motion_enabled': False,
}
CONTEXT = '''The CURRENT physical task is resistor replacement, not correcting misplaced wires.
The user reports that the circuit wiring is already correct, one installed resistor
is faulty, and a good spare is available. The resistor modules have enlarged
rectangular grip structures for the SO101. Treat these as user-provided task
context, not proof that an image shows a particular fault or that the spare works.
A copper mesh enlarges the probe target on a test net. The probe must touch the
electrically connected mesh; its reference/ground and valid contact must be
established. The planned sequence is: probe before replacement, dock the probe,
disconnect circuit power, swap the resistor module into the same socket, restore
power, then re-probe the same net and inspect LED illumination.
The user's expected symptom is approximately zero volts before replacement and
an illuminated LED afterward. The instrument is Bluetooth, but its model/protocol
and expected healthy voltage are NOT configured. No live measurements are
available. Never invent readings. Zero alone cannot distinguish an open resistor
from a missing supply, wrong reference, or missed contact. An image cannot verify
resistance or electrical continuity. Do not propose rewiring as the default task.
'''
