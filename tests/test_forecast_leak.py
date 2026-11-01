"""The forecast at slot t must not depend on demand the controller has not seen."""
import copy

import numpy as np
import pytest

from traffic.dataset import load_trace
from traffic.forecaster import Forecaster
from traffic.generator import make_trace
from utils.config import REAL_TRACE, load_config


@pytest.mark.parametrize("t", [1, 20, 60, 99])
def test_future_demand_does_not_change_forecast(t):
    cfg = load_config()
    tr = make_trace("event_surge", load_trace(REAL_TRACE), 5)
    fc = Forecaster(cfg)
    a = fc.predict_trace(tr, lag=1)[t]
    bad = copy.deepcopy(tr)
    bad.rate[t:] = np.random.default_rng(0).uniform(0, 80, bad.rate[t:].shape)
    assert np.allclose(a, fc.predict_trace(bad, lag=1)[t])
