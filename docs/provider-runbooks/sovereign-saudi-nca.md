# Sovereign Saudi NCA Runbook

## Authority
Saudi National Cybersecurity Authority (NCA) provides sovereign advisories, vulnerability directives, IOC intelligence, and compliance frameworks for critical sectors.

## Advisory Format
Advisories are bilingual (`title_ar/title_en`, `description_ar/description_en`) with affected sectors, actions, and optional IOC/CVE context.

## Critical Infrastructure Sectors
S3M tracks at least these sovereign sectors:
- energy
- water
- telecommunications
- government
- finance
- healthcare
- defense
- transportation

## Compliance Frameworks
Relevant frameworks for S3M:
- ECC
- CSCC
- CCC
- OTCC

CCC mapping includes implemented vs partial control coverage.

## IOC Feed
IOC types include IP, domain, hash, URL, and CVE. Confidence from NCA is treated as high-authority intelligence.

## SOC Bridge
Critical NCA advisories convert to immediate Phase 13 SOC alerts.

## CTI Bridge
NCA IOCs are suitable inputs to the Chunk 2 CTI enrichment chain for cross-source correlation.

## Air-Gapped Mode
If government API is unavailable, advisories can be delivered by file drop in the incoming directory.

## Smoke Test
```bash
python3 -m pytest -q packages/providers/sovereign-saudi-nca/tests/test_nca_adapter.py
```
