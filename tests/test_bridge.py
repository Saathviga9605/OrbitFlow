"""The sampler and its log-probability must agree, or the policy gradient is wrong."""
import itertools

import numpy as np
import torch

from bridge.policy import plackett_luce_logprob, sample_topk, to_watts


def test_plackett_luce_is_a_distribution_and_matches_sampler():
    torch.manual_seed(0)
    z = torch.tensor([[0.5, -1.0, 2.0, 0.0, 1.0]])
    perms = list(itertools.permutations(range(5), 3))
    lp = plackett_luce_logprob(z.repeat(len(perms), 1), torch.tensor(perms))
    probs = lp.exp()
    assert abs(float(probs.sum()) - 1.0) < 1e-5
    samples = sample_topk(z.repeat(200_000, 1), 3)
    uniq, counts = np.unique(samples.numpy(), axis=0, return_counts=True)
    freq = {tuple(u): c / 200_000 for u, c in zip(uniq.tolist(), counts)}
    for perm, p in zip(perms, probs.tolist()):
        assert abs(freq.get(perm, 0.0) - p) < 0.01


def test_watts_respect_floor_and_total():
    w = np.random.default_rng(0).dirichlet(np.ones(4), 100)
    for row in w:
        p = to_watts(row, 2.0, 100.0)
        assert abs(p.sum() - 100.0) < 1e-6 and (p >= 2.0 - 1e-9).all()
