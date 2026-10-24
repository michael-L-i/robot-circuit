import pytest

@pytest.fixture(scope='session',autouse=True)
def close_api_renderer():
    yield
    import sys
    module=sys.modules.get('arm_sim.app')
    if module and hasattr(module.world,'bench'): module.world.bench.close()
