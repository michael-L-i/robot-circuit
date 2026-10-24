import pytest
from arm_sim.world import Config, scripted_action
from arm_sim.physics.world import PhysicsWorld
from arm_sim.physics.bench import SkillError


def run(**config):
    world = PhysicsWorld(Config(**config))
    while not world.done and world.revision < 16:
        world.step(scripted_action(world))
    return world


@pytest.mark.parametrize('seed', [1, 7, 42])
def test_scripted_repair_closes_circuit_through_contact(seed):
    world = run(seed=seed)
    assert world.success and world.events[-1]['action'] == 'finish'
    assert [m['voltage'] for m in world.measurements] == [0.0, 5.0]
    assert world.bench.touching('jumper_pin', 'copper_mesh') and world.electrical()['led_on']
    assert all(e['ok'] for e in world.events)


def test_already_connected_needs_no_repair():
    world = run(scenario='already_connected')
    assert world.success and not world.placed


def test_missed_mesh_is_caught_by_post_placement_measurement():
    world = run(placement_error_mm=28)
    assert not world.success and world.done
    assert 'never touched' in next(e['note'] for e in world.events if e['action'] == 'place_mesh')
    assert world.measurements[-1]['voltage'] == 0.0


def test_missed_probe_contact_reads_null_not_zero():
    world = run(probe_error_mm=25)
    assert world.measurements[0] == dict(voltage=None, valid_contact=False, led_on=False, after_placement=False)
    assert not world.success


def test_supply_off_keeps_led_dark_despite_contact():
    world = run(scenario='supply_off')
    assert not world.success and world.bench.circuit_closed() and not world.bench.led


def test_render_and_clip():
    world = PhysicsWorld()
    world.step('pick_probe')
    assert world.bench.render('bench', size=(120, 160)).shape == (120, 160, 3)
    assert world.bench.clip('overview', size=(90, 120))[:4] == b'RIFF'
    world.bench.close()


def test_collision_guard_stops_motion_into_the_bench():
    world = PhysicsWorld()
    with pytest.raises(SkillError, match='Collision'):
        world.bench.move([.45, .15, -.01], 0.)


def test_failed_lift_keeps_tool_state_truthful(monkeypatch):
    world = PhysicsWorld()
    move = world.bench.move
    def lift_fails(pos, *a, **kw):
        if world.bench.held:
            raise SkillError('injected lift failure')
        return move(pos, *a, **kw)
    monkeypatch.setattr(world.bench, 'move', lift_fails)
    world.step('pick_probe')
    assert world.tool == world.bench.holding() == 'probe' and not world.events[-1]['ok']
