"""Connectivity and minimum-move plans for one resistor, LED and supply pair.
Terminal strips only: a-e and f-j form separate nets at each numbered row.
"""
import re
from itertools import permutations
from pydantic import BaseModel, field_validator

KEYS = ('resistor_a', 'resistor_b', 'led_anode', 'led_cathode', 'positive', 'ground')
LABELS = dict(resistor_a='Resistor lead 1', resistor_b='Resistor lead 2',
              led_anode='LED anode', led_cathode='LED cathode',
              positive='Positive jumper', ground='Ground jumper')

class Pins(BaseModel):
    resistor_a: str | None = None
    resistor_b: str | None = None
    led_anode: str | None = None
    led_cathode: str | None = None
    positive: str | None = None
    ground: str | None = None

    @field_validator('*', mode='before')
    @classmethod
    def hole(cls, value):
        if value is None or value == '':
            return None
        value = str(value).strip().lower()
        if not re.fullmatch(r'[a-j]([1-9]|[1-5][0-9]|6[0-3])', value):
            raise ValueError('Use a hole from a1 to j63; power rails are not supported.')
        return value

def net(hole):
    return ('left' if hole[0] <= 'e' else 'right', int(hole[1:]))

def strip_name(strip):
    return f"{'A–E' if strip[0] == 'left' else 'F–J'} row {strip[1]}"

def series_connected(n):
    # Resistor may be on either side of the LED; both orientations are valid.
    for a, b in (('resistor_a', 'resistor_b'), ('resistor_b', 'resistor_a')):
        for groups in ((( 'positive', a), (b, 'led_anode'), ('led_cathode', 'ground')),
                       (('positive', 'led_anode'), ('led_cathode', a), (b, 'ground'))):
            if all(n[x] == n[y] for x, y in groups) and len({n[x] for x, _ in groups}) == 3:
                return True
    return False

def inspect(pins: Pins):
    p = pins.model_dump()
    n = {k: net(v) for k, v in p.items() if v is not None}
    groups = {}
    for key, strip in n.items():
        groups.setdefault(strip, []).append(LABELS[key])
    findings = [f"{', '.join(leads)}: {strip_name(strip)}." for strip, leads in groups.items()]
    missing = [k for k, v in p.items() if v is None]
    if missing:
        return dict(status='needs_observation', summary='Partial connections identified. Exact move planning needs: ' + ', '.join(LABELS[k] for k in missing) + '.', missing=missing, findings=findings, moves=[])
    if len(set(p.values())) != len(p):
        return dict(status='needs_observation', summary='Two leads occupy the same hole. Check these observations before planning moves.', findings=findings, moves=[])
    if series_connected(n):
        return dict(status='connected', summary='The observed strips form a series resistor–LED path. Verify polarity, voltage, resistor value and electrical contact separately.', findings=findings, moves=[])

    # Enumerate topology assignments, not a scripted faulty component or hole.
    # Include spare rows so even a board with all leads on one net can be repaired.
    strips = set(n.values())
    for side in ('left', 'right'):
        spare = [ (side, row) for row in range(1,64) if (side,row) not in strips ][:3]
        strips.update(spare)
    plans = []
    seen = set()
    for a, b in (('resistor_a', 'resistor_b'), ('resistor_b', 'resistor_a')):
        for groups in ((( 'positive', a), (b, 'led_anode'), ('led_cathode', 'ground')),
                       (('positive', 'led_anode'), ('led_cathode', a), (b, 'ground'))):
            for destinations in permutations(sorted(strips), 3):
                desired = {key: dest for pair, dest in zip(groups, destinations) for key in pair}
                changed = [key for key in KEYS if n[key] != desired[key]]
                signature = tuple((key, desired[key]) for key in changed)
                if signature in seen:
                    continue
                seen.add(signature)
                # Prefer fewer moves, then flexible jumpers, then resistor, then LED.
                score = (len(changed), sum(key.startswith('led_') for key in changed),
                         sum(key.startswith('resistor_') for key in changed),
                         sum(abs(n[key][1]-desired[key][1]) + (n[key][0]!=desired[key][0])*5 for key in changed))
                plans.append((score, desired, changed))
    plans.sort(key=lambda plan: plan[0])
    def make_moves(plan):
        _, desired, changed = plan
        occupied = set(p.values())  # Don't suggest any currently occupied hole.
        moves = []
        for key in changed:
            dest = desired[key]
            columns = 'abcde' if dest[0] == 'left' else 'fghij'
            candidates = [f'{c}{dest[1]}' for c in columns if f'{c}{dest[1]}' not in occupied]
            if not candidates:
                return None
            target = min(candidates, key=lambda h: abs(ord(h[0])-ord(p[key][0])))
            occupied.add(target)
            peers = [LABELS[k] for k in KEYS if k != key and desired[k] == dest]
            moves.append(dict(component='jumper' if key in ('positive','ground') else key.split('_')[0],
                              lead=key, from_hole=p[key], to_hole=target,
                              reason=f"Join {', '.join(peers)} on {strip_name(dest)} to complete a series path."))
        return moves
    feasible = []
    minimum_moves = None
    for plan in plans:
        moves = make_moves(plan)
        if moves is not None:
            if minimum_moves is not None and plan[0][0] != minimum_moves:
                break
            minimum_moves = plan[0][0]
            feasible.append((plan, moves))
            if len(feasible) == 4:
                break
    if not feasible:
        return dict(status='invalid', summary='No free destination hole found. Review the wiring manually.', findings=findings, moves=[])
    best, moves = feasible[0]
    alternatives = [dict(moves=ms) for plan, ms in feasible[1:] if plan[0][0] == best[0][0]][:3]
    if n['positive'] == n['ground']:
        findings.insert(0, 'Positive and ground share a strip: a supply short is indicated. Disconnect power.')
    return dict(status='correction', summary=f"A series path can be made with {len(moves)} lead move(s). This is a minimum-move option, not proof of which component was originally misplaced. Check that destination holes are empty and leads can reach.",
                findings=findings, moves=moves, alternatives=alternatives)
