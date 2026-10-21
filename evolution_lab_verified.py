"""Evolution Lab: hypothetical breeding systems, not a reconstruction of early life.
Install: pip install numpy matplotlib
Example: python evolution_lab.py --generations 10000 --capacity 10000 --replicates 20 --mode both
Six strategies A: clone; B: 2; C: clone + two parents every 100th generation;
D: clone + two parents after a fitness decline; E: 4; F: 8.
"""
import argparse, csv
from pathlib import Path
import numpy as np

NAMES = ['A_clone','B_two','C_periodic','D_stress','E_four','F_eight']
PARENTS = [1,2,2,2,4,8]

def choose_distinct_parents(rng, indexes, weights, births, needed):
    """Weighted sampling of DISTINCT members per mating; members may be any age."""
    if len(indexes) < needed:
        raise ValueError('Insufficient compatible individuals')
    if needed == 1:
        return rng.choice(indexes, size=(births, 1), p=weights)
    # Vectorized candidate draws with collision repair; exact sequential
    # weighted sampling without replacement for small groups.
    if len(indexes) < max(40, needed * 5):
        return np.asarray([rng.choice(indexes, needed, replace=False, p=weights)
                           for _ in range(births)], dtype=np.int64)
    selected = rng.choice(indexes, size=(births, needed), replace=True, p=weights)
    for col in range(1, needed):
        collision = (selected[:, col, None] == selected[:, :col]).any(axis=1)
        attempts = 0
        while collision.any():
            selected[collision, col] = rng.choice(indexes, int(collision.sum()), p=weights)
            collision = (selected[:, col, None] == selected[:, :col]).any(axis=1)
            attempts += 1
            if attempts > 100:
                raise RuntimeError('Unable to find distinct mates; lower mating group size')
    return selected

def simulate(seed=0, generations=10000, capacity=10000, mode='established',
             sex_cost=0.12, partner_cost=0.08, mutation_rate=0.001,
             environmental_change=150, parasite_strength=0.23, log_every=100):
    """One patch, finite population, density competition, clonal/sexual strategies.
    All strategies share local resources. Haploid bit genomes and multi-parent mosaic
    are hypothetical; parental contributions differ from meiosis. Fitness is a score.
    A strategy is maternally transmitted (offspring retains focal breeder strategy).
    """
    rng = np.random.default_rng(seed)
    K = capacity
    L = 32
    start = min(K, max(120, int(K*.7)))
    genome = rng.integers(0, 2, (start,L), dtype=np.uint8)
    birth_generation = np.zeros(start, dtype=np.int32)
    mixed_age_matings = np.zeros(6, dtype=np.int64)
    if mode == 'invasion':
        strategy = np.zeros(start, dtype=np.uint8)
        # Natural appearance of strategy variants via rare, explicitly modeled mutations.
    else:
        strategy = np.arange(start, dtype=np.uint8) % 6
        rng.shuffle(strategy)
    env = rng.integers(0,2,16,dtype=np.uint8)
    parasite = rng.integers(0,2,8,dtype=np.uint8)
    old_mean = np.full(6,.5)
    records = []
    for gen in range(generations + 1):
        n = len(strategy)
        if n == 0:
            records.append({'seed':seed,'mode':mode,'generation':gen,'total':0,**{nm:0 for nm in NAMES}})
            break
        if gen and gen % environmental_change == 0:
            changed = rng.choice(16, size=2, replace=False)
            env[changed] ^= 1
        if gen and gen % 30 == 0:
            # Pathogen adaptation toward frequently seen immunity alleles, with some noise.
            parasite = (genome[:,16:24].mean(axis=0) > .5).astype(np.uint8)
            parasite ^= (rng.random(8)<.06).astype(np.uint8)
        season = np.sin(2*np.pi*gen/60)
        effective_K = max(60, int(K*(.82+.17*season)))
        if gen and gen%911==0: effective_K=int(effective_K*.60)
        fitness = (.52*(genome[:,:16]==env).mean(axis=1)
                   +parasite_strength*(genome[:,16:24]!=parasite).mean(axis=1)
                   +(.48-parasite_strength)*(genome[:,24:]==(genome[:,:8]^genome[:,8:16])).mean(axis=1))
        freq = np.bincount(strategy, minlength=6)
        if gen % log_every == 0 or gen == generations:
            rec = {'seed':seed,'mode':mode,'generation':gen,'total':n,
                   'mean_fitness':round(float(fitness.mean()),5),
                   'allelic_diversity':round(float((2*genome.mean(axis=0)*(1-genome.mean(axis=0))).mean()),5),
                   'mixed_age_matings':int(mixed_age_matings.sum())}
            rec.update({nm:int(freq[i]) for i,nm in enumerate(NAMES)})
            records.append(rec)
        if gen == generations: break
        # Survival can fail under low fitness, disease, crowding, and climate shocks.
        survival = np.clip(.18+.56*fitness - .10*max(0,n/effective_K-1),.03,.86)
        if gen%587 in (1,2,3): survival *= .72
        live = rng.random(n) < survival
        survivors_g = genome[live]
        survivors_s = strategy[live]
        survivors_birth = birth_generation[live]
        survivors_fit = fitness[live]
        # Each extant breeder gets reproductive opportunities with a declining
        # chance in a crowded population; NO enforced replacement or fixed n.
        newborn_g, newborn_s, newborn_birth = [], [], []
        stress = np.array([float(fitness[strategy==i].mean()) if freq[i] else 0 for i in range(6)])
        sex_flags = np.array([False,True,(gen%100==0),stress[3]<old_mean[3]-.012,True,True])
        old_mean = .90*old_mean+.10*stress
        for s in range(6):
            indexes = np.flatnonzero(survivors_s==s)
            m = len(indexes)
            if m == 0: continue
            parents_needed = PARENTS[s] if sex_flags[s] else 1
            if m < parents_needed: continue # mate limitation / Allee effect
            # Cost of achieving a compatible mating and biological production.
            cost = (sex_cost + partner_cost*np.log2(parents_needed)) if parents_needed>1 else 0.
            reproductive_rate = 1.5 * (1-cost) * max(.05, 1-n/(1.55*effective_K))
            births = min(2*K,int(rng.poisson(m*reproductive_rate)))
            if births == 0: continue
            # Parent selection: fitter individuals are disproportionately represented.
            w = (.15+.85*survivors_fit[indexes])**3
            p = w/w.sum()
            group = choose_distinct_parents(rng, indexes, p, births, parents_needed)
            if parents_needed == 1:
                children = survivors_g[group[:,0]].copy()
            else:
                # Count mating groups including breeders born in different generations.
                group_ages = survivors_birth[group]
                mixed_age_matings[s] += int(np.count_nonzero(np.ptp(group_ages, axis=1)))
                # Hypothetical multi-parent mosaic (NOT biological meiosis).
                which = rng.integers(0,parents_needed,(births,L))
                children = survivors_g[group[np.arange(births)[:,None],which],np.arange(L)[None,:]].copy()
            children ^= (rng.random(children.shape)<mutation_rate).astype(np.uint8)
            newborn_g.append(children)
            offspring_strat = np.full(births,s,dtype=np.uint8)
            if mode=='invasion':
                # Very rare one-step shifts in inherited reproduction programs.
                switches = rng.random(births)<1e-5
                offspring_strat[switches] = rng.integers(0,6,size=int(switches.sum()),dtype=np.uint8)
            newborn_s.append(offspring_strat)
            newborn_birth.append(np.full(births, gen+1, dtype=np.int32))
        if newborn_g:
            genome = np.concatenate([survivors_g,*newborn_g],axis=0)
            strategy = np.concatenate([survivors_s,*newborn_s])
            birth_generation = np.concatenate([survivors_birth,*newborn_birth])
        else:
            genome, strategy, birth_generation = survivors_g, survivors_s, survivors_birth
        # Competition for shared resources, individuals with higher fitness favored.
        if len(strategy)>effective_K:
            newfit = (.52*(genome[:,:16]==env).mean(axis=1)
                     +parasite_strength*(genome[:,16:24]!=parasite).mean(axis=1)
                     +(.48-parasite_strength)*(genome[:,24:]==(genome[:,:8]^genome[:,8:16])).mean(axis=1))
            priority = newfit + rng.normal(0,.12,len(strategy))
            kept = np.argpartition(priority,-effective_K)[-effective_K:]
            genome, strategy, birth_generation = genome[kept], strategy[kept], birth_generation[kept]
    return records

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--generations',type=int,default=10000)
    ap.add_argument('--capacity',type=int,default=10000)
    ap.add_argument('--replicates',type=int,default=20)
    ap.add_argument('--mode',choices=['invasion','established','both'],default='both')
    ap.add_argument('--sex-cost',type=float,default=.12)
    ap.add_argument('--partner-cost',type=float,default=.08)
    ap.add_argument('--mutation-rate',type=float,default=.001)
    ap.add_argument('--environmental-change',type=int,default=150)
    ap.add_argument('--output',default='evolution_lab_results.csv')
    args=ap.parse_args()
    if args.sex_cost + 3*args.partner_cost>=1: ap.error('total mating cost must be under 1')
    if args.capacity<120 or args.replicates<1 or args.generations<1: ap.error('invalid simulation size')
    modes=['invasion','established'] if args.mode=='both' else [args.mode]
    p=Path(args.output)
    with p.open('w',newline='') as f:
        writer=None
        for mode in modes:
            for rep in range(args.replicates):
                seed=2026+rep*137+ (0 if mode=='invasion' else 100000)
                series=simulate(seed,args.generations,args.capacity,mode,args.sex_cost,
                    args.partner_cost,args.mutation_rate,args.environmental_change)
                if writer is None:
                    writer=csv.DictWriter(f,fieldnames=series[0].keys());writer.writeheader()
                writer.writerows(series)
                last=series[-1]
                winner=max(NAMES,key=lambda name:last.get(name,0))
                print(f'{mode} replicate {rep+1}/{args.replicates}: population={last["total"]}, largest={winner} ({last.get(winner,0)})',flush=True)
    print(f'Results: {p.resolve()}')

if __name__=='__main__':main()
