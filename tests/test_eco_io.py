from dataclasses import replace
import csv
import gzip
import json

import numpy as np
import pytest

from evolution_lab_v2.eco_config import EcoConfig
from evolution_lab_v2.eco_io import load_checkpoint, save_checkpoint, simulate
from evolution_lab_v2.ecology import advance, initialize, state_digest


@pytest.mark.parametrize('mechanism', ['locus_mosaic', 'chromosome_partition'])
@pytest.mark.parametrize('split', [0, 3, 8])
def test_ecological_checkpoint_exact_replay(tmp_path, mechanism, split):
    cfg = EcoConfig(steps=8, log_every=5, environment='autocorrelated', parasite='tracking',
                    parasite_period=2, multiparent_mechanism=mechanism)
    full = advance(initialize(cfg))
    partial = advance(initialize(cfg), until=split)
    path = tmp_path/'checkpoint.npz'
    save_checkpoint(path, partial)
    recovered = advance(load_checkpoint(path, cfg))
    assert state_digest(full) == state_digest(recovered)
    for key in ('metrics', 'parentage', 'ledger', 'resource_ledger', 'events', 'cumulative'):
        assert getattr(full, key) == getattr(recovered, key)
    for name in full.rngs:
        assert full.rngs[name].bit_generator.state == recovered.rngs[name].bit_generator.state


def test_ecological_outputs_and_resume_byte_identical(tmp_path):
    cfg = EcoConfig(steps=7, log_every=5, checkpoint_every=4)
    full, partial, resumed = [tmp_path/x for x in ('full', 'partial', 'resumed')]
    a = simulate(cfg, full, quiet=True)
    paused = simulate(cfg, partial, stop_after=3, quiet=True)
    b = simulate(cfg, resumed, resume=partial/'checkpoint.npz', quiet=True)
    assert not paused['complete'] and a['complete'] and b['complete']
    assert a['state_sha256'] == b['state_sha256']
    for name in ('metrics.csv', 'ledger.csv', 'resources.csv', 'events.csv', 'founders.csv', 'parentage.csv.gz'):
        assert (full/name).read_bytes() == (resumed/name).read_bytes()
    with gzip.open(full/'parentage.csv.gz', 'rt', newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == sum(x['cumulative']['raw_newborns'] for x in a['strategies'].values())
    assert all(sum(json.loads(r['contributed_copies'])) == 2*cfg.loci for r in rows)
    with pytest.raises(FileExistsError):
        simulate(cfg, full)


@pytest.mark.parametrize('damage', ['genomes', 'ids', 'birth_tick', 'strategy', 'mating_type', 'mix_probability', 'resources', 'signature', 'ledger'])
def test_corrupt_eco_checkpoint_rejected(tmp_path, damage):
    cfg = EcoConfig(steps=3)
    path = tmp_path/'checkpoint.npz'
    save_checkpoint(path, advance(initialize(cfg), until=1))
    with np.load(path, allow_pickle=False) as archive:
        data = {k: archive[k].copy() for k in archive.files}
    if damage in ('resources', 'signature', 'ledger'):
        meta = json.loads(str(data['metadata'].item()))
        if damage == 'signature':
            meta['signature']['package'] = 'unknown'
        elif damage == 'resources':
            meta['resources'] = -1
        else:
            meta['ledger'] = []
        data['metadata'] = np.array(json.dumps(meta))
    elif damage == 'genomes':
        data['genomes'][0, 0, 0] = 2
    elif damage == 'ids':
        data['ids'][0] = data['ids'][1]
    elif damage == 'birth_tick':
        data['birth_tick'][0] = 100
    elif damage == 'strategy':
        data['strategy'][0] = 100
    elif damage == 'mating_type':
        data['mating_type'][0] = 100
    else:
        data['mix_probability'][0] = 1.5
    np.savez_compressed(path, **data)
    with pytest.raises(ValueError):
        load_checkpoint(path, cfg)


def test_eco_checkpoint_config_mismatch(tmp_path):
    cfg = EcoConfig(steps=3)
    path = tmp_path/'checkpoint.npz'
    save_checkpoint(path, initialize(cfg))
    with pytest.raises(ValueError, match='configuration mismatch'):
        load_checkpoint(path, replace(cfg, mating_cost=.1))
