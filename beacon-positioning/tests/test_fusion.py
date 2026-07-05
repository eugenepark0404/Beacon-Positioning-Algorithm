"""파티클 필터 수렴성 검증. # ref: P2"""
import numpy as np

from ble_positioning.config.settings import ParticleFilterParams
from ble_positioning.fusion.interfaces import BlePositionInput, PdrStep
from ble_positioning.fusion.particle_filter import ParticleFilter2D


def test_pf_converges_to_static_target():
    pf = ParticleFilter2D(ParticleFilterParams(n_particles=3000),
                          bounds=(0, 0, 20, 20), rng=np.random.default_rng(0))
    for t in range(30):
        pf.update_ble(BlePositionInput(timestamp=float(t), x=12.0, y=5.0, sigma_m=1.5))
    x, y = pf.estimate()
    assert np.hypot(x - 12.0, y - 5.0) < 1.0


def test_pf_accepts_pdr_interface():
    pf = ParticleFilter2D(ParticleFilterParams(n_particles=1000), bounds=(0, 0, 10, 10))
    pf.update_ble(BlePositionInput(0.0, 5.0, 5.0, 2.0))
    pf.update_pdr(PdrStep(timestamp=0.6, step_length_m=0.7, heading_rad=0.0))
    assert pf.estimate() is not None


def test_map_constraint_hook():
    pf = ParticleFilter2D(ParticleFilterParams(n_particles=500), bounds=(0, 0, 10, 10))
    pf.map_constraint = lambda x, y: (min(x, 9.0), y)  # P5 도면 사후보정 훅
    pf.update_ble(BlePositionInput(0.0, 20.0, 5.0, 0.5))
    x, y = pf.estimate()
    assert x <= 9.0
