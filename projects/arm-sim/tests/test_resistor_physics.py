import pytest
from arm_sim.resistor.world import ResistorWorld, ResistorConfig, scripted_action


def run(**config):
    world = ResistorWorld(ResistorConfig(**config))
    while not world.done and world.revision < 20:
        world.step(scripted_action(world))
    world.bench.close()
    return world


def readings(world):
    return [(m['point'], m['voltage']) for m in world.measurements]


@pytest.mark.parametrize('seed', [1, 7, 42])
def test_camera_guided_swap_repairs_open_resistor(seed):
    world = run(seed=seed)
    assert world.success and all(e['ok'] for e in world.events)
    assert readings(world) == [('input', 5.0), ('output', 0.0), ('output', 2.0)]
    assert world.bench.installed() == 'resistor_b' and world.bench.in_bin('resistor_a') and world.bench.led


def test_oracle_baseline_matches():
    world = run(perception='oracle')
    assert world.success and world.revision == 12


def test_healthy_circuit_needs_no_swap():
    world = run(scenario='healthy')
    assert world.success and world.socket == 'resistor_a' and not world.discarded


def test_dead_supply_is_not_blamed_on_the_resistor():
    world = run(scenario='supply_off')
    assert not world.success and world.events[-1]['action'] == 'abort'
    assert 'remove_resistor' not in [e['action'] for e in world.events]


def test_bad_spare_aborts_after_one_swap():
    world = run(scenario='bad_spare')
    assert not world.success and readings(world)[-1] == ('output', 0.0)
    assert [e['action'] for e in world.events].count('insert_resistor') == 1


def test_missed_probe_reads_null_and_stops():
    world = run(perception='oracle', probe_error_mm=25)
    assert world.measurements[0]['voltage'] is None and not world.success


def test_disallowed_actions_are_rejected_before_motion():
    world = ResistorWorld(ResistorConfig(perception='oracle'))
    with pytest.raises(ValueError):
        world.step('remove_resistor')                   # no diagnosis yet
    assert world.revision == 0
    world.bench.close()
