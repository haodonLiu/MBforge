# [Feature Request] MCS: Add `ringMatchesRingOnly` and `completeRingsOnly` options

## Problem

We're using `chematic-smarts` for MCS (Maximum Common Substructure) in our SAR analysis pipeline, but the current implementation lacks ring-awareness constraints that are critical for scaffold extraction.

Specifically, RDKit's `FindMCS` provides two ring-related options that have no equivalent in `chematic`:

- **`ringMatchesRingOnly=True`** — Ring atoms can only match ring atoms, and non-ring atoms only match non-ring atoms.
- **`completeRingsOnly=True`** — If a ring is partially included in the MCS, either the entire ring must be present or none of it.

Without these constraints, the MCS result can produce chemically meaningless fragments — e.g., matching half of a benzene ring, or matching a ring atom against a non-ring atom.

## Use Case

In drug discovery SAR analysis, we extract common scaffolds from a series of compounds. The scaffold must be a chemically meaningful substructure — partial rings are not acceptable. This is why `ringMatchesRingOnly` and `completeRingsOnly` are standard options in cheminformatics MCS tools.

## Proposed Solution

Extend `McsConfig` with two new fields:

```rust
pub struct McsConfig {
    pub match_bonds: bool,
    pub min_atoms: usize,
    pub timeout_ms: Option<u64>,
    // New:
    pub ring_matches_ring_only: bool,  // default: false
    pub complete_rings_only: bool,     // default: false
}
```

### Implementation Approach

1. Use `chematic-perception`'s SSSR ring detection to identify ring atoms/bonds in each molecule.
2. During candidate filtering in the McGregor branch-and-bound search:
   - When `ring_matches_ring_only=true`: reject atom mappings where a ring atom maps to a non-ring atom (or vice versa).
   - When `complete_rings_only=true`: after finding the MCS, verify that no ring is partially included — if any ring atom is in the MCS, all ring atoms must be present.
3. The `complete_rings_only` check can be done as post-processing: detect rings in the original molecules, check if any ring is partially covered by the MCS mapping, and if so, remove the partial ring atoms from the result.

## Examples

### Example 1: Ring/non-ring boundary (ringMatchesRingOnly)

Comparing **naproxen** and **indomethacin**:

```
Naproxen:     COc1ccc2cc(ccc2c1)C(C)C(=O)O
Indomethacin: O=C(O)Cc1cc(C(=O)Nc2c(Cl)cccc2Cl)ccc1O
```

RDKit output without `ringMatchesRingOnly`:
```
[#8]-[#6]:[#6]:[#6]:[#6](:[#6]:[#6]-[#6]-[#6](=[#8])-[#8]):,-[#6]
```
Note `:-[#6]` — ring atom matched to non-ring atom (the `,` indicates aromatic/ring bond mismatch).

RDKit output with `ringMatchesRingOnly=true`:
```
[#6]1:&@[#6]:&@[#6](:&@[#6]:&@[#6]:&@[#6]:&@1)-&!@[#6&!R]-&!@[#6&!R](=&!@[#8&!R])-&!@[#8&!R]
```
The `&!R` tags explicitly enforce ring/non-ring separation. chematic currently has no way to express this.

### Example 2: Partial ring inclusion (completeRingsOnly)

Comparing **caffeine** and **theophylline**:

```
Caffeine:    Cn1c(=O)c2c(ncn2C)n(C)c1=O
Theophylline:Cn1c(=O)c2c(ncn2C)[nH]c1=O
```

RDKit output without `completeRingsOnly`:
```
[#6]-[#7]1:[#6](=[#8]):[#6]2:[#6](:[#7]:[#6]:1=[#8]):[#7]:[#6]:[#7]:2-[#6]
```
This is actually correct for this pair (the full fused ring system matches). But consider when molecules share only a partial ring — RDKit would exclude it with `completeRingsOnly=true`. The SMARTS with ring constraints:
```
[#6&!R]-&!@[#7]1:&@[#6](=&!@[#8&!R]):&@[#6]2:&@[#6](:&@[#7]:&@[#6]:&@1=&!@[#8&!R]):&@[#7]:&@[#6]:&@[#7]:&@2-&!@[#6&!R]
```

### Example 3: Scaffold extraction in SAR (real output)

A quinoline series — this is our actual use case:

```
Compound A:  c1ccc2nc(CC)ccc2c1
Compound B:  c1ccc2nc(CO)ccc2c1
Compound C:  c1ccc2nc(CN)ccc2c1
```

RDKit output without ring constraints:
```
[#6]1:[#6]:[#6]:[#6]2:[#6](:[#6]:1):[#6]:[#6]:[#6](:[#7]:2)-[#6]
```
The trailing `-[#6]` includes the exocyclic carbon from the substituent — chemically invalid as a scaffold.

RDKit output with `ringMatchesRingOnly=true, completeRingsOnly=true`:
```
[#6]1:&@[#6]:&@[#6]:&@[#6]2:&@[#6](:&@[#6]:&@1):&@[#6]:&@[#6]:&@[#6](:&@[#7]:&@2)-&!@[#6&!R]
```
The `-&!@[#6&!R]` correctly marks the exocyclic carbon as non-ring, separating it from the quinoline scaffold.

### What chematic produces today (real output)

chematic's `find_mcs` uses pure McGregor branch-and-bound with no ring awareness. Here is the actual output for the three examples:

**Example 1 — naproxen vs indomethacin** (8 atoms, 8 bonds):
```
atom[0]: And(AtomicNum(6), Aromatic(true))   ← ring C
atom[1]: And(AtomicNum(6), Aromatic(true))   ← ring C
atom[2]: And(AtomicNum(6), Aromatic(true))   ← ring C
atom[3]: And(AtomicNum(6), Aromatic(true))   ← ring C
atom[4]: And(AtomicNum(6), Aromatic(false))  ← non-ring C ⚠️
atom[5]: And(AtomicNum(6), Aromatic(true))   ← ring C
atom[6]: And(AtomicNum(6), Aromatic(true))   ← ring C
atom[7]: And(AtomicNum(6), Aromatic(false))  ← non-ring C ⚠️
```
`atom[4]` and `atom[7]` are non-ring atoms matched to ring positions — **impossible with `ringMatchesRingOnly=true`**.

**Example 2 — caffeine vs theophylline** (13 atoms, 14 bonds):
Full fused ring system captured correctly (both molecules share the same core). This case works by coincidence — the shared substructure happens to be ring-complete.

**Example 3 — quinoline series** (11 atoms, 12 bonds):
```
atom[0-9]:  And(AtomicNum(6/7), Aromatic(true))   ← 10 ring atoms (quinoline)
atom[10]:   And(AtomicNum(6), Aromatic(false))     ← exocyclic C ⚠️
```
The quinoline ring has 10 atoms, but chematic returns **11** — the extra `atom[10]` is the exocyclic carbon from the substituent (`CC`/`CO`/`CN`). **With `ringMatchesRingOnly=true`, this non-ring atom would be excluded**, giving the correct 10-atom quinoline scaffold.

## Current Workaround

We currently rely on RDKit's `rdFMCS.FindMCS` for this functionality, which means we can't fully migrate to pure-Rust cheminformatics.

## Environment

- chematic version: 0.1.19
- Use case: SAR scaffold extraction from compound series
