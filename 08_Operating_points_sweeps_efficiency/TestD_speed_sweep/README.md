# Test D: speed sweep, Rev0 and Rev1-S (same tests on both machines)

Post-processing only: the solved rotating field models (FMROT_REV0, jobs 1500352/1500707; FMROT_REV1S, job 1502103)
re-evaluated from 250 to 4000 rpm. No model was changed. Inputs: K = 18.534 / 39.50 mN·m/A, measured R = 1.89 Ω per
stator (α = 0.00393 /K), track eddy loss at 1000 rpm 20.4 / 44.2 mW (∝ speed²), L = 25 µH per stator,
SVPWM m = 0.95, thermal resistance per stator from Icepak (8.75 / 14.8 K/W).

| File | Content | Brief heading |
|---|---|---|
| D1_backemf_vs_speed.png | Line back-EMF against speed with the 12 V and 24 V bus limits | Back-EMF characteristics |
| D2_losses_vs_speed.png | Copper and track-eddy loss, eddy drag torque | Electromagnetic losses |
| D3_torque_speed_envelopes.png | Torque-speed envelopes at 0.84 A pk, 12 V and 24 V | Torque production, performance |
| D4_efficiency_maps.png | Electromagnetic efficiency maps | Efficiency and losses |
| D5_thermal_current_vs_speed.png | Current that keeps the board at 60 °C against speed | Thermal behaviour |
| D_speed_sweep_table.csv | Numbers at 250, 500, 1000, 2000, 3000, 4000 rpm (incl. skin depth) | Coreless behaviour |
| speed_sweep.py | The script (re-run: python3 speed_sweep.py) | |
