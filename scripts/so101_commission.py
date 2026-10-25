"""Read SO101 motor status, or run explicitly attended LeRobot calibration.

Run using .venv-robot/bin/python. Neither command sends goal positions.
Calibration disables torque and writes calibration registers; support the arm.
"""
import argparse
import fcntl
import json
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def status(port_name):
    import scservo_sdk as sdk
    port, packet = sdk.PortHandler(port_name), sdk.PacketHandler(0)
    rows = []
    try:
        if not port.setBaudRate(1_000_000):
            raise RuntimeError('Cannot open servo port at 1 Mbps.')
        for motor_id in range(1, 7):
            model, result, error = packet.ping(port, motor_id)
            if result != sdk.COMM_SUCCESS or error or model != 777:
                raise RuntimeError(f'Motor {motor_id}: expected STS3215; model={model}, communication={result}, error={error}')
            row = dict(id=motor_id, model=model)
            for name, address, size in [('position', 56, 2), ('torque_enabled', 40, 1),
                                        ('voltage_tenths', 62, 1), ('temperature_c', 63, 1)]:
                read = packet.read2ByteTxRx if size == 2 else packet.read1ByteTxRx
                value, result, error = read(port, motor_id, address)
                if result != sdk.COMM_SUCCESS or error:
                    raise RuntimeError(f'Motor {motor_id}: failed reading {name}: {result}, {error}')
                row[name] = value
            rows.append(row)
    finally:
        port.closePort()
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['status', 'calibrate'])
    parser.add_argument('--port')
    args = parser.parse_args()
    config = tomllib.loads((ROOT / 'config/workbench.toml').read_text())
    port = args.port or config['robot']['serial_port']
    cache = ROOT / '.cache'
    cache.mkdir(exist_ok=True)
    with (cache / 'so101-serial.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        rows = status(port)
        (cache / 'so101-readonly-status.json').write_text(json.dumps(rows, indent=2))
        print(json.dumps(rows, indent=2), flush=True)
        if args.command == 'status':
            return
        from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
        print('Calibration will release motor holding torque. Support the arm, clear its workspace, '
              'and disconnect circuit-board power. Do not force powered joints.', flush=True)
        if input('Type SUPPORTED only when physically ready: ').strip() != 'SUPPORTED':
            print('Cancelled; no torque or calibration writes sent.')
            return
        robot = SO101Follower(SO101FollowerConfig(
            port=port, id='circuit_so101', calibration_dir=cache / 'so101-calibration',
            disable_torque_on_disconnect=False))
        try:
            # Avoid connect()'s configure step; use only the attended calibration flow.
            robot.bus.connect()
            robot.calibrate()
        finally:
            if robot.bus.is_connected:
                robot.bus.disconnect(disable_torque=False)
        print('Calibration complete. Motors remain released; support and rest the arm. '
              'No pick trajectory has been taught or executed.')


if __name__ == '__main__':
    main()
