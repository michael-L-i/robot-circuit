"""Background reader for the Alientek DM40C multimeter over BLE (uses the vendored dm40ble driver)."""
import asyncio, threading, time
from dm40ble import Com_DM40


class Meter:
    """Polls the meter in its own thread; .value is the latest reading in volts (None until connected)."""
    def __init__(self, period=0.15):
        self.value, self.unit, self.mode, self.error = None, '', '', None
        self.updated = 0.0
        self._period, self._stop = period, threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True); self._thread.start()

    def _run(self):
        asyncio.run(self._loop())

    async def _loop(self):
        m = Com_DM40(max_retry=3)
        try:
            await m.connect()
            while not self._stop.is_set():
                v, unit, mode = await m.get_data()
                if v is not None:
                    try: self.value = float(v) * (1e-3 if unit == 'mV' else 1.0)
                    except ValueError: self.value = float('inf') if v == 'OL' else None
                    self.unit, self.mode, self.updated = unit, mode, time.time()
                await asyncio.sleep(self._period)
        except Exception as e:
            self.error = str(e)
        finally:
            try: await m.disconnect()
            except Exception: pass

    def wait_ready(self, timeout=25):
        t = time.time()
        while time.time() - t < timeout and self.value is None and self.error is None: time.sleep(0.1)
        return self.value is not None

    def fresh(self, max_age=0.8):
        return self.value if time.time() - self.updated < max_age else None

    def close(self):
        self._stop.set(); self._thread.join(timeout=5)
