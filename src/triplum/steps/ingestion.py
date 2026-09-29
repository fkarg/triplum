# Full Ingestion Pipeline

"""
Rough outline of the ingestion pipeline:
0. dataloader -> files/sources (?)
1. files -> source
2. source -> chunk
3. chunk -> text
4. text -> embedding

either:
- first loop over dataloader entries until exhaustion, then for each entry, loop over the steps 1-4
- while looping over dataloader entries, loop over steps 1-4 for each entry, then continue to next entry

depends on examples and workers etc I guess
"""
