# OPS Checklist — Silence-Trigger Trucks
**Date:** 2026-06-12

> **Retrospective-artifact note:** In this retrospective snapshot, trucks whose
> history ends before the fleet data wall appear silent by construction.
> Silence is NOT proof of failure — 5 NF trucks are also SMA-dead.
> This checklist is for connectivity verification only.

---
## 72-Hour Connectivity Check Procedure

For each truck listed below, complete within 72 hours:

1. **Verify vehicle operational status** — contact depot/driver to confirm
   the truck is in service (not parked, off-route, or in maintenance hold).
2. **Check telematics connectivity** — confirm the ECU/telemetry unit is
   powered and transmitting. Check antenna, SIM card, and gateway status.
3. **Force a manual data poll** if supported by the fleet management platform.
4. **If truck is operational but telematics silent:** escalate to telematics
   maintenance team; tag VIN in fleet system as 'telemetry fault'.
5. **If truck is NOT operational (parked/decommissioned):** update fleet
   status and remove from active monitoring queue.
6. **If truck is operational and telemetry resumes:** no further action;
   PdM system will re-score on next weekly run.

---
## Affected Trucks

| VIN | Tier | Silence (days) | Evidence Summary |
|-----|------|----------------|-----------------|
| VIN10_F_SM | RED | 50 | silence_days=50; tier=RED; ops check <=72h |
| VIN10_NF_SM | AMBER | 356 | silence_days=356; tier=AMBER; ops check <=72h |
| VIN11_F_SM | RED | 87 | silence_days=87; tier=RED; ops check <=72h |
| VIN12_F_SM | RED | 72 | silence_days=72; tier=RED; ops check <=72h |
| VIN13_F_SM | RED | 103 | silence_days=103; tier=RED; ops check <=72h |
| VIN14_F_SM | RED | 92 | silence_days=92; tier=RED; ops check <=72h |
| VIN20_NF_SM | RED | 144 | silence_days=144; tier=RED; ops check <=72h |
| VIN2_F_SM | RED | 66 | silence_days=66; tier=RED; ops check <=72h |
| VIN4_F_SM | AMBER | 199 | silence_days=199; tier=AMBER; ops check <=72h |
| VIN5_F_SM | RED | 113 | silence_days=113; tier=RED; ops check <=72h |
| VIN6_F_SM | RED | 105 | silence_days=105; tier=RED; ops check <=72h |
| VIN7_F_SM | RED | 101 | silence_days=101; tier=RED; ops check <=72h |
| VIN8_F_SM | RED | 114 | silence_days=114; tier=RED; ops check <=72h |

---
## Sign-Off

| VIN | Checked by | Date | Status | Notes |
|-----|-----------|------|--------|-------|
| VIN10_F_SM | | | | |
| VIN10_NF_SM | | | | |
| VIN11_F_SM | | | | |
| VIN12_F_SM | | | | |
| VIN13_F_SM | | | | |
| VIN14_F_SM | | | | |
| VIN20_NF_SM | | | | |
| VIN2_F_SM | | | | |
| VIN4_F_SM | | | | |
| VIN5_F_SM | | | | |
| VIN6_F_SM | | | | |
| VIN7_F_SM | | | | |
| VIN8_F_SM | | | | |

---
*Return completed checklist to fleet operations supervisor.*