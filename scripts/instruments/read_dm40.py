"""Read-only DM40C BLE polling; no mode changes or robot commands.

Protocol reference: https://github.com/mriscoc/DM40Visor (dm40ble.py).
Only the observed DCV AUTO+ (0x30) profile is decoded. Verify against the
physical display before using these values as electrical test evidence.
Run: uv run --with bleak python scripts/instruments/read_dm40.py --seconds 30
"""
import argparse
import asyncio
import json
import time
from pathlib import Path
import tomllib

HEADER = bytes.fromhex('df0503090b')
TX = '0000fff1-0000-1000-8000-00805f9b34fb'
RX = '0000fff2-0000-1000-8000-00805f9b34fb'
READ = bytes.fromhex('af0503090040')


def decode(packet):
    if len(packet) != 17 or not packet.startswith(HEADER) or sum(packet) % 256:
        raise ValueError('Invalid DM40 measurement packet or checksum')
    result = dict(received_at=time.time(), raw_hex=packet.hex(), checksum_valid=True,
                  display_verified=False, contact_verified=False, mode_code=packet[5], volts=None)
    if packet[5] != 0x30:
        return dict(result, status='unsupported_mode')
    counts = int.from_bytes(packet[14:16], 'little')
    if counts == 65535:
        return dict(result, status='overload', mode='DCV AUTO+')
    # Byte 9 carries polarity in the observed DM40C firmware profile.
    return dict(result, status='unverified_reading', mode='DCV AUTO+',
                volts=round(counts * (-1 if packet[9] & 1 else 1) * .0001, 4))


async def monitor(address, seconds):
    from bleak import BleakClient
    buffer = bytearray()
    def receive(_, data):
        buffer.extend(data)
        while len(buffer) >= 17:
            start=buffer.find(HEADER)
            if start < 0:
                del buffer[:-4]; break
            del buffer[:start]
            if len(buffer)<17: break
            packet=bytes(buffer[:17]); del buffer[:17]
            try: print(json.dumps(decode(packet)), flush=True)
            except ValueError: print(json.dumps({'status':'bad_checksum'}),flush=True)
    async with BleakClient(address, timeout=15) as client:
        print(json.dumps({'status':'connected','address':address}),flush=True)
        await client.start_notify(RX,receive)
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            await client.write_gatt_char(TX,READ,response=False)
            await asyncio.sleep(1)
    print(json.dumps({'status':'disconnected'}),flush=True)


if __name__ == '__main__':
    config=tomllib.loads((Path(__file__).resolve().parents[2]/'config/workbench.toml').read_text())
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--address',default=config['measurement'].get('device_address'))
    parser.add_argument('--seconds',type=int,default=30)
    args=parser.parse_args()
    if not args.address:parser.error('Scan for a DM40C first, then supply --address.')
    if not 1<=args.seconds<=3600:parser.error('--seconds must be between 1 and 3600')
    asyncio.run(asyncio.wait_for(monitor(args.address,args.seconds),timeout=args.seconds+30))
